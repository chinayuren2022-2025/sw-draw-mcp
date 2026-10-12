"""sw_asm_ref.py — 装配体组件级引用 + 闭环配合（SW2018 v26 实测，见 probe_asm.py）

核心思路：零件阶段给关键面命名（sw_topo.name_entity），装配阶段按
"组件 + 面名" 选实体（IComponent2.GetCorrespondingEntity 映射到装配上下文），
配合后读回约束状态 / 剩余自由度 / 配合错误，冲突自动回滚。

引用 ref（dict，任选其一；component 为组件 Name2，如 "pin-1"，
也可只写零件名 "pin"，唯一实例时自动匹配）：
    {"component": "pin-1", "face": "PIN_CYL"}           零件中已命名的面（推荐）
    {"component": "pin-1", "edge": "E1"} / {"vertex": "V1"}
    {"component": "pin-1", "persist_id": "<base64>"}    asm_component_faces 返回的零件级持久 ID
    {"component": "pin-1", "spec": {...}}               sw_sel 几何过滤（零件局部坐标，毫米）
    {"component": "pin-1", "index": 3}                  零件面序号
    {"component": "pin-1", "plane": "front"}            组件基准面 front/top/right 或自定义名
    {"component": "pin-1", "axis": "基准轴1"} / {"point": "原点"}
    {"plane": "front"}                                  装配体自身基准面
    {"ray": {"origin_mm": [...], "direction": [...]}, "kind": "face"}   装配坐标射线拾取

SW2018 v26 实测坑：
    - AddComponent4 的 x/y/z 定位的是组件包围盒中心，不是零件原点；
      要按原点定位用 insert_component(place="origin")。
    - IComponent2.GetBodies3 的面几何是零件局部坐标，需乘 Transform2 才是装配坐标。
    - GetConstrainedStatus：2=欠定义（剩余自由度见 GetRemainingDOFs）。
"""
import math

import sw_assembly_full as af
import sw_core
import sw_sel
import sw_topo

_PLANES = {
    "front": ["前视基准面", "Front Plane", "前视"],
    "top": ["上视基准面", "Top Plane", "上视"],
    "right": ["右视基准面", "Right Plane", "右视"],
}
_ORIGIN = ["原点", "Origin", "Point1@Origin"]
_MATE_NAME_BY_CODE = {v: k for k, v in af.MATE_TYPES.items()}


class AsmRefError(RuntimeError):
    """装配引用无法解析。"""


# ---------------------------------------------------------------------------
# 变换
# ---------------------------------------------------------------------------

def xform(comp):
    """组件变换：rotation 行向量为组件 X/Y/Z 轴在装配中的方向，translation 为原点（mm）。"""
    t = sw_core._early(sw_core.com_get(comp, "Transform2"), "IMathTransform")
    a = [float(v) for v in t.ArrayData]
    return {"rotation": [a[0:3], a[3:6], a[6:9]],
            "translation_mm": [a[9] * 1000.0, a[10] * 1000.0, a[11] * 1000.0],
            "scale": a[12]}


def apply_point(xf, p_mm):
    """零件局部点（mm）-> 装配坐标（mm）。SW 采用行向量约定：p' = p·R·s + t。"""
    r, s, t = xf["rotation"], xf["scale"], xf["translation_mm"]
    return [s * sum(p_mm[i] * r[i][j] for i in range(3)) + t[j] for j in range(3)]


def apply_dir(xf, v):
    r = xf["rotation"]
    return [sum(v[i] * r[i][j] for i in range(3)) for j in range(3)]


def _to_asm_coords(rec, xf):
    """把 sw_sel 几何记录中的点/方向字段换算到装配坐标（原记录保留为 local_*）。"""
    out = dict(rec)
    for key in ("root_mm", "center_mm", "start_mm", "end_mm"):
        if isinstance(rec.get(key), list):
            out[key] = [round(v, 4) for v in apply_point(xf, rec[key])]
    for key in ("normal", "axis"):
        if isinstance(rec.get(key), list):
            out[key] = [round(v, 6) for v in apply_dir(xf, rec[key])]
    if isinstance(rec.get("box_mm"), list) and len(rec["box_mm"]) == 6:
        b = rec["box_mm"]
        corners = [apply_point(xf, [x, y, z]) for x in (b[0], b[3])
                   for y in (b[1], b[4]) for z in (b[2], b[5])]
        out["box_mm"] = [round(min(c[i] for c in corners), 4) for i in range(3)] + \
                        [round(max(c[i] for c in corners), 4) for i in range(3)]
    return out


