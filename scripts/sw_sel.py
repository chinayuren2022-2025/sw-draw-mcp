"""sw_sel.py — 几何属性选择器（补全清单 2.4/2.6）

按几何属性（面类型/法向/半径/面积、边类型/长度/半径、顶点坐标）反查并选择实体，
不依赖视角与模型空间坐标拾取。所有输入坐标单位：毫米；内部转为米。

spec 字典示例：
    {"kind": "plane",  "normal": [0,0,1], "root_mm": [0,0,5], "select": "largest"}
    {"kind": "cylinder", "radius_mm": 12.5, "axis": [0,1,0]}
    {"kind": "edge", "type": "circle", "radius_mm": 12.5, "near_mm": [0,0,0]}
    {"kind": "vertex", "near_mm": [0,0,0]}
"""
import math

import sw_core


class SelectError(RuntimeError):
    """无法按 spec 找到/选择实体。"""


def _faces(model):
    """遍历零件面（实体 + 曲面体；swSolidBody=0, swSheetBody=1, swAllBodies=5）。"""
    part = sw_core._early(model, "IPartDoc")
    seen = set()
    for body_type in (0, 1, 5):
        try:
            bodies = part.GetBodies2(body_type, False) or []
        except Exception:
            continue
        for b in bodies:
            b = sw_core._early(b, "IBody2")
            for f in (b.GetFaces() or []):
                face = sw_core._early(f, "IFace2")
                try:
                    key = (id(face), str(getattr(face, "GetFaceId", lambda: "")())[:0])
                except Exception:
                    key = None
                if key not in seen:
                    seen.add(key)
                    yield face


def _edges(model):
    part = sw_core._early(model, "IPartDoc")
    for b in (part.GetBodies2(0, False) or []):
        b = sw_core._early(b, "IBody2")
        for e in (b.GetEdges() or []):
            yield sw_core._early(e, "IEdge")


def _vertices(model):
    part = sw_core._early(model, "IPartDoc")
    for b in (part.GetBodies2(0, False) or []):
        b = sw_core._early(b, "IBody2")
        for v in (b.GetVertices() or []):
            yield sw_core._early(v, "IVertex")


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 1e-12 else list(v)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _near(a, b, tol=0.2):
    if a is None or b is None:
        return True
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) <= tol


def _parallel_dir(a, b, tol=1e-3, directional=False):
    """方向平行（directional=True 要求同向）。"""
    u, v = _unit(a), _unit(b)
    dot = _dot(u, v)
    return abs(abs(dot) - 1.0) < tol if not directional else abs(dot - 1.0) < tol


def face_area(f):
    try:
        return float(f.GetArea()) * 1e6
    except Exception:
        return 0.0


def face_info(face):
    """返回 {kind, params...}；单位毫米。"""
    surf = sw_core._early(face.GetSurface(), "ISurface")
    info = {"area_mm2": face_area(face)}
    try:
        if surf.IsPlane():
            p = surf.PlaneParams  # [法向 xyz, 根点 xyz]（SW2018 实测布局）
            # PlaneParams 的法向是曲面法向，约一半的面与面外法向相反（面与曲面反向）；
            # IFace2.Normal 才是实体外法向，directional 过滤依赖它。
            try:
                n = _unit([float(v) for v in face.Normal])
            except Exception:
                n = _unit([float(v) for v in p[0:3]])
            info.update(kind="plane", normal=n,
                        root_mm=[float(v) * 1000.0 for v in p[3:6]])
        elif surf.IsCylinder():
            p = surf.CylinderParams  # [根点 xyz, 轴 xyz, 半径]
            info.update(kind="cylinder",
                        root_mm=[float(v) * 1000.0 for v in p[0:3]],
                        axis=_unit([float(v) for v in p[3:6]]),
                        radius_mm=float(p[6]) * 1000.0)
        elif surf.IsCone():
            p = surf.ConeParams
            info.update(kind="cone",
                        root_mm=[float(v) * 1000.0 for v in p[0:3]],
                        axis=_unit([float(v) for v in p[3:6]]),
                        radius_mm=float(p[6]) * 1000.0 if len(p) > 6 else None)
        elif surf.IsSphere():
            p = surf.SphereParams
            info.update(kind="sphere",
                        center_mm=[float(v) * 1000.0 for v in p[0:3]],
                        radius_mm=float(p[3]) * 1000.0 if len(p) > 3 else None)
        elif surf.IsTorus():
            p = surf.TorusParams
            info.update(kind="torus",
                        center_mm=[float(v) * 1000.0 for v in p[0:3]],
                        axis=_unit([float(v) for v in p[3:6]]),
                        major_radius_mm=float(p[6]) * 1000.0 if len(p) > 6 else None,
                        minor_radius_mm=float(p[7]) * 1000.0 if len(p) > 7 else None)
        else:
            info.update(kind="surface")
    except Exception as exc:
        info.update(kind="surface", params_error=str(exc))
    return info


