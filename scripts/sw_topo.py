"""sw_topo.py — 拓扑查询 / 稳定引用 / 测量（零件级；装配组件见 sw_asm_ref）

给 AI 一个"先看几何、再按稳定 ID 操作、做完测量验证"的闭环：
    - topology()       列出面/边：类型、几何参数、面积/长度、名字、持久 ID
    - resolve()        把引用解析成实体：{"name"} / {"persist_id"} / {"spec"} / {"ray"}
    - name_entity()    给面/边/顶点起名（IPartDoc.SetEntityName，随零件保存）
    - measure()        IMeasure：距离/角度/半径/面积等
    - mass()           体积/质量/质心/表面积

SW2018 v26 实测要点（probe_api.py）：
    - GetPersistReference3 返回字节数组，GetObjectByPersistReference3 回查得同一实体
      （IsSame=1），重建后依然有效，是比 Face<n> 名字更稳定的引用。
    - SetEntityName/GetEntityByName 在零件中可用；名字存进文件，装配体中可经
      IComponent2.GetCorrespondingEntity 映射到装配上下文（见 sw_asm_ref）。
    - SelectByRay 可用；IMeasure.Calculate(None) 测量当前选择集。
所有输入/输出长度单位：毫米；角度：度。
"""
import base64
import math

import pythoncom
from win32com.client import VARIANT

import sw_core
import sw_sel

# swSelectType_e
SEL_EDGES, SEL_FACES, SEL_VERTICES = 1, 2, 3
_KIND_TO_SEL = {"face": SEL_FACES, "edge": SEL_EDGES, "vertex": SEL_VERTICES}


class RefError(RuntimeError):
    """引用无法解析成实体。"""


# ---------------------------------------------------------------------------
# 持久 ID / 实体名
# ---------------------------------------------------------------------------

def persist_id(model, entity):
    """实体 -> 持久 ID（base64 字符串）；失败返回 None。"""
    try:
        ref = model.Extension.GetPersistReference3(entity)
    except Exception:
        return None
    if ref is None:
        return None
    try:
        raw = bytes(ref) if not isinstance(ref, (list, tuple)) else bytes(int(b) & 0xFF for b in ref)
    except Exception:
        return None
    return base64.b64encode(raw).decode("ascii")


def from_persist_id(model, pid):
    """持久 ID -> 实体；失败抛 RefError。"""
    try:
        raw = base64.b64decode(pid)
    except Exception as exc:
        raise RefError(f"persist_id 不是合法 base64: {exc}") from exc
    arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1, raw)
    try:
        r = model.Extension.GetObjectByPersistReference3(arr, 0)
    except Exception as exc:
        raise RefError(f"GetObjectByPersistReference3 失败: {exc}") from exc
    obj, err = r if isinstance(r, tuple) else (r, 0)
    if obj is None:
        # swPersistReferencedObjectStates_e: 0 OK, 1 Deleted, 2 Invalid, 3 Suppressed
        state = {1: "实体已被删除", 2: "引用无效", 3: "实体所在特征被压缩"}.get(err, f"err={err}")
        raise RefError(f"持久 ID 无法回查：{state}")
    return obj


def entity_name(model, entity):
    """读零件实体名（未命名返回空串）。"""
    try:
        part = sw_core._early(model, "IPartDoc")
        return str(part.GetEntityName(entity) or "")
    except Exception:
        return ""


def find_named(model, name, kind=None):
    """按名字找零件实体；kind 缺省依次尝试 face/edge/vertex。"""
    part = sw_core._early(model, "IPartDoc")
    kinds = [kind] if kind else ["face", "edge", "vertex"]
    for k in kinds:
        try:
            ent = part.GetEntityByName(str(name), _KIND_TO_SEL[k])
        except Exception:
            ent = None
        if ent is not None:
            return ent, k
    raise RefError(f"零件中没有名为 {name!r} 的{'/'.join(kinds)}（先用 entity_name 命名）")


def name_entity(model, entity, name):
    """给零件实体命名（随零件保存）。重名时 SW 返回 False。"""
    part = sw_core._early(model, "IPartDoc")
    ok = bool(part.SetEntityName(entity, str(name)))
    if not ok:
        raise RefError(f"SetEntityName({name!r}) 失败：名字可能已被其他实体占用")
    return True


# ---------------------------------------------------------------------------
# 拓扑
# ---------------------------------------------------------------------------

def _bodies(model):
    part = sw_core._early(model, "IPartDoc")
    out = []
    for body_type in (0, 1):  # swSolidBody, swSheetBody
        try:
            out += [sw_core._early(b, "IBody2") for b in (part.GetBodies2(body_type, True) or [])]
        except Exception:
            pass
    return out