# ---------------------------------------------------------------------------
# 组件
# ---------------------------------------------------------------------------

def components(asm, top_level=True):
    return af.component_list(asm, top_level=top_level)


def find_comp(asm, name):
    """按 Name2 精确匹配；否则按零件名（"pin" -> "pin-1"）唯一匹配。"""
    comps = components(asm, top_level=False)
    names = [af._comp_name(c) for c in comps]
    for c, n in zip(comps, names):
        if n == name or n.split("/")[-1] == name:
            return c
    hits = [c for c, n in zip(comps, names)
            if n.split("/")[-1].rsplit("-", 1)[0] == name]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise AsmRefError(f"组件名 {name!r} 有多个实例，请写全名: "
                          f"{[af._comp_name(c) for c in hits]}")
    raise AsmRefError(f"装配体中没有组件 {name!r}；现有: {names}")


def comp_model(comp):
    """组件对应的零件/子装配文档；轻化组件先还原。"""
    doc = comp.GetModelDoc2()
    if doc is None:
        try:
            af.set_component_suppression(comp, "resolved")
        except Exception:
            pass
        doc = comp.GetModelDoc2()
    if doc is None:
        raise AsmRefError(f"组件 {af._comp_name(comp)} 的模型未加载（被压缩？）")
    return sw_core._early(doc, "IModelDoc2")


def constrained_status(comp):
    try:
        code = int(comp.GetConstrainedStatus())
    except Exception:
        return None
    return af.CONSTRAINED_STATUS.get(code, f"code_{code}")


def remaining_dofs(comp):
    """剩余自由度：{count, rotation_axes[{point_mm, direction}], translation_dirs[]}。

    固定组件或完全定义时 count=0。读取失败返回 None。
    """
    try:
        r = comp.GetRemainingDOFs()
    except Exception:
        return None
    if not isinstance(r, tuple):
        return {"count": int(r)}
    vals = list(r)
    out = {"count": int(vals[0]), "rotation_axes": [], "translation_dirs": []}

    def _arr(obj):
        try:
            return [float(v) for v in sw_core.com_get(obj, "ArrayData")][:3]
        except Exception:
            return None

    outs = vals[1:]
    # 输出参数顺序：Rp1_st, Rp1, Rd1_st, Rd1, Rp2_st, Rp2, Rd2_st, Rd2, Td1_st, Td1, Td2_st, Td2
    for k in (0, 4):
        if len(outs) > k + 3 and outs[k + 2]:
            p, d = _arr(outs[k + 1]), _arr(outs[k + 3])
            if d:
                out["rotation_axes"].append({
                    "point_mm": [round(v * 1000, 4) for v in p] if p else None,
                    "direction": [round(v, 6) for v in d]})
    for k in (8, 10):
        if len(outs) > k + 1 and outs[k]:
            d = _arr(outs[k + 1])
            if d:
                out["translation_dirs"].append([round(v, 6) for v in d])
    # SW2018 实测：返回值不是自由度个数（同心后返回 0 却带 1 转 1 移），按输出数据计数
    out["count"] = len(out["rotation_axes"]) + len(out["translation_dirs"])
    return out