def _curve_flag(curve, name):
    """ICurve 的 Is* 成员：早绑定 TLB 中可能是 bool 属性，也可能是方法。"""
    try:
        v = getattr(curve, name)
    except Exception:
        return False
    if isinstance(v, bool):
        return v
    try:
        return bool(v())
    except Exception:
        return bool(v)


def _edge_endpoint_mm(edge, prop):
    """边/草图图元端点坐标（毫米）。

    IEdge：GetStartVertex/GetEndVertex -> IVertex.GetPoint()；
    ISketchSegment：GetStartPoint2/GetEndPoint2 是返回 SketchPoint 对象的属性。
    """
    obj = sw_core._early(edge, "IEdge") if _has(edge, "GetStartVertex") else None
    if obj is not None:
        try:
            v = getattr(obj, prop)()
            # IVertex.GetPoint 在 v26 中是 tuple 属性而非方法
            p = sw_core.com_get(v, "GetPoint")
            if isinstance(p, (list, tuple)):
                return [float(x) * 1000.0 for x in p[:3]]
        except Exception:
            pass
    try:
        dyn = sw_core._dyn(edge)
        sp = sw_core.com_get(dyn, prop)  # SketchPoint 对象
        if sp is not None and hasattr(sp, "X"):
            return [float(sw_core.com_get(sp, "X")) * 1000.0,
                    float(sw_core.com_get(sp, "Y")) * 1000.0,
                    float(sw_core.com_get(sp, "Z") or 0.0) * 1000.0]
    except Exception:
        pass
    return None


def _has(obj, name):
    try:
        return hasattr(obj, name)
    except Exception:
        return False


def edge_info(edge):
    """返回 {type, radius_mm, length_mm, start/end, axis, center}；单位毫米。

    兼容 IEdge 与 ISketchSegment。SW2018 v26 实测要点：
      - ICurve.IsLine/IsCircle 是 bool 属性（不是方法），可能没有 IsArc；
      - LineParams 布局为 [起点 xyz, 单位方向 xyz]，不是 [起点, 终点]，
        因此端点一律改从 Vertex/SketchPoint 读取。
    """
    info = {}
    try:
        info["length_mm"] = float(sw_core.com_get(edge, "GetLength")) * 1000.0
    except Exception:
        pass
    curve = None
    try:
        curve = sw_core._early(edge.GetCurve(), "ICurve")
        is_line = _curve_flag(curve, "IsLine")
        is_circle = _curve_flag(curve, "IsCircle")
        is_arc = _curve_flag(curve, "IsArc")
        is_ellipse = _curve_flag(curve, "IsEllipse")
        if is_line:
            info.update(type="line")
        elif is_arc:
            try:
                p = curve.ArcParams  # [圆心 xyz, 轴 xyz, 半径, 起点 xyz, 终点 xyz]
                info.update(type="arc",
                            center_mm=[float(v) * 1000.0 for v in p[0:3]],
                            axis=_unit([float(v) for v in p[3:6]]),
                            radius_mm=float(p[6]) * 1000.0)
            except Exception:
                info.update(type="arc")
        elif is_circle:
            try:
                p = curve.CircleParams  # [圆心 xyz, 轴 xyz, 半径]
                info.update(type="circle",
                            center_mm=[float(v) * 1000.0 for v in p[0:3]],
                            axis=_unit([float(v) for v in p[3:6]]),
                            radius_mm=float(p[6]) * 1000.0)
            except Exception:
                info.update(type="circle")
        elif is_ellipse:
            info.update(type="ellipse")
        if "type" not in info:
            info.update(type="other")
    except Exception as exc:
        info.setdefault("params_error", str(exc))

    start = _edge_endpoint_mm(edge, "GetStartVertex") or \
        _edge_endpoint_mm(edge, "GetStartPoint2")
    end = _edge_endpoint_mm(edge, "GetEndVertex") or \
        _edge_endpoint_mm(edge, "GetEndPoint2")
    if start is not None:
        info["start_mm"] = start
    if end is not None:
        info["end_mm"] = end
    return info