def iter_faces(model):
    for bi, body in enumerate(_bodies(model)):
        for f in (body.GetFaces() or []):
            yield bi, sw_core._early(f, "IFace2")


def iter_edges(model):
    for bi, body in enumerate(_bodies(model)):
        for e in (body.GetEdges() or []):
            yield bi, sw_core._early(e, "IEdge")


def _round(v, nd=4):
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, (list, tuple)):
        return [_round(x, nd) for x in v]
    return v


def face_record(model, face, index, body_index=0, with_id=True):
    info = sw_sel.face_info(face)
    rec = {"index": index, "body": body_index, **info}
    try:
        box = face.GetBox()
        rec["box_mm"] = [float(v) * 1000.0 for v in box]
    except Exception:
        pass
    try:
        rec["edge_count"] = int(face.GetEdgeCount())
    except Exception:
        pass
    try:
        feat = face.GetFeature()
        rec["feature"] = sw_core.feature_name(feat) if feat is not None else None
    except Exception:
        pass
    name = entity_name(model, face)
    if name:
        rec["name"] = name
    if with_id:
        rec["persist_id"] = persist_id(model, face)
    return _round(rec)


def edge_record(model, edge, index, body_index=0, with_id=True):
    rec = {"index": index, "body": body_index, **sw_sel.edge_info(edge)}
    name = entity_name(model, edge)
    if name:
        rec["name"] = name
    if with_id:
        rec["persist_id"] = persist_id(model, edge)
    return _round(rec)


def topology(model, include=("faces",), kind=None, limit=200, with_ids=True):
    """列出零件拓扑。kind 过滤面类型（plane/cylinder/...）；limit 截断数量。"""
    out = {"bodies": len(_bodies(model))}
    if "faces" in include:
        faces = []
        total = 0
        for i, (bi, f) in enumerate(iter_faces(model)):
            rec = face_record(model, f, i, bi, with_ids)
            if kind and rec.get("kind") != kind:
                continue
            total += 1
            if len(faces) < limit:
                faces.append(rec)
        out["faces"] = faces
        out["face_total"] = total
    if "edges" in include:
        edges = []
        total = 0
        for i, (bi, e) in enumerate(iter_edges(model)):
            total += 1
            if len(edges) < limit:
                edges.append(edge_record(model, e, i, bi, with_ids))
        out["edges"] = edges
        out["edge_total"] = total
    out["truncated"] = any(out.get(f"{k}_total", 0) > limit for k in ("face", "edge"))
    return out


# ---------------------------------------------------------------------------
# 引用解析 / 选择
# ---------------------------------------------------------------------------

def ray_pick(model, origin_mm, direction, radius_mm=0.5, kind="face"):
    """沿射线拾取第一个实体。origin_mm 为射线起点（毫米），direction 为方向向量。"""
    sel_type = _KIND_TO_SEL.get(kind, SEL_FACES)
    d = sw_sel._unit([float(v) for v in direction])
    o = [float(v) / 1000.0 for v in origin_mm]
    model.ClearSelection2(True)
    ok = model.Extension.SelectByRay(o[0], o[1], o[2], d[0], d[1], d[2],
                                     float(radius_mm) / 1000.0, sel_type, False, 0, 0)
    if not ok:
        raise RefError(f"射线 origin={origin_mm} dir={direction} 未命中任何{kind}")
    sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
    ent = sm.GetSelectedObject6(1, -1)
    model.ClearSelection2(True)
    return ent


def resolve(model, ref):
    """引用 -> (实体, kind)。

    ref 形式（任选其一）：
        {"name": "HOLE"}                         实体名（零件中已命名）
        {"persist_id": "<base64>"}               topology 返回的持久 ID
        {"index": 3, "kind": "face"}             topology 返回的序号（模型改动后会变）
        {"spec": {"kind": "cylinder", "radius_mm": 5}}   sw_sel 几何过滤
        {"ray": {"origin_mm": [0,0,50], "direction": [0,0,-1]}, "kind": "face"}
    """
    if not isinstance(ref, dict):
        raise RefError(f"引用必须是 dict，收到 {ref!r}")
    kind = ref.get("kind")
    if ref.get("persist_id"):
        return from_persist_id(model, ref["persist_id"]), kind or "face"
    if ref.get("name"):
        ent, k = find_named(model, ref["name"], kind if kind in _KIND_TO_SEL else None)
        return ent, k
    if ref.get("ray"):
        r = ref["ray"]
        k = kind or "face"
        return ray_pick(model, r["origin_mm"], r["direction"], r.get("radius_mm", 0.5), k), k
    if ref.get("spec"):
        spec = ref["spec"]
        if spec.get("kind") == "edge":
            hits = sw_sel.collect_edges(model, spec)
            k = "edge"
        elif spec.get("kind") == "vertex":
            hits = sw_sel.collect_vertices(model, spec)
            k = "vertex"
        else:
            hits = sw_sel.collect_faces(model, spec)
            k = "face"
        if not hits:
            raise RefError(f"没有实体满足 spec {spec}")
        return hits[0][0], k
    if "index" in ref:
        k = kind or "face"
        it = iter_faces(model) if k == "face" else iter_edges(model)
        for i, (_, ent) in enumerate(it):
            if i == int(ref["index"]):
                return ent, k
        raise RefError(f"{k} 序号 {ref['index']} 超出范围")
    raise RefError(f"无法识别的引用 {ref!r}：需要 name/persist_id/spec/ray/index 之一")