def comp_info(asm, comp, with_dofs=True):
    name = af._comp_name(comp)
    info = {"name": name}
    try:
        info["path"] = str(comp.GetPathName())
    except Exception:
        pass
    try:
        info["fixed"] = af.is_fixed(comp)
    except Exception:
        pass
    try:
        info["suppressed"] = bool(comp.IsSuppressed())
    except Exception:
        pass
    info["status"] = constrained_status(comp)
    if with_dofs and not info.get("fixed"):
        info["remaining_dofs"] = remaining_dofs(comp)
    try:
        xf = xform(comp)
        info["origin_mm"] = [round(v, 4) for v in xf["translation_mm"]]
        info["rotation"] = [[round(v, 6) for v in row] for row in xf["rotation"]]
    except Exception:
        pass
    try:
        box = comp.GetBox(False, False)
        info["bbox_mm"] = [round(float(v) * 1000.0, 4) for v in box]
    except Exception:
        pass
    try:
        info["mate_count"] = len(comp.GetMates() or [])
    except Exception:
        pass
    return info


def assembly_components(asm, top_level=True, with_dofs=True):
    return [comp_info(asm, c, with_dofs) for c in components(asm, top_level)]


def comp_faces(asm, comp_name, kind=None, limit=200, include_edges=False):
    """组件拓扑：零件局部 + 装配坐标两套几何；persist_id 是零件级 ID，可直接用于 ref。"""
    comp = find_comp(asm, comp_name)
    model = comp_model(comp)
    xf = xform(comp)
    include = ("faces", "edges") if include_edges else ("faces",)
    topo = sw_topo.topology(model, include=include, kind=kind, limit=limit)
    for key in ("faces", "edges"):
        if key in topo:
            topo[key] = [_to_asm_coords(r, xf) for r in topo[key]]
    topo["component"] = af._comp_name(comp)
    topo["coords"] = "装配坐标（零件局部坐标请用 part_topology 打开零件查看）"
    return topo


# ---------------------------------------------------------------------------
# 引用解析
# ---------------------------------------------------------------------------

def _byid_string(comp):
    try:
        return str(comp.GetSelectByIDString())
    except Exception:
        return af._comp_name(comp)


def _asm_title(asm):
    return sw_core.model_title(asm).rsplit(".", 1)[0]


def _plane_candidates(name):
    return _PLANES.get(str(name).strip().lower().replace(" plane", ""), [str(name)])


def resolve(asm, ref):
    """ref -> ("entity", obj, desc) 或 ("byid", [(name, type), ...], desc)。"""
    if not isinstance(ref, dict):
        raise AsmRefError(f"引用必须是 dict，收到 {ref!r}")
    comp_name = ref.get("component")
    if not comp_name:
        if ref.get("plane"):
            cands = [(c, "PLANE") for c in _plane_candidates(ref["plane"])]
            return "byid", cands, f"装配体基准面 {ref['plane']}"
        if ref.get("axis"):
            return "byid", [(ref["axis"], "AXIS")], f"装配体基准轴 {ref['axis']}"
        if ref.get("ray"):
            r = ref["ray"]
            kind = ref.get("kind", "face")
            ent = sw_topo.ray_pick(asm, r["origin_mm"], r["direction"],
                                   r.get("radius_mm", 0.5), kind)
            return "entity", ent, f"射线拾取 {r}"
        if ref.get("asm_persist_id"):
            return "entity", sw_topo.from_persist_id(asm, ref["asm_persist_id"]), "装配级持久 ID"
        raise AsmRefError(f"引用缺少 component：{ref}")

    comp = find_comp(asm, comp_name)
    cname = af._comp_name(comp)
    sid = _byid_string(comp)
    if ref.get("plane"):
        cands = [(f"{p}@{sid}", "PLANE") for p in _plane_candidates(ref["plane"])]
        return "byid", cands, f"{cname} 基准面 {ref['plane']}"
    if ref.get("axis"):
        return "byid", [(f"{ref['axis']}@{sid}", "AXIS")], f"{cname} 基准轴 {ref['axis']}"
    if ref.get("point"):
        pts = _ORIGIN if str(ref["point"]).lower() in ("origin", "原点") else [ref["point"]]
        return "byid", [(f"{p}@{sid}", "EXTSKETCHPOINT") for p in pts] + \
            [(f"{p}@{sid}", "DATUMPOINT") for p in pts], f"{cname} 点 {ref['point']}"

    model = comp_model(comp)
    if ref.get("face") or ref.get("edge") or ref.get("vertex"):
        kind = "face" if ref.get("face") else "edge" if ref.get("edge") else "vertex"
        part_ent, _ = sw_topo.find_named(model, ref[kind], kind)
        desc = f"{cname} {kind} {ref[kind]}"
    else:
        sub = {k: ref[k] for k in ("persist_id", "spec", "index", "kind") if k in ref}
        if not sub:
            raise AsmRefError(f"引用 {ref} 缺少 face/edge/vertex/plane/axis/point/"
                              "persist_id/spec/index 之一")
        part_ent, _ = sw_topo.resolve(model, sub)
        desc = f"{cname} {sub}"
    ent = comp.GetCorrespondingEntity(part_ent)
    if ent is None:
        raise AsmRefError(f"{desc}：GetCorrespondingEntity 返回 None（组件被压缩/轻化？）")
    return "entity", ent, desc