def collect_faces(model, spec):
    """按 spec 过滤全部面，返回 [(IFace2, info)]（未过滤时返回全部）。"""
    spec = spec or {}
    kind = spec.get("kind")
    out = []
    for f in _faces(model):
        info = face_info(f)
        if kind and info.get("kind") != kind:
            continue
        if kind == "plane":
            if spec.get("normal") is not None and not _parallel_dir(
                    info["normal"], spec["normal"], directional=bool(spec.get("directional"))):
                continue
            # root_mm：给定点落在该平面上即匹配（SW 的 PlaneParams 根点是平面上任取的一点，
            # 无法预知，按点相等比较几乎总失败）
            if spec.get("root_mm") is not None and abs(_dot(
                    [a - b for a, b in zip(spec["root_mm"], info["root_mm"])],
                    info["normal"])) > spec.get("tol_mm", 0.01):
                continue
            if spec.get("min_area_mm2") is not None and info["area_mm2"] < spec["min_area_mm2"]:
                continue
        elif kind == "cylinder":
            if spec.get("radius_mm") is not None and abs(
                    info["radius_mm"] - spec["radius_mm"]) >= spec.get("tol_mm", 0.01):
                continue
            if spec.get("axis") is not None and not _parallel_dir(info["axis"], spec["axis"]):
                continue
            if spec.get("root_mm") is not None and not _near(info["root_mm"], spec["root_mm"]):
                continue
        elif kind == "sphere":
            if spec.get("radius_mm") is not None and abs(
                    info.get("radius_mm", 0) - spec["radius_mm"]) >= spec.get("tol_mm", 0.01):
                continue
            if spec.get("center_mm") is not None and not _near(
                    info.get("center_mm"), spec["center_mm"]):
                continue
        out.append((f, info))
    select = spec.get("select", "first")
    if select in ("largest", "smallest") and out:
        sign = -1 if select == "largest" else 1
        out.sort(key=lambda fi: sign * fi[1].get("area_mm2", 0.0))
    if out:
        idx = max(0, int(spec.get("index", 0)))
        out = [out[idx % len(out)]]
    return out


def _near_edge(info, point_mm, tol_mm):
    """点是否靠近边（端点或线段上的任意点 / 圆心距≈半径）。"""
    start, end = info.get("start_mm"), info.get("end_mm")
    if start and _near(start, point_mm, tol_mm):
        return True
    if end and _near(end, point_mm, tol_mm):
        return True
    if start and end and info.get("type") == "line":
        ax, ay = start[0], start[1]
        bx, by = end[0], end[1]
        px, py = point_mm[0], point_mm[1]
        dx, dy = bx - ax, by - ay
        ln2 = dx * dx + dy * dy
        if ln2 > 1e-18:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ln2))
            return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) <= tol_mm
    center, radius = info.get("center_mm"), info.get("radius_mm")
    if center and radius is not None:
        return abs(math.hypot(point_mm[0] - center[0], point_mm[1] - center[1])
                   - radius) <= tol_mm
    return False


def collect_edges(model, spec):
    spec = spec or {}
    etype = spec.get("type")
    out = []
    for e in _edges(model):
        info = edge_info(e)
        if etype and info.get("type") != etype:
            continue
        if spec.get("radius_mm") is not None and abs(
                info.get("radius_mm", 0) - spec["radius_mm"]) >= spec.get("tol_mm", 0.01):
            continue
        if spec.get("axis") is not None and not _parallel_dir(info.get("axis", [0, 0, 1]),
                                                              spec["axis"]):
            continue
        if spec.get("length_mm") is not None and abs(
                info.get("length_mm", 0) - spec["length_mm"]) >= spec.get("tol_mm", 0.01):
            continue
        if spec.get("near_mm") is not None:
            if not _near_edge(info, spec["near_mm"], spec.get("near_tol_mm", 0.2)):
                continue
        out.append((e, info))
    if out:
        idx = max(0, int(spec.get("index", 0)))
        out = [out[idx % len(out)]]
    return out