def select(model, entity, append=False, mark=0):
    """选择实体对象（IEntity.Select4，失败回退 IFeature.Select2）。"""
    return sw_sel._select_entity(model, entity, append, mark) or _select_feature(entity, append, mark)


def _select_feature(obj, append, mark):
    try:
        return bool(sw_core._early(obj, "IFeature").Select2(bool(append), int(mark)))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 测量 / 质量
# ---------------------------------------------------------------------------

_MEASURE_FIELDS = (
    ("Distance", "distance_mm", 1000.0), ("NormalDistance", "normal_distance_mm", 1000.0),
    ("CenterDistance", "center_distance_mm", 1000.0), ("Angle", "angle_deg", None),
    ("Radius", "radius_mm", 1000.0), ("Diameter", "diameter_mm", 1000.0),
    ("Length", "length_mm", 1000.0), ("Area", "area_mm2", 1e6),
    ("Perimeter", "perimeter_mm", 1000.0), ("TotalLength", "total_length_mm", 1000.0),
    ("TotalArea", "total_area_mm2", 1e6),
)


def measure_selection(model):
    """测量当前选择集（1~2 个实体）。值为 -1 的字段（不适用）省略。"""
    m = model.Extension.CreateMeasure()
    m.ArcOption = 0  # 圆弧按圆心测
    if not m.Calculate(None):
        raise RefError("IMeasure.Calculate 失败：所选实体组合不支持测量")
    out = {}
    for attr, key, scale in _MEASURE_FIELDS:
        try:
            v = float(getattr(m, attr))
        except Exception:
            continue
        if v == -1:
            continue
        out[key] = round(math.degrees(v), 4) if scale is None else round(v * scale, 4)
    for attr, key in (("IsParallel", "parallel"), ("IsPerpendicular", "perpendicular"),
                      ("IsIntersect", "intersect")):
        try:
            out[key] = bool(getattr(m, attr))
        except Exception:
            pass
    try:
        dx, dy, dz = float(m.DeltaX), float(m.DeltaY), float(m.DeltaZ)
        if not (dx == dy == dz == -1):
            out["delta_mm"] = [round(dx * 1000, 4), round(dy * 1000, 4), round(dz * 1000, 4)]
    except Exception:
        pass
    return out


def measure(model, ref1, ref2=None):
    """测量一个或两个引用实体之间的几何关系。"""
    e1, _ = resolve(model, ref1)
    entities = [e1]
    if ref2 is not None:
        entities.append(resolve(model, ref2)[0])
    return measure_entities(model, entities)


def measure_entities(model, entities):
    model.ClearSelection2(True)
    for i, ent in enumerate(entities):
        if not select(model, ent, append=i > 0, mark=0):
            raise RefError(f"测量前选择第 {i + 1} 个实体失败")
    try:
        return measure_selection(model)
    finally:
        model.ClearSelection2(True)


def mass(model):
    """体积/质量/质心/表面积（毫米制输出）。"""
    mp = model.Extension.CreateMassProperty()
    if mp is None:
        raise RuntimeError("CreateMassProperty 返回 None：文档中可能没有实体")
    out = {
        "volume_mm3": round(float(mp.Volume) * 1e9, 3),
        "surface_area_mm2": round(float(mp.SurfaceArea) * 1e6, 3),
        "mass_kg": round(float(mp.Mass), 6),
        "density_kg_m3": round(float(mp.Density), 3),
        "center_of_mass_mm": [round(float(v) * 1000.0, 4) for v in mp.CenterOfMass],
    }
    try:
        box = sw_core._early(model, "IPartDoc").GetPartBox(True)
        out["bbox_mm"] = [round(float(v) * 1000.0, 4) for v in box]
    except Exception:
        pass
    return out