def select_ref(asm, ref, append=False, mark=0):
    """解析并选中 ref；失败抛 AsmRefError。"""
    how, obj, desc = resolve(asm, ref)
    if how == "byid":
        for name, typ in obj:
            if sw_core.select_by_id(asm, name, typ, 0, 0, 0, append, mark):
                return True
        raise AsmRefError(f"选择失败：{desc}（尝试了 {[n for n, _ in obj]}）")
    if sw_topo.select(asm, obj, append=append, mark=mark):
        return True
    raise AsmRefError(f"选择失败：{desc}")


# ---------------------------------------------------------------------------
# 配合
# ---------------------------------------------------------------------------

def _mate_feature(asm, name):
    for sub in af._mate_group_feats(asm):
        if sw_core.feature_name(sub) == name:
            return sub
    return None


def _mate_detail(feat):
    rec = {"name": sw_core.feature_name(feat)}
    err, warn = sw_core.feature_error_codes(feat)
    rec["error_code"], rec["warning_code"] = int(err), int(warn)
    try:
        rec["suppressed"] = bool(feat.IsSuppressed())
    except Exception:
        pass
    try:
        m = sw_core._early(feat.GetSpecificFeature2(), "IMate2")
        code = int(m.Type)
        rec["type"] = _MATE_NAME_BY_CODE.get(code, f"code_{code}")
        rec["align"] = {0: "aligned", 1: "anti_aligned", 2: "closest"}.get(int(m.Alignment))
        try:
            rec["flipped"] = bool(m.Flipped)
        except Exception:
            pass
        ents = []
        for i in range(int(m.GetMateEntityCount())):
            me = sw_core._early(m.MateEntity(i), "IMateEntity2")
            ent = {"component": af._comp_name(me.ReferenceComponent) or None}
            try:
                # swSelectType_e：1 边 2 面 3 顶点 4 基准面 5 基准轴 6 基准点
                code_t = int(me.ReferenceType2)
                ent["ref_type"] = {1: "edge", 2: "face", 3: "vertex", 4: "plane",
                                   5: "axis", 6: "point", 11: "sketch_point",
                                   25: "sketch_point"}.get(code_t, f"type_{code_t}")
            except Exception:
                pass
            ents.append(ent)
        rec["entities"] = ents
        try:
            dd = m.DisplayDimension2(0)
            if dd is not None:
                dim = sw_core._early(sw_core._early(dd, "IDisplayDimension").GetDimension2(0),
                                     "IDimension")
                v = float(dim.SystemValue)
                rec["value"] = round(math.degrees(v), 4) if rec.get("type") == "angle" \
                    else round(v * 1000.0, 4)
        except Exception:
            pass
    except Exception as exc:
        rec["detail_error"] = str(exc)
    return rec


def mates(asm):
    """全部配合的详细信息：类型、对齐、翻转、两端组件、数值、错误码。"""
    return [_mate_detail(f) for f in af._mate_group_feats(asm)]


def _comp_names_in(ref):
    return [ref.get("component")] if isinstance(ref, dict) and ref.get("component") else []