def collect_vertices(model, spec):
    spec = spec or {}
    out = []
    for v in _vertices(model):
        try:
            p = v.GetPoint()  # 米
            pt = [float(x) * 1000.0 for x in p]
        except Exception:
            continue
        if spec.get("near_mm") is not None and not _near(pt, spec["near_mm"],
                                                         spec.get("tol_mm", 0.2)):
            continue
        out.append((v, {"point_mm": pt}))
    if out:
        idx = max(0, int(spec.get("index", 0)))
        out = [out[idx % len(out)]]
    return out


def _select_data(model, mark):
    sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
    data = sm.CreateSelectData()
    data.Mark = int(mark)
    return data


def _select_entity(model, entity, append, mark):
    ent = sw_core._early(entity, "IEntity")
    data = _select_data(model, mark)
    try:
        return bool(ent.Select4(bool(append), data))
    except Exception:
        try:
            return bool(ent.Select2(bool(append), int(mark)))
        except Exception:
            pass
    dyn = sw_core._dyn(entity)
    try:
        return bool(dyn.Select4(bool(append), data))
    except Exception:
        try:
            return bool(dyn.Select2(bool(append), int(mark)))
        except Exception:
            return False


def select_face(model, spec, append=False, mark=0):
    """按 spec 选择面。成功返回 (IFace2, info)。"""
    for f, info in collect_faces(model, spec):
        if _select_entity(model, f, append, mark):
            return f, info
    raise SelectError(f"未找到可选择的平面/曲面: {spec}")


def select_edge(model, spec, append=False, mark=0):
    """按 spec 选择边。成功返回 (IEdge, info)。"""
    for e, info in collect_edges(model, spec):
        if _select_entity(model, e, append, mark):
            return e, info
    raise SelectError(f"未找到可选择的边: {spec}")


def select_vertex(model, spec, append=False, mark=0):
    """按 spec 选择顶点。成功返回 (IVertex, info)。"""
    for v, info in collect_vertices(model, spec):
        if _select_entity(model, v, append, mark):
            return v, info
    raise SelectError(f"未找到可选择的顶点: {spec}")


def select_entity(model, spec, append=False, mark=0):
    """通用实体选择入口：spec["kind"] ∈ plane/cylinder/sphere/cone/surface/edge/vertex。"""
    kind = (spec or {}).get("kind")
    if kind in ("plane", "cylinder", "sphere", "cone", "surface", "face"):
        return select_face(model, spec, append=append, mark=mark)
    if kind == "edge":
        return select_edge(model, spec, append=append, mark=mark)
    if kind == "vertex":
        return select_vertex(model, spec, append=append, mark=mark)
    raise SelectError(f"不支持的实体 spec kind: {kind}")


def select_feature(model, name=None, type_name=None, append=False, mark=0):
    """按名称或类型选择特征。"""
    for feat in sw_core.walk_features(model):
        if name and sw_core.feature_name(feat) != name:
            continue
        if type_name and sw_core.feature_type(feat) != type_name:
            continue
        try:
            if bool(feat.Select2(bool(append), int(mark))):
                return feat
        except Exception:
            continue
    raise SelectError(f"未找到特征 name={name} type={type_name}")


def find_feature(model, name=None, type_name=None, index=0):
    """按名称/类型查找特征对象（不选择）。"""
    hits = [f for f in sw_core.walk_features(model)
            if (not name or sw_core.feature_name(f) == name)
            and (not type_name or sw_core.feature_type(f) == type_name)]
    if not hits:
        raise SelectError(f"未找到特征 name={name} type={type_name}")
    return hits[min(max(0, index), len(hits) - 1)]


def selected_count(model):
    try:
        return int(model.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:
        return -1