def mate(asm, a, b, mate_type="coincident", align="closest", flip=False,
         distance_mm=0.0, angle_deg=0.0, extra=None, rollback_on_error=True, **kw):
    """闭环配合：选择 a/b（及 extra）-> AddMate5 -> 重建 -> 读回状态。

    extra: [{"ref": {...}, "mark": 2}]，用于对称面等第三选择。
    rollback_on_error: 配合报错（过定义/冲突）时自动删除，保持装配体干净。
    返回 {ok, mate, error, mate_detail, components:[{name,status,remaining_dofs,origin_mm}]}。
    """
    if isinstance(mate_type, str):
        if mate_type not in af.MATE_TYPES:
            raise AsmRefError(f"不支持的配合类型 {mate_type!r}，可选 {sorted(af.MATE_TYPES)}")
        type_code = af.MATE_TYPES[mate_type]
    else:
        type_code = int(mate_type)
    align_code = af.ALIGN.get(align, align) if isinstance(align, str) else int(align)
    if not isinstance(align_code, int):
        raise AsmRefError(f"align 必须是 aligned/anti/closest，收到 {align!r}")

    asm.ClearSelection2(True)
    select_ref(asm, a, append=False, mark=1)
    select_ref(asm, b, append=True, mark=1)
    for item in extra or []:
        select_ref(asm, item["ref"], append=True, mark=int(item.get("mark", 2)))

    before = {f["name"] for f in af.list_mates(asm)}
    result = {"ok": False}
    try:
        feat, code = af.add_mate_selected(
            asm, type_code, align_code, flip=flip, distance_m=float(distance_mm) / 1000.0,
            angle_deg=float(angle_deg), desc=f"mate({mate_type})",
            **{k: kw[k] for k in ("dist_upper_m", "dist_lower_m", "angle_upper_deg",
                                  "angle_lower_deg", "gear_num", "gear_den",
                                  "lock_rotation", "width_option") if k in kw})
    except Exception as exc:
        asm.ClearSelection2(True)
        result["error"] = str(exc)
        return result
    sw_core.rebuild(asm)
    name = str(getattr(feat, "Name", "") or "")
    new_names = [f["name"] for f in af.list_mates(asm) if f["name"] not in before]
    if name not in new_names and new_names:
        name = new_names[0]
    mf = _mate_feature(asm, name)
    detail = _mate_detail(mf) if mf is not None else {"name": name}
    result.update(mate=name, add_mate_code=code,
                  add_mate_message=af.ADD_MATE_ERRORS.get(code, "未知"),
                  mate_detail=detail)
    failed = code != 1 or detail.get("error_code", 0) not in (0, -1)
    if failed:
        result["error"] = (f"配合有错误：AddMate 返回 {code}（{af.ADD_MATE_ERRORS.get(code)}）,"
                           f" 特征错误码 {detail.get('error_code')}")
        if rollback_on_error and mf is not None:
            try:
                af.delete_mate(asm, name)
                sw_core.rebuild(asm)
                result["rolled_back"] = True
            except Exception as exc:
                result["rollback_error"] = str(exc)
    else:
        result["ok"] = True
    names = _comp_names_in(a) + _comp_names_in(b)
    result["components"] = []
    for n in dict.fromkeys(names):
        try:
            info = comp_info(asm, find_comp(asm, n))
            result["components"].append({k: info.get(k) for k in
                                         ("name", "fixed", "status", "remaining_dofs",
                                          "origin_mm")})
        except Exception as exc:
            result["components"].append({"name": n, "error": str(exc)})
    return result


def edit_mate(asm, name, distance_mm=None, angle_deg=None, flip=None):
    """修改配合数值 / 翻转后重建，返回新的配合详情。"""
    feat = _mate_feature(asm, name)
    if feat is None:
        raise AsmRefError(f"未找到配合 {name!r}")
    m = sw_core._early(feat.GetSpecificFeature2(), "IMate2")
    if distance_mm is not None or angle_deg is not None:
        dd = m.DisplayDimension2(0)
        if dd is None:
            raise AsmRefError(f"配合 {name} 没有可编辑的尺寸（不是距离/角度配合）")
        dim = sw_core._early(sw_core._early(dd, "IDisplayDimension").GetDimension2(0),
                             "IDimension")
        value = float(distance_mm) / 1000.0 if distance_mm is not None \
            else math.radians(float(angle_deg))
        sw_core.com_set(dim, "SystemValue", value)
    if flip is not None:
        sw_core.com_set(m, "Flipped", bool(flip))
    sw_core.rebuild(asm)
    return _mate_detail(_mate_feature(asm, name))


# ---------------------------------------------------------------------------
# 组件放置 / 检查
# ---------------------------------------------------------------------------

def insert_component(asm, path, at_mm=(0.0, 0.0, 0.0), place="origin", fix=None):
    """插入组件。place="origin"：零件原点落在 at_mm；"bbox_center"：SW 原生语义。"""
    at = [float(v) for v in at_mm]
    comp = af.insert_component_full(asm, path, x=at[0] / 1000.0, y=at[1] / 1000.0,
                                    z=at[2] / 1000.0)
    if place == "origin":
        cur = xform(comp)["translation_mm"]
        d = [(at[i] - cur[i]) / 1000.0 for i in range(3)]
        if any(abs(v) > 1e-9 for v in d):
            af.move_component(asm, comp, *d)
    if fix is True:
        af.fix_component(asm, comp)
    elif fix is False and af.is_fixed(comp):
        af.float_component(asm, comp)
    return comp_info(asm, comp)


def move_component(asm, comp_name, delta_mm=None, to_mm=None):
    """平移组件（受配合约束时由求解器决定最终位置）。to_mm 指定原点目标位置。"""
    comp = find_comp(asm, comp_name)
    cur = xform(comp)["translation_mm"]
    if to_mm is not None:
        delta_mm = [float(to_mm[i]) - cur[i] for i in range(3)]
    d = [float(v) / 1000.0 for v in (delta_mm or (0, 0, 0))]
    af.move_component(asm, comp, *d)
    return comp_info(asm, comp)


def interference(asm, include_coincident=False):
    """精确干涉检查（IInterferenceDetectionMgr）：[{components, volume_mm3}]。"""
    adoc = af._as_asm(asm)
    idm = sw_core._early(adoc.InterferenceDetectionManager, "IInterferenceDetectionMgr")
    try:
        try:
            idm.TreatCoincidenceAsInterference = bool(include_coincident)
        except Exception:
            pass
        out = []
        for it in idm.GetInterferences() or []:
            it = sw_core._early(it, "IInterference")
            rec = {}
            try:
                rec["components"] = [af._comp_name(c) for c in (it.Components or [])]
            except Exception:
                pass
            try:
                rec["volume_mm3"] = round(float(it.Volume) * 1e9, 4)
            except Exception:
                pass
            out.append(rec)
        return out
    finally:
        try:
            idm.Done()
        except Exception:
            pass


def check(asm, with_interference=True):
    """装配闭环检查：重建 + 配合错误 + 欠/过定义组件 + 干涉。"""
    rebuild_ok = True
    try:
        sw_core.rebuild(asm)
    except Exception:
        rebuild_ok = False
    all_mates = mates(asm)
    comps = assembly_components(asm, top_level=True)
    report = {
        "rebuild_ok": rebuild_ok,
        "mate_count": len(all_mates),
        "mate_errors": [m for m in all_mates
                        if m.get("error_code") not in (0, -1, None)
                        or m.get("warning_code") not in (0, -1, None)],
        "components": comps,
        "floating": [c["name"] for c in comps
                     if not c.get("fixed") and c.get("status") == "under_constrained"],
        "over_defined": [c["name"] for c in comps
                         if c.get("status") in ("over_constrained", "no_solution",
                                                "invalid_solution")],
        "whats_wrong": sw_core.get_whats_wrong(asm),
    }
    if with_interference:
        try:
            report["interference"] = interference(asm)
        except Exception as exc:
            report["interference_error"] = str(exc)
    report["ok"] = rebuild_ok and not report["mate_errors"] and not report["over_defined"] \
        and not report.get("interference")
    return report
