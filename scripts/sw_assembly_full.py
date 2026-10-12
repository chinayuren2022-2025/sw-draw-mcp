# -*- coding: utf-8 -*-
"""sw_assembly_full.py — SolidWorks 2018（TLB v26）装配体能力补全层。

目标环境：Windows + pywin32 311 + SolidWorks 2018。当前开发环境为 Linux，
只能 py_compile，无法真正调用 COM；因此本模块与 sw_features 一致：
    - 多签名回退（sw_core.call_sigs / 本模块 _invoke_any）
    - 多方法名回退（AddMate3/4/5、AddComponent4/5、InsertMirrorFeature/2 等）
    - 返回值统一包装 sw_core._early(..., "IFeature" / "IComponent2")
    - 单位：API 参数用米；毫米输入参数名带 _mm 并在内部转换
    - 错误信息中文并带函数名/关键参数
    - 库代码不 print

选择规则（SW2018 v26 已实测）：
    - 零件实体用 sw_sel
    - 种子特征 / 零部件用 SelectByID2(name, "BODYFEATURE", 0,0,0, append, mark)
    - 阵列方向实体 mark=1/2
    - 镜像基准面中英文候选：Top Plane/上视基准面/上视 等
"""
import math
import os

import pythoncom
import win32com.client
from win32com.client import VARIANT

import sw_assembly
import sw_check
import sw_core
import sw_features as _swf
import sw_sel

# ---------------------------------------------------------------------------
# 常量映射（来源：SW2018 API swconst；0/1/5/6 已实测，其余待实测）
# ---------------------------------------------------------------------------

# swMateType_e：配合类型。数值取自 SW2018 自带 SolidWorks.Interop.swconst.dll
# 反射结果（旧表 9 以后整体错位，如 hinge=16 实为 LOCK）。
MATE_TYPES = {
    "coincident": 0,       # 重合（SW2018 v26 已实测）
    "concentric": 1,       # 同轴心（SW2018 v26 已实测）
    "perpendicular": 2,    # 垂直
    "parallel": 3,         # 平行
    "tangent": 4,          # 相切
    "distance": 5,         # 距离（SW2018 v26 已实测）
    "angle": 6,            # 角度（SW2018 v26 已实测）
    "symmetric": 8,        # 对称（需第三个选择：对称面，mark=1）
    "cam_follower": 9,     # 凸轮推杆
    "gear": 10,            # 齿轮
    "width": 11,           # 宽度
    "lock_to_sketch": 12,  # 锁定到草图
    "rack_pinion": 13,     # 齿条小齿轮
    "path": 15,            # 路径
    "lock": 16,            # 锁定
    "screw": 17,           # 螺旋
    "linear_coupler": 18,  # 线性/线性耦合器
    "universal_joint": 19, # 万向节
    "coordinate": 20,      # 坐标系
    "slot": 21,            # 槽口
    "hinge": 22,           # 铰链
    "slider": 23,          # 滑块
    "profile_center": 24,  # 轮廓中心
    "magnetic": 25,        # 磁力
}

# swAddMateError_e：AddMate 返回的错误码
ADD_MATE_ERRORS = {
    0: "未知错误", 1: "无错误", 2: "配合类型与所选实体不匹配",
    3: "对齐方式不正确", 4: "所选实体不正确（类型/数量不对）",
    5: "装配体过定义（与已有配合冲突）", 6: "齿轮比不正确",
}

# swConstrainedStatus_e：零部件约束状态
CONSTRAINED_STATUS = {
    1: "unknown", 2: "under_constrained", 3: "fully_constrained",
    4: "over_constrained", 5: "no_solution", 6: "invalid_solution",
    7: "autosolve_off",
}

# swMateAlign_e：配合对齐
ALIGN = {"aligned": 0, "anti": 1, "closest": 2}

# swAddComponentConfigOptions_e：AddComponent5 配置选项（待 SW2018 实测）
_CONFIG_OPTION = {
    "use_existing": 0,               # 使用现有配置
    "new_config": 1,                 # 新建配置
    "new_config_with_reference": 2,  # 新建配置并引用参考模型
}

# swComponentSuppressionState_e：零部件压缩状态
_COMP_SUPPRESSION = {
    "suppressed": 0,
    "lightweight": 1,
    "resolved": 2,
}

# swEndConditions_e：终止条件（与 sw_features 保持一致）
_END_COND = {
    "blind": 0,
    "through_all": 1,
    "through_next": 2,
    "offset_from_surface": 5,
    "midplane": 6,
    "through_all_both": 9,
    "up_to_vertex": 10,
    "up_to_surface": 10,
    "up_to_selection": 10,
}

# 镜像基准面中英文候选（中文 UI 下英文名不存在）
_PLANE_CANDIDATES = {
    "front": ["Front Plane", "前视基准面", "前视"],
    "top": ["Top Plane", "上视基准面", "上视"],
    "right": ["Right Plane", "右视基准面", "右视"],
}


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _as_asm(asm):
    """包装为早绑定 IAssemblyDoc。"""
    return sw_core._early(asm, "IAssemblyDoc")


def _dyn(obj):
    """取后期绑定视图，用于 VARIANT 参数调用。"""
    return sw_core._dyn(obj)


def _empty():
    """SelectByID2 的 Callout 空参数。"""
    return sw_core._empty_callout()


def _comp_name(comp):
    """读取零部件 Name2（属性/方法二义兼容）。"""
    try:
        return str(sw_core.com_get(comp, "Name2"))
    except Exception:
        return ""


def _invoke_any(obj, method, sigs, desc):
    """按候选签名依次调用方法，返回首次未抛错的结果（允许 None，表示 void 成功）。

    与 sw_core.call_sigs 的区别：本函数允许方法返回 None 且视为调用成功。
    """
    last = None
    for args in sigs:
        try:
            return getattr(obj, method)(*args)
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}") from last


def _feat_void(fm, method, sigs, desc, model):
    """调用可能返回 void 的特征方法，随后从特征树找最新特征包装返回。"""
    last = None
    for args in sigs:
        try:
            ret = getattr(fm, method)(*args)
            if ret is not None:
                return sw_core._early(ret, "IFeature")
            feat = _swf._newest_feature(model)
            if feat is not None:
                return feat
            last = RuntimeError(f"{desc}: {method} 调用后未在特征树找到新特征")
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}") from last


def _get_sw():
    """附着运行中的 SolidWorks，失败则启动新实例（不 print）。"""
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
    except Exception:
        sw = win32com.client.Dispatch("SldWorks.Application")
        try:
            sw.Visible = True
        except Exception:
            pass
    sw_core.ensure_tlb(sw)
    return sw_core._early(sw, "ISldWorks")


def _select_entity_obj(model, entity, append=False, mark=0):
    """选择 COM 实体对象（IEntity/IFeature/IComponent2 均可）。"""
    return _swf._select_entity_obj(model, entity, append=append, mark=mark)


def _select_component(asm, comp, desc, append=False, mark=0):
    """按 SW2018 实测方式选择零部件：SelectByID2(name, "BODYFEATURE", ...)。

    comp 可为 IComponent2 或名称 str；失败回退 COMPONENT 类型与对象 Select4/Select2。
    """
    if isinstance(comp, str):
        name = comp
    else:
        name = _comp_name(comp)
    if name:
        if sw_core.select_by_id(asm, name, "BODYFEATURE", 0, 0, 0, append, mark):
            return True
        if sw_core.select_by_id(asm, name, "COMPONENT", 0, 0, 0, append, mark):
            return True
    if not isinstance(comp, str) and _select_entity_obj(asm, comp, append=append, mark=mark):
        return True
    raise RuntimeError(f"{desc}: 无法选择零部件 {name or comp!r}")


def _select_seed_component(asm, seed_comp, desc):
    """选择阵列种子零部件：BODYFEATURE + mark=4（SW2018 实测）。"""
    asm.ClearSelection2(True)
    return _select_component(asm, seed_comp, desc, append=False, mark=4)


def _select_asm_direction(asm, direction_spec, desc, mark):
    """选择装配体阵列方向实体。

    dict 且含 name 时走 SelectByID2；dict 且含 kind 时先试 sw_sel（零件实体），
    失败给出中文提示；对象走 Select4/Select2。方向实体 mark=1/2。
    """
    if direction_spec is None:
        raise RuntimeError(f"{desc}: 缺少方向实体")
    if isinstance(direction_spec, dict):
        name = direction_spec.get("name")
        if name:
            type_name = str(direction_spec.get("type", "EDGE"))
            if sw_core.select_by_id(asm, str(name), type_name, 0, 0, 0, True, mark):
                return True
            raise RuntimeError(f"{desc}: SelectByID2 无法选择方向 {name!r} (type={type_name})")
        if "kind" in direction_spec:
            try:
                return sw_sel.select_entity(asm, direction_spec, append=True, mark=mark)
            except Exception as exc:
                raise RuntimeError(
                    f"{desc}: 装配体中按几何 spec 选择方向实体失败"
                    f"（仅支持 IEntity 对象或含 name/type 的 dict）: {exc}") from exc
    if isinstance(direction_spec, str):
        if sw_core.select_by_id(asm, direction_spec, "EDGE", 0, 0, 0, True, mark):
            return True
        raise RuntimeError(f"{desc}: SelectByID2 无法选择方向 {direction_spec!r}")
    if _select_entity_obj(asm, direction_spec, append=True, mark=mark):
        return True
    raise RuntimeError(f"{desc}: 无法选择方向实体 {direction_spec!r}")


def _select_plane(asm, plane_spec=None, plane_name=None, desc="选择镜像基准面"):
    """选择基准面：plane_name 中英文候选；plane_spec 可为对象或含 name/type 的 dict。"""
    if plane_name:
        key = str(plane_name).strip().lower().replace(" plane", "")
        cands = _PLANE_CANDIDATES.get(key, [str(plane_name)])
        for cand in cands:
            if sw_core.select_by_id(asm, cand, "PLANE"):
                return True
        raise RuntimeError(f"{desc}: 无法选择基准面 {plane_name!r}（已尝试中英文候选）")
    if isinstance(plane_spec, dict):
        name = plane_spec.get("name")
        if name:
            if sw_core.select_by_id(asm, str(name), str(plane_spec.get("type", "PLANE"))):
                return True
            raise RuntimeError(f"{desc}: SelectByID2 无法选择基准面 {name!r}")
        if "kind" in plane_spec:
            try:
                return sw_sel.select_entity(asm, plane_spec)
            except Exception as exc:
                raise RuntimeError(
                    f"{desc}: 装配体中按几何 spec 选择基准面失败"
                    f"（仅支持 IEntity 对象或含 name/type 的 dict）: {exc}") from exc
    if plane_spec is not None:
        if _select_entity_obj(asm, plane_spec):
            return True
        raise RuntimeError(f"{desc}: 无法选择基准面 {plane_spec!r}")
    raise RuntimeError(f"{desc}: 必须提供 plane_spec 或 plane_name")


def _select_named_entity(asm, spec, desc, append=False, mark=0, default_type="FACE"):
    """装配体中按 spec 选择实体：对象 / name+type dict / 字符串名。"""
    if spec is None:
        return False
    if isinstance(spec, dict) and spec.get("component"):
        import sw_asm_ref  # 组件级引用：{"component": "pin-1", "face": "HOLE"} 等
        return sw_asm_ref.select_ref(asm, spec, append=append, mark=mark)
    if isinstance(spec, dict):
        name = spec.get("name")
        if name:
            type_name = str(spec.get("type", default_type))
            if sw_core.select_by_id(asm, str(name), type_name, 0, 0, 0, append, mark):
                return True
            raise RuntimeError(f"{desc}: SelectByID2 无法选择 {name!r} (type={type_name})")
        if "kind" in spec:
            try:
                return sw_sel.select_entity(asm, spec, append=append, mark=mark)
            except Exception as exc:
                raise RuntimeError(
                    f"{desc}: 装配体中按几何 spec 选择实体失败"
                    f"（仅支持 IEntity 对象或含 name/type 的 dict）: {exc}") from exc
    if isinstance(spec, str):
        if sw_core.select_by_id(asm, spec, default_type, 0, 0, 0, append, mark):
            return True
        raise RuntimeError(f"{desc}: SelectByID2 无法选择 {spec!r}")
    if _select_entity_obj(asm, spec, append=append, mark=mark):
        return True
    raise RuntimeError(f"{desc}: 无法选择实体 {spec!r}")


def _find_component_by_name(asm, name):
    """按 Name2 查找零部件（找不到返回 None）。"""
    if isinstance(name, str):
        for c in component_list(asm, top_level=False):
            if _comp_name(c) == name:
                return c
    return None


def _selected_entity_objects(model, max_count):
    """从 SelectionManager 读回已选实体对象（InsertMateReference 等需要对象参数）。"""
    objs = []
    try:
        sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
    except Exception:
        return objs
    for i in range(1, max_count + 1):
        obj = None
        for method in ("GetSelectedObject6", "GetSelectedObject5", "GetSelectedObject3"):
            try:
                obj = getattr(sm, method)(i, -1)
                if obj is not None:
                    break
            except Exception:
                obj = None
        if obj is not None:
            objs.append(obj)
    return objs


def _norm_list(items):
    return _swf._norm_list(items)


# ---------------------------------------------------------------------------
# 配合
# ---------------------------------------------------------------------------

def mate_types():
    """返回配合类型映射 dict（swMateType_e，取自 SW2018 swconst）。"""
    return dict(MATE_TYPES)


def add_mate_full(asm, face1, face2, mate_type, align="closest", flip=False,
                  distance_m=0, angle_deg=0, dist_upper_m=None, dist_lower_m=None,
                  angle_upper_deg=None, angle_lower_deg=None, gear_num=1, gear_den=1,
                  lock_rotation=False, positioning_only=False, width_option=0):
    """添加配合（AddMate3/4/5 多版本回退），返回 (mate_feature, error_code)。

    参数：
        asm: IModelDoc2 装配体文档。
        face1 / face2: 配合实体。支持 IEntity 对象、含 name/type 的 dict 或名称 str。
        mate_type: 配合类型（str 或 int，见 mate_types()）。
        align: aligned=0 / anti=1 / closest=2。
        flip: 是否翻转。
        distance_m: 距离（米，API 内部单位）。
        angle_deg: 角度（度）。
        dist_upper_m / dist_lower_m: 距离上下限（米）。缺省等于 distance_m；
            与 distance_m 不同时 SW 会建成"极限距离"配合（LimitDistance）。
        angle_upper_deg / angle_lower_deg: 角度上下限（度）。缺省等于 angle_deg。
        gear_num / gear_den: 齿轮比分子/分母。
        lock_rotation: AddMate4 的 LockRotation。
        width_option: AddMate5 的 WidthMateOption。
        positioning_only: 是否仅定位。

    spec 示例：
        add_mate_full(asm, face1={"name": "Face<1>"}, face2={"name": "Face<2>"},
                      mate_type="coincident", align="closest")
        add_mate_full(asm, face1, face2, mate_type="distance", distance_m=0.02)

    SW2018 v26 实测：AddMate3 签名可用；AddMate4/5 回退待实测。
    """
    desc = f"add_mate_full(mate_type={mate_type}, align={align})"
    if isinstance(mate_type, str):
        if mate_type not in MATE_TYPES:
            raise RuntimeError(f"{desc}: 不支持的配合类型 {mate_type!r}")
        type_code = MATE_TYPES[mate_type]
    else:
        type_code = int(mate_type)
    if isinstance(align, str):
        if align not in ALIGN:
            raise RuntimeError(f"{desc}: 不支持的对齐方式 {align!r}")
        align_code = ALIGN[align]
    else:
        align_code = int(align)

    asm.ClearSelection2(True)
    sel_mgr = sw_core._early(asm.SelectionManager, "ISelectionMgr")
    for idx, face in enumerate((face1, face2)):
        if isinstance(face, (dict, str)):
            _select_named_entity(asm, face, desc, append=idx > 0, mark=1)
        else:
            data = sel_mgr.CreateSelectData()
            data.Mark = 1
            ent = sw_core._early(face, "IEntity")
            try:
                ok = bool(ent.Select4(idx > 0, data))
            except Exception:
                ok = False
            if not ok:
                try:
                    ok = bool(ent.Select2(idx > 0, 1))
                except Exception:
                    ok = False
            if not ok:
                raise RuntimeError(f"{desc}: 无法选择配合实体 {face!r}")

    return add_mate_selected(
        asm, type_code, align_code, flip=flip, distance_m=distance_m, angle_deg=angle_deg,
        dist_upper_m=dist_upper_m, dist_lower_m=dist_lower_m,
        angle_upper_deg=angle_upper_deg, angle_lower_deg=angle_lower_deg,
        gear_num=gear_num, gear_den=gear_den, lock_rotation=lock_rotation,
        positioning_only=positioning_only, width_option=width_option, desc=desc)


def add_mate_selected(asm, type_code, align_code, flip=False, distance_m=0, angle_deg=0,
                      dist_upper_m=None, dist_lower_m=None, angle_upper_deg=None,
                      angle_lower_deg=None,
                      gear_num=1, gear_den=1, lock_rotation=False, positioning_only=False,
                      width_option=0, desc="add_mate_selected"):
    """对当前已选实体（mark=1）调用 AddMate5/4/3，返回 (mate_feature, error_code)。

    调用方负责先选好实体；本函数调用后清空选择。
    上下限缺省（None）等于标称值；传 0 而标称值非 0 会被 SW 建成极限配合（SW2018 实测）。
    """
    dist_upper_m = distance_m if dist_upper_m is None else dist_upper_m
    dist_lower_m = distance_m if dist_lower_m is None else dist_lower_m
    angle_upper_deg = angle_deg if angle_upper_deg is None else angle_upper_deg
    angle_lower_deg = angle_deg if angle_lower_deg is None else angle_lower_deg
    base = (int(type_code), int(align_code), bool(flip), float(distance_m),
            float(dist_upper_m), float(dist_lower_m),
            int(gear_num), int(gear_den),
            math.radians(float(angle_deg)),
            math.radians(float(angle_upper_deg)), math.radians(float(angle_lower_deg)),
            bool(positioning_only))

    asm_dyn = _dyn(_as_asm(asm))
    last = None
    for method, extra in (("AddMate5", (bool(lock_rotation), int(width_option))),
                          ("AddMate4", (bool(lock_rotation),)),
                          ("AddMate3", ())):
        errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        try:
            mate = getattr(asm_dyn, method)(*(base + extra + (errors,)))
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
            continue
        asm.ClearSelection2(True)
        if mate is None:
            code = int(errors.value)
            raise RuntimeError(f"{desc}: {method} 未创建配合，错误码 {code}"
                               f"（{ADD_MATE_ERRORS.get(code, '未知')}）")
        # SW2018 实测：AddMate3 动态返回 CDispatch，包装成 IFeature 后
        # Name 会变成数字；原样返回，Name 读取正常。
        return mate, int(errors.value)
    raise RuntimeError(f"{desc}: AddMate3/4/5 所有候选签名均失败: {last}") from last


def _mate_group_feats(asm):
    """遍历 MateGroup 下的配合子特征，yield IFeature。"""
    for feat in sw_core.walk_features(asm):
        if sw_core.feature_type(feat) != "MateGroup":
            continue
        try:
            sub = feat.GetFirstSubFeature()
        except Exception:
            continue
        while sub is not None:
            sub = sw_core._early(sub, "IFeature")
            yield sub
            try:
                sub = sub.GetNextSubFeature()
            except Exception:
                break


def list_mates(asm):
    """列出全部配合：[{name, type, error_code, warning_code, suppressed}]。

    SW2018 v26 已实测：MateGroup 位于特征树顶层，配合为其子特征。
    """
    out = []
    for sub in _mate_group_feats(asm):
        err, warn = sw_core.feature_error_codes(sub)
        suppressed = None
        try:
            suppressed = bool(sw_core.com_get(sub, "GetSuppression2"))
        except Exception:
            suppressed = None
        out.append({
            "name": sw_core.feature_name(sub),
            "type": sw_core.feature_type(sub),
            "error_code": int(err),
            "warning_code": int(warn),
            "suppressed": suppressed,
        })
    return out


def _find_mate(asm, name):
    for sub in _mate_group_feats(asm):
        if sw_core.feature_name(sub) == str(name):
            return sub
    raise RuntimeError(f"delete_mate/suppress_mate: 未找到配合 {name!r}")


def delete_mate(asm, name):
    """删除配合：选中 MateGroup 子特征后 DeleteSelection2。

    SW2018 v26 实测：MateGroup 子特征为 IFeature，可用 Select2。
    """
    desc = f"delete_mate(name={name!r})"
    feat = _find_mate(asm, name)
    try:
        ok = bool(feat.Select2(False, 0))
    except Exception as exc:
        raise RuntimeError(f"{desc}: 配合特征选择失败: {exc}") from exc
    if not ok:
        raise RuntimeError(f"{desc}: 配合特征选择失败（Select2 返回 False）")
    ext = _dyn(asm).Extension
    # SW2018 v26 实测：DeleteSelection2(DeleteOptions)，1 个参数
    sigs = [(0,), (1,), (), (_empty(),), (VARIANT(pythoncom.VT_DISPATCH, None),)]
    try:
        _invoke_any(ext, "DeleteSelection2", sigs, desc)
        return True
    except Exception as exc:
        raise RuntimeError(f"{desc}: DeleteSelection2 失败: {exc}") from exc


def suppress_mate(asm, name, suppress=True):
    """抑制/解除抑制配合（IFeature.SetSuppression2）。

    SW2018 v26：配合为 MateGroup 子特征；SetSuppression2 多签名回退。
    """
    desc = f"suppress_mate(name={name!r}, suppress={suppress})"
    feat = _find_mate(asm, name)
    state = 0 if suppress else 1  # swFeatureSuppressionAction_e
    sigs = [(state,), (state, 0), (state, 0, None), (state, 0, "")]
    try:
        ret = _invoke_any(feat, "SetSuppression2", sigs, desc)
        return bool(ret) if ret is not None else True
    except Exception as exc:
        raise RuntimeError(f"{desc}: SetSuppression2 失败: {exc}") from exc


def check_mates_full(asm):
    """ForceRebuild3 + 配合清单 + What's Wrong。

    返回 {rebuild_ok, rebuild_error, mates, whats_wrong, errors}。
    """
    mates = list_mates(asm)
    rebuild_error = None
    try:
        rebuild_ok = sw_core.rebuild(asm)
    except Exception as exc:
        rebuild_ok = False
        rebuild_error = str(exc)
    whats_wrong = sw_core.get_whats_wrong(asm)
    errors = [m for m in mates
              if m["error_code"] not in (0, -1) or m["warning_code"] not in (0, -1)]
    return {
        "rebuild_ok": rebuild_ok,
        "rebuild_error": rebuild_error,
        "mates": mates,
        "whats_wrong": whats_wrong,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 零部件
# ---------------------------------------------------------------------------

def component_list(asm, top_level=True):
    """返回零部件列表（早绑定 IComponent2）。

    SW2018 v26 实测：IAssemblyDoc.GetComponents(TopLevelOnly)。
    """
    try:
        comps = _as_asm(asm).GetComponents(bool(top_level)) or []
    except Exception as exc:
        raise RuntimeError(f"component_list(top_level={top_level}): GetComponents 失败: {exc}") from exc
    return [sw_core._early(c, "IComponent2") for c in comps]


def insert_component_full(asm, path, config_option="use_existing", config_name="",
                          x=0, y=0, z=0):
    """插入零部件（AddComponent4 默认；新配置走 AddComponent5），返回 IComponent2。

    参数：
        asm: IModelDoc2 装配体文档。
        path: 零部件路径。
        config_option: use_existing / new_config / new_config_with_reference。
        config_name: 配置名；use_existing 时作为现有配置名传给 AddComponent4。
        x / y / z: 初始位置（米，API 内部单位）。

    spec 示例：
        insert_component_full(asm, r"D:\\parts\\a.SLDPRT", x=0.01)
        insert_component_full(asm, path, config_option="new_config",
                              config_name="Config-A")

    SW2018 v26 实测：AddComponent4(CompName, ConfigName, X, Y, Z)。
    AddComponent5 及配置选项值待实测。
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if config_option not in _CONFIG_OPTION:
        raise RuntimeError(
            f"insert_component_full: config_option 必须是 {list(_CONFIG_OPTION)} 之一")
    desc = f"insert_component_full(config_option={config_option})"
    x, y, z = float(x), float(y), float(z)

    if config_option == "use_existing":
        comp = _add_component4_with_retry(asm, path, config_name or "", x, y, z, desc)
    else:
        option = _CONFIG_OPTION[config_option]
        use_ref = (config_option == "new_config_with_reference")
        new_name = config_name or ""
        comp = _add_component5(asm, path, option, new_name, use_ref, x, y, z, desc)
    if comp is None:
        raise RuntimeError(f"{desc}: 插入零部件失败: {path}")
    return sw_core._early(comp, "IComponent2")


def _add_component4_with_retry(asm, path, config_name, x, y, z, desc):
    adoc = _as_asm(asm)
    try:
        comp = adoc.AddComponent4(path, config_name, x, y, z)
    except Exception as exc:
        if not sw_core.is_arg_count_error(exc):
            raise RuntimeError(f"{desc}: AddComponent4 调用失败: {exc}") from exc
        comp = None
    if comp is None:
        # AddComponent4 在零件未加载进内存时可能静默返回 None（SW2018 实测），
        # 打开文档、激活装配体后重试。
        try:
            sw = _get_sw()
            errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            _dyn(sw).OpenDoc6(path, 1, 0, "", errors, warns)
            _dyn(sw).ActivateDoc2(sw_core.com_get(asm, "GetTitle"), False, errors)
        except Exception:
            pass
        comp = adoc.AddComponent4(path, config_name, x, y, z)
    if comp is None:
        # 回退 AddComponent5（use_existing）
        comp = _add_component5(asm, path, 0, config_name, False, x, y, z, desc)
    return comp


def _add_component5(asm, path, option, new_config, use_ref, x, y, z, desc):
    adoc = _as_asm(asm)
    try:
        comp = adoc.AddComponent5(path, int(option), str(new_config),
                                  bool(use_ref), "", x, y, z)
    except Exception as exc:
        if not sw_core.is_arg_count_error(exc):
            raise RuntimeError(f"{desc}: AddComponent5 调用失败: {exc}") from exc
        comp = None
    if comp is None:
        # 部分版本现有配置选项值不同：回退 option=0 再试一次
        try:
            comp = adoc.AddComponent5(path, 0, str(new_config), bool(use_ref), "", x, y, z)
        except Exception:
            comp = None
    return comp


def set_component_suppression(comp, state):
    """设置零部件压缩状态。

    state ∈ suppressed / resolved / lightweight 或 int（0/1/2）。
    SW2018 v26 实测：IComponent2.SetSuppression2(State)。
    """
    desc = f"set_component_suppression(state={state!r})"
    if isinstance(state, str):
        if state not in _COMP_SUPPRESSION:
            raise RuntimeError(f"{desc}: state 必须是 {list(_COMP_SUPPRESSION)} 之一")
        code = _COMP_SUPPRESSION[state]
    else:
        code = int(state)
    try:
        ret = _invoke_any(comp, "SetSuppression2", [(code,), (code, 0)], desc)
        return bool(ret) if ret is not None else True
    except Exception as exc:
        raise RuntimeError(f"{desc}: SetSuppression2 失败: {exc}") from exc


def set_component_visible(comp, visible):
    """设置零部件可见性（Visible 属性/方法二义，用 sw_core.com_set）。"""
    try:
        sw_core.com_set(comp, "Visible", bool(visible))
        return True
    except Exception as exc:
        raise RuntimeError(f"set_component_visible(visible={visible}): 设置失败: {exc}") from exc


def is_fixed(comp):
    """返回零部件是否固定（IsFixed 属性/方法二义）。"""
    try:
        return bool(sw_core.com_get(comp, "IsFixed"))
    except Exception as exc:
        raise RuntimeError(f"is_fixed: 读取 IsFixed 失败: {exc}") from exc


def fix_component(asm, comp):
    """固定零部件：选择后调用 asm.FixComponent()，多签名回退。

    SW2018 v26 实测：零部件用 BODYFEATURE 选择；FixComponent 待实测。
    """
    desc = f"fix_component(comp={_comp_name(comp)!r})"
    _select_component(asm, comp, desc, append=False, mark=0)
    try:
        ret = _invoke_any(_dyn(_as_asm(asm)), "FixComponent", [()], desc)
        if ret is False:
            raise RuntimeError(f"{desc}: FixComponent 返回 False")
        return True
    except Exception as exc:
        raise RuntimeError(f"{desc}: FixComponent 调用失败: {exc}") from exc


def float_component(asm, comp):
    """浮动零部件：选择后调用 asm.UnfixComponent()，多签名回退。"""
    desc = f"float_component(comp={_comp_name(comp)!r})"
    _select_component(asm, comp, desc, append=False, mark=0)
    try:
        ret = _invoke_any(_dyn(_as_asm(asm)), "UnfixComponent", [()], desc)
        if ret is False:
            raise RuntimeError(f"{desc}: UnfixComponent 返回 False")
        return True
    except Exception as exc:
        raise RuntimeError(f"{desc}: UnfixComponent 调用失败: {exc}") from exc


def replace_component(asm, comp, new_path, config_name="", replace_all=True,
                      reattach_mates=True):
    """替换零部件（ReplaceComponents2）。

    SW2018 v26 签名：ReplaceComponents2(FileName, ConfigName,
    ReplaceAllInstance, UseConfigChoice, ReAttachMates)。
    """
    desc = f"replace_component(comp={_comp_name(comp)!r})"
    new_path = os.path.abspath(new_path)
    if not os.path.exists(new_path):
        raise FileNotFoundError(new_path)
    _select_component(asm, comp, desc, append=False, mark=0)
    use_config_choice = bool(config_name)
    sigs = [(new_path, config_name or "", bool(replace_all),
             use_config_choice, bool(reattach_mates))]
    try:
        ret = _invoke_any(_dyn(_as_asm(asm)), "ReplaceComponents2", sigs, desc)
        return bool(ret) if ret is not None else True
    except Exception as exc:
        raise RuntimeError(f"{desc}: ReplaceComponents2 失败: {exc}") from exc


def delete_component(asm, comp):
    """删除零部件：选择后 Extension.DeleteSelection2。"""
    desc = f"delete_component(comp={_comp_name(comp)!r})"
    _select_component(asm, comp, desc, append=False, mark=0)
    ext = _dyn(asm).Extension
    # SW2018 v26 实测：DeleteSelection2(DeleteOptions)，1 个参数
    sigs = [(0,), (1,), (), (_empty(),), (VARIANT(pythoncom.VT_DISPATCH, None),)]
    try:
        _invoke_any(ext, "DeleteSelection2", sigs, desc)
        return True
    except Exception as exc:
        raise RuntimeError(f"{desc}: DeleteSelection2 失败: {exc}") from exc


def move_component(asm, comp, dx_m=0, dy_m=0, dz_m=0):
    """平移零部件：复制 Transform2，修改 ArrayData[9:12] 后 SetTransformAndSolve2。

    参数 dx_m / dy_m / dz_m 为米（API 内部单位）。
    SW2018 v26 实测：Transform2 与 SetTransformAndSolve2 可用。
    """
    desc = f"move_component(comp={_comp_name(comp)!r}, dx_m={dx_m})"
    try:
        xform = sw_core.com_get(comp, "Transform2")
    except Exception as exc:
        raise RuntimeError(f"{desc}: 读取 Transform2 失败: {exc}") from exc
    try:
        arr = [float(v) for v in xform.ArrayData]
        arr[9] += float(dx_m)
        arr[10] += float(dy_m)
        arr[11] += float(dz_m)
        # SW2018 实测：早绑定直接赋 Python list 会被编组成 VARIANT 数组，SW 读成全零矩阵
        # （组件被打回原点且旋转丢失）；必须显式 VT_ARRAY|VT_R8。勿加 VT_BYREF（会使 SW 崩溃）。
        setattr(_dyn(xform), "ArrayData", VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, arr))
    except Exception as exc:
        raise RuntimeError(f"{desc}: 修改 Transform2.ArrayData 失败: {exc}") from exc
    try:
        ret = _invoke_any(comp, "SetTransformAndSolve2", [(xform,)], desc)
        return bool(ret) if ret is not None else True
    except Exception as exc:
        raise RuntimeError(f"{desc}: SetTransformAndSolve2 失败: {exc}") from exc


def insert_new_virtual_part(asm):
    """插入新虚拟零件（InsertNewVirtualPart），返回 IComponent2。

    SW2018 v26 签名：InsertNewVirtualPart(FaceOrPlaneToSelect,
    InsertedComponent(ByRef 可选))；需要先选择基准面/面。
    """
    desc = "insert_new_virtual_part"
    if sw_sel.selected_count(asm) <= 0:
        if not sw_core.select_by_id(asm, "前视基准面", "PLANE"):
            sw_core.select_by_id(asm, "Front Plane", "PLANE")
    plane_obj = None
    try:
        plane_obj = asm.SelectionManager.GetSelectedObject6(1, -1)
    except Exception:
        pass
    before = {c.Name2 for c in component_list(asm, top_level=False)}
    asm_dyn = _dyn(_as_asm(asm))
    out = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_DISPATCH, None)
    comp = None
    try:
        ret = asm_dyn.InsertNewVirtualPart(plane_obj, out)
        comp = out.value or ret
    except Exception:
        comp = None
    if comp is None or isinstance(comp, int):
        try:
            after = component_list(asm, top_level=False)
            for c in after:
                if c.Name2 not in before:
                    comp = c
                    break
        except Exception:
            comp = None
    if comp is None:
        raise RuntimeError(f"{desc}: InsertNewVirtualPart 调用失败（返回 None）")
    if isinstance(comp, int):
        return comp  # v26 返回组件 ID；组件列表在该版本暂不回读
    return sw_core._early(comp, "IComponent2")


def insert_new_assembly(asm, path):
    """插入新装配体（InsertNewAssembly(FileName)），返回 IComponent2 或 True。

    SW2018 v26 签名已实测；返回值类型待实测（对象则包装 IComponent2）。
    """
    desc = f"insert_new_assembly(path={path!r})"
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        ret = _invoke_any(_dyn(_as_asm(asm)), "InsertNewAssembly", [(path,)], desc)
    except Exception as exc:
        raise RuntimeError(f"{desc}: InsertNewAssembly 失败: {exc}") from exc
    if ret is None:
        return True
    try:
        return sw_core._early(ret, "IComponent2")
    except Exception:
        return ret


def save_virtual_component(comp, path):
    """保存虚拟零部件到文件（SaveAs/Save/Save2 多方法回退）。

    SW2018 v26：虚拟件保存方法名待实测。
    """
    desc = f"save_virtual_component(path={path!r})"
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    comp_dyn = _dyn(comp)
    last = None
    for method, sigs in (("SaveAs", [(path,)]),
                         ("Save", [(path,)]),
                         ("Save2", [(path, True)]),
                         ("Save2", [(path, False)])):
        try:
            ret = _invoke_any(comp_dyn, method, sigs, desc)
            return bool(ret) if ret is not None else True
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: SaveAs/Save/Save2 均失败: {last}") from last


# ---------------------------------------------------------------------------
# 阵列 / 镜像（装配体 FeatureManager）
# ---------------------------------------------------------------------------

def linear_pattern_components(asm, seed_comp, direction_spec, d1_spacing_m,
                              d1_instances, direction2_spec=None,
                              d2_spacing_m=0, d2_instances=1):
    """零部件线性阵列（FeatureLinearPattern4 20 参，SW2018 实测）。

    参数：
        asm: IModelDoc2 装配体。
        seed_comp: 种子零部件（IComponent2 或名称 str）。
        direction_spec: 方向1实体（IEntity 对象或含 name/type 的 dict）。
        d1_spacing_m: 方向1间距（米）。
        d1_instances: 方向1实例数（含种子）。
        direction2_spec / d2_spacing_m / d2_instances: 方向2，可空。

    spec 示例：
        linear_pattern_components(asm, seed_comp, direction_spec,
                                  d1_spacing_m=0.01, d1_instances=4)
    """
    desc = (f"linear_pattern_components(n1={d1_instances}, s1={d1_spacing_m}, "
            f"n2={d2_instances})")
    # SW2018 v26 实测：种子零部件 Select2 mark=1，方向实体 mark=2
    _select_component(asm, seed_comp, desc, append=False, mark=1)
    _select_asm_direction(asm, direction_spec, desc, mark=2)
    if direction2_spec is not None:
        _select_asm_direction(asm, direction2_spec, desc, mark=4)
    fm = _swf._fm(asm)
    n1, n2 = int(d1_instances), int(d2_instances)
    s1, s2 = float(d1_spacing_m), float(d2_spacing_m)
    # 与 sw_features.linear_pattern 的实测参数构造一致（装配版同为 FeatureLinearPattern4 20 参）
    a2 = (n1, s1, n2, s2, False, False, "", "", False)
    a3 = a2 + (False,)
    a4 = a3 + (False, False, False, False, False, False, False, False, 0.0, 0.0)
    a5 = a4 + (False, False)
    return _swf._feat_methods(fm, [
        ("FeatureLinearPattern5", [a5]),
        ("FeatureLinearPattern4", [a4]),
        ("FeatureLinearPattern3", [a3]),
        ("FeatureLinearPattern2", [a2]),
    ], desc)


def circular_pattern_components(asm, seed_comp, axis_spec, angle_deg, instances,
                                equal_spacing=True):
    """零部件圆周阵列（FeatureCircularPattern5 14 参，装配版含 BDir2/BSymmetric）。

    参数：
        asm: IModelDoc2 装配体。
        seed_comp: 种子零部件。
        axis_spec: 阵列轴实体。
        angle_deg: 总角度（度）；equal_spacing=True 时均布整周。
        instances: 实例数（含种子）。
        equal_spacing: True 均布整周。

    spec 示例：
        circular_pattern_components(asm, seed_comp, axis_spec,
                                    angle_deg=360, instances=6)
    """
    desc = f"circular_pattern_components(n={instances}, equal={equal_spacing})"
    # SW2018 v26 实测（同线性阵列）：种子 mark=1，轴实体 mark=2
    _select_component(asm, seed_comp, desc, append=False, mark=1)
    _select_asm_direction(asm, axis_spec, desc, mark=2)
    fm = _swf._fm(asm)
    num = int(instances)
    if equal_spacing:
        spacing = 2.0 * math.pi / max(1, num)
    else:
        spacing = math.radians(float(angle_deg)) / max(1, num - 1)
    seed_obj = seed_comp if not isinstance(seed_comp, str) else \
        _find_component_by_name(asm, seed_comp)
    # 装配版 FeatureCircularPattern5 14 参（Spacing, Count, ReverseDirection,
    # GeometryPattern, EqualSpacing, DirectionVect, SyncFlexibleComponents,
    # BDir2, BSymmetric, SeedComp, PatternCompArray, InstancesArray,
    # InstancesVary, SkipInstances）；BDir2/BSymmetric 等待实测。
    a5 = (spacing, num, False, "", bool(equal_spacing),
          False, False, False, bool(equal_spacing),
          seed_obj, None, None, False, False)
    a4 = a5[:13]
    a3 = a5[:12]
    a2 = a5[:11]
    return _swf._feat_methods(fm, [
        ("FeatureCircularPattern5", [a5]),
        ("FeatureCircularPattern4", [a4]),
        ("FeatureCircularPattern3", [a3]),
        ("FeatureCircularPattern2", [a2]),
    ], desc)


def mirror_components(asm, seed_comps, plane_spec=None, plane_name=None):
    """镜像零部件（InsertMirrorFeature / InsertMirrorFeature2）。

    参数：
        asm: IModelDoc2 装配体。
        seed_comps: 种子零部件或列表。
        plane_spec: 镜像平面对象或含 name/type 的 dict。
        plane_name: 基准面名称（支持中英文候选：Top Plane/上视基准面/上视 等）。

    spec 示例：
        mirror_components(asm, seed_comps=[comp1], plane_name="Top Plane")
        mirror_components(asm, seed_comps=[comp1], plane_name="上视基准面")
    """
    desc = f"mirror_components(n={len(_norm_list(seed_comps))})"
    _select_plane(asm, plane_spec=plane_spec, plane_name=plane_name, desc=desc)
    comps = _norm_list(seed_comps)
    # SW2018 v26 实测：IAssemblyDoc.MirrorComponents 可用；返回 (feature,)
    try:
        plane_obj = asm.SelectionManager.GetSelectedObject6(1, -1)
        comp_var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, comps)
        ret = _as_asm(asm).MirrorComponents(
            plane_obj, None, comp_var, None, True, 0, "", "", True)
        if ret:
            return ret[0]
    except Exception:
        pass
    # 回退 FeatureManager.InsertMirrorFeature
    for seed in comps:
        if seed is not None:
            _select_component(asm, seed, desc, append=True, mark=1)
    fm = _swf._fm(asm)
    sigs = [(False, False, True, False),
            (False, False, False, False),
            (False, True, False, False)]
    sigs2 = [s + (0,) for s in sigs]
    return _swf._feat_methods(fm, [
        ("InsertMirrorFeature", sigs),
        ("InsertMirrorFeature2", sigs2),
    ], desc)


def sketch_driven_pattern_components(asm, seed_comp, point_sketch):
    """草图驱动零部件阵列（FeatureSketchDrivenPattern(UseCentroid, BGeomPatt)）。

    spec 示例：
        sketch_driven_pattern_components(asm, seed_comp, point_sketch="Sketch3")
    """
    desc = "sketch_driven_pattern_components"
    _select_seed_component(asm, seed_comp, desc)
    _swf._select_feature_spec(asm, point_sketch, desc, append=True, mark=16)
    fm = _swf._fm(asm)
    return _swf._feat_methods(fm, [
        ("FeatureSketchDrivenPattern", [(True, False), (False, False)]),
        ("FeatureLocalSketchDrivenPattern", [(0,), (1,)]),
    ], desc)


def derived_pattern_components(asm, seed_comp):
    """派生零部件阵列（InsertDerivedPattern()）。

    spec 示例：
        derived_pattern_components(asm, seed_comp)
    """
    desc = "derived_pattern_components"
    _select_seed_component(asm, seed_comp, desc)
    fm = _swf._fm(asm)
    try:
        return _swf._feat(fm, "InsertDerivedPattern", [()], desc)
    except Exception as exc:
        raise RuntimeError(f"{desc}: InsertDerivedPattern 失败: {exc}") from exc


# ---------------------------------------------------------------------------
# 检查
# ---------------------------------------------------------------------------

def _com_interference_count(asm):
    """优先 COM 干涉检查 ToolsCheckInterference2；返回数量或 None（失败不抛）。"""
    try:
        comps = component_list(asm, top_level=False)
        if not comps:
            return 0
        ext = _dyn(asm).Extension
        comp_arr = comps
        sigs = [
            (len(comp_arr), comp_arr, 0, None),
            (len(comp_arr), comp_arr, 0, _empty()),
            (len(comp_arr), comp_arr, 0, VARIANT(pythoncom.VT_DISPATCH, None)),
        ]
        try:
            ret = _invoke_any(ext, "ToolsCheckInterference2", sigs,
                              "assembly_interference(ToolsCheckInterference2)")
        except Exception:
            return None
    except Exception:
        return None
    if ret is None:
        return None
    try:
        n = int(getattr(ret, "Count"))
        return n
    except Exception:
        pass
    if isinstance(ret, (list, tuple)):
        return len(ret)
    return 1


def _bbox_interference_pairs(asm):
    """包围盒干涉初筛（COM 干涉不可用时的回退）。"""
    pairs = []
    boxes = []
    try:
        comps = component_list(asm, top_level=False)
    except Exception:
        return pairs
    for comp in comps:
        try:
            body = comp.GetBody()
            if body is None:
                continue
            box = body.GetBodyBox()
            boxes.append((_comp_name(comp), [float(v) for v in box]))
        except Exception:
            continue
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1, b2 = boxes[i][1], boxes[j][1]
            if sw_check.boxes_overlap(b1, b2):
                pairs.append({"component_a": boxes[i][0], "component_b": boxes[j][0],
                              "box_a_m": b1, "box_b_m": b2})
    return pairs


def assembly_interference(asm):
    """装配体干涉检查。

    优先 model.Extension.ToolsCheckInterference2（返回对象数组形式待实测），
    失败回退包围盒初筛（sw_check.boxes_overlap），不抛致命错误。
    返回 {ok, interference_count, message}。
    """
    count = _com_interference_count(asm)
    if count is not None:
        message = "COM 干涉检查 ToolsCheckInterference2"
        if count == 0:
            message += "：未发现干涉"
        else:
            message += f"：发现 {count} 处干涉"
        return {"ok": count == 0, "interference_count": count, "message": message}
    pairs = _bbox_interference_pairs(asm)
    count = len(pairs)
    message = "COM 干涉接口不可用，已回退包围盒初筛（仅参考，非精确干涉）"
    return {"ok": count == 0, "interference_count": count,
            "message": message, "bbox_overlaps": pairs}


def assembly_mass_properties(asm):
    """装配体质量属性：{volume_m3, mass_kg, density_kg_m3, surface_area_m2}。

    SW2018 v26 实测：IModelDocExtension.CreateMassProperty 可用。
    """
    try:
        return sw_core.mass_properties(asm)
    except Exception as exc:
        raise RuntimeError(f"assembly_mass_properties: CreateMassProperty 失败: {exc}") from exc


def assembly_rebuild_report(asm):
    """装配体重建报告：ForceRebuild3 + 配合清单 + What's Wrong。

    返回 {rebuild_ok, rebuild_error, mates, whats_wrong, errors}。
    """
    return check_mates_full(asm)


# ---------------------------------------------------------------------------
# 装配特征
# ---------------------------------------------------------------------------

def _select_affected_components(asm, affected_components, desc):
    """预选受装配特征影响的零部件：BODYFEATURE mark=1。None 表示不预选（自动选择）。"""
    if affected_components is None:
        return
    first = True
    for comp in _norm_list(affected_components):
        if comp is None:
            continue
        _select_component(asm, comp, desc, append=not first, mark=1)
        first = False


def assembly_cut(asm, sketch, depth_m, affected_components=None,
                 end_condition="blind"):
    """装配体拉伸切除（FeatureCut3 的 AssemblyFeatureScope=True 版本）。

    参数：
        asm: IModelDoc2 装配体。
        sketch: 草图名(str) 或 IFeature。
        depth_m: 切除深度（米）。
        affected_components: 受影响的零部件列表；None 表示不预选（UseAutoSelect=True）。
        end_condition: blind / through_all / midplane 等。

    spec 示例：
        assembly_cut(asm, sketch="Sketch1", depth_m=0.005,
                     affected_components=[comp1, comp2])

    SW2018 v26：FeatureCut3 参数与 sw_features.extrude_cut 一致，但需预选
    受影响零部件（BODYFEATURE mark=1）并将 AssemblyFeatureScope 置 True。
    """
    desc = f"assembly_cut(end_condition={end_condition})"
    t1 = _END_COND.get(end_condition)
    if t1 is None:
        raise RuntimeError(f"{desc}: 不支持的终止条件 {end_condition!r}")

    asm.ClearSelection2(True)
    _select_affected_components(asm, affected_components, desc)
    use_auto = affected_components is None
    if sketch is None:
        # 未显式给草图时，要求调用方已把草图选入选择集（且不会被清空）。
        if sw_sel.selected_count(asm) <= 0:
            raise RuntimeError(f"{desc}: sketch 为 None 时当前选择集不能为空")
    else:
        # 注意：必须在已选零部件的基础上追加选择草图，append=False 会清掉零部件。
        _swf._select_feature_spec(asm, sketch, desc, append=True, mark=0)

    t2 = t1 if False else 0  # direction2 不支持，保持与 extrude_cut 兼容
    d1 = float(depth_m)
    d2 = 0.0
    sd = False if end_condition == "midplane" else True
    dchk = False
    dang = 0.0
    flip_cut = False
    # 与 sw_features.extrude_cut 的 FeatureCut3 26 参一致；
    # 第 20 参 UseAutoSelect、第 22 参 AssemblyFeatureScope（位置待实测，按 v26 推测）
    args3 = [sd, flip_cut, False, t1, t2, d1, d2,
             dchk, False, False, False, dang, 0.0,
             False, False, False, False,
             False, False, use_auto, False, True, False,
             0, 0.0, False]
    args4 = tuple(args3) + (True,)
    fm = _swf._fm(asm)
    return _swf._feat_methods(fm, [
        ("FeatureCut4", [args4]),
        ("FeatureCut3", [tuple(args3)]),
    ], desc)


def _select_ref_entities(model, primary_spec, secondary_spec, tertiary_spec, desc):
    """依次选择配合参考实体（InsertMateReference 用）。"""
    first = True
    for spec in (primary_spec, secondary_spec, tertiary_spec):
        if spec is None:
            continue
        _select_named_entity(model, spec, desc, append=not first, mark=0)
        first = False


def add_mate_reference(model, name, primary_spec, primary_type=0, primary_align=0,
                       secondary_spec=None, secondary_type=0, secondary_align=0,
                       tertiary_spec=None, tertiary_type=0, tertiary_align=0):
    """添加配合参考（FeatureManager.InsertMateReference / InsertMateReference2）。

    参数：
        model: 零件或装配体文档。
        name: 配合参考名称。
        primary_spec / secondary_spec / tertiary_spec: 参考实体（对象或 name/type dict）。
        primary_type / secondary_type / tertiary_type: 参考类型枚举（0 待实测）。
        primary_align / secondary_align / tertiary_align: 对齐枚举。

    spec 示例：
        add_mate_reference(model, "Ref-A",
                           primary_spec={"name": "Face<1>", "type": "FACE"},
                           primary_type=0, primary_align=0)

    SW2018 v26：InsertMateReference / InsertMateReference2 签名待实测。
    """
    desc = f"add_mate_reference(name={name!r})"
    model.ClearSelection2(True)
    _select_ref_entities(model, primary_spec, secondary_spec, tertiary_spec, desc)
    fm = _swf._fm(model)
    sel_objs = _selected_entity_objects(model, 3)
    p_ent = _dyn(primary_spec) if not isinstance(primary_spec, (dict, str, type(None))) else (
        _dyn(sel_objs[0]) if len(sel_objs) > 0 else None)
    s_ent = _dyn(secondary_spec) if not isinstance(secondary_spec, (dict, str, type(None))) else (
        _dyn(sel_objs[1]) if len(sel_objs) > 1 else None)
    t_ent = _dyn(tertiary_spec) if not isinstance(tertiary_spec, (dict, str, type(None))) else (
        _dyn(sel_objs[2]) if len(sel_objs) > 2 else None)
    base = (str(name), p_ent, int(primary_type), int(primary_align),
            s_ent, int(secondary_type), int(secondary_align),
            t_ent, int(tertiary_type), int(tertiary_align))
    sigs1 = [base]
    sigs2 = [base + (0,), base + (0.0,), base + (False,)]
    try:
        return _swf._feat_methods(fm, [
            ("InsertMateReference", sigs1),
            ("InsertMateReference2", sigs2),
        ], desc)
    except Exception as exc:
        raise RuntimeError(f"{desc}: InsertMateReference/2 调用失败: {exc}") from exc


def hole_series(asm, sketch, face_specs, dia_m, depth_m):
    """装配体孔系列（FeatureManager.HoleSeries，尽力实现）。

    参数：
        asm: IModelDoc2 装配体。
        sketch: 孔位置草图。
        face_specs: 参与孔系列的面（对象或 name/type dict 列表）。
        dia_m: 孔径（米）。
        depth_m: 深度（米）。

    spec 示例：
        hole_series(asm, sketch="Sketch1",
                    face_specs=[{"name": "Face<1>", "type": "FACE"}],
                    dia_m=0.006, depth_m=0.02)

    SW2018 v26：FeatureManager.HoleSeries 签名待实测；不存在时抛清晰中文。
    """
    desc = "hole_series"
    asm.ClearSelection2(True)
    _swf._select_sketch(asm, sketch, desc)
    # 草图已选中，后续参与面必须全部 append=True。
    for spec in _norm_list(face_specs):
        if spec is None:
            continue
        _select_named_entity(asm, spec, desc, append=True, mark=0)
    fm = _swf._fm(asm)
    sigs = [
        (0, float(dia_m), float(depth_m), None, None, None),
        (0, 0, float(dia_m), float(depth_m), None, None, None),
        (float(dia_m), float(depth_m), None, None, None),
    ]
    # 若传入的是对象，把对象填进候选签名
    obj_specs = [s for s in _norm_list(face_specs) if s is not None and not isinstance(s, (dict, str))]
    if len(obj_specs) >= 3:
        sigs.insert(0, (0, float(dia_m), float(depth_m),
                        obj_specs[0], obj_specs[1], obj_specs[2]))
    elif len(obj_specs) == 2:
        sigs.insert(0, (0, float(dia_m), float(depth_m),
                        obj_specs[0], obj_specs[1], None))
    elif len(obj_specs) == 1:
        sigs.insert(0, (0, float(dia_m), float(depth_m),
                        obj_specs[0], None, None))
    try:
        return _feat_void(fm, "HoleSeries", sigs, desc, asm)
    except Exception as exc:
        raise RuntimeError(
            f"{desc}: 当前 SolidWorks 的 FeatureManager 不存在可用的 HoleSeries "
            f"方法（或签名不匹配），无法创建装配体孔系列: {exc}") from exc


# ---------------------------------------------------------------------------
# 编排：run_spec
# ---------------------------------------------------------------------------

def run_spec(spec):
    """按 spec 编排装配体建模流程，返回报告 dict。

    spec 示例：
        {
          "template": null,
          "asm": null,               # 已打开装配体对象；缺省则新建
          "components": [
            {"path": "D:/parts/a.SLDPRT", "at": [0, 0, 0],
             "config_option": "use_existing", "config_name": "",
             "fix": false, "visible": true, "suppression": "resolved"},
          ],
          "mates": [
            {"face1": {"name": "Face<1>", "type": "FACE"},
             "face2": {"name": "Face<2>", "type": "FACE"},
             "mate_type": "coincident", "align": "closest"},
          ],
          "patterns": [
            {"type": "linear", "seed_comp": "a-1",
             "direction_spec": {"name": "Edge<1>", "type": "EDGE"},
             "d1_spacing_m": 0.02, "d1_instances": 4},
          ],
          "checks": {"rebuild": true, "interference": true, "mass_properties": true},
          "save": "D:/out/asm.SLDASM",
        }

    返回报告 dict；所有距离/坐标在 spec 中均为米（API 内部单位）。
    """
    sw = _get_sw()
    asm_obj = spec.get("asm")
    if asm_obj is None:
        asm = sw_assembly.new_assembly(sw, spec.get("template"))
    elif isinstance(asm_obj, str):
        asm = sw_core.open_doc(sw, asm_obj, doc_type=2)
    else:
        asm = sw_core._early(asm_obj, "IModelDoc2")

    report = {"components": [], "mates": [], "patterns": []}

    for c in spec.get("components", []) or []:
        path = c["path"]
        at = c.get("at", (0.0, 0.0, 0.0))
        comp = insert_component_full(
            asm, path,
            config_option=c.get("config_option", "use_existing"),
            config_name=c.get("config_name", ""),
            x=float(at[0]), y=float(at[1]), z=float(at[2]))
        comp = sw_core._early(comp, "IComponent2")
        if c.get("suppression") is not None:
            set_component_suppression(comp, c["suppression"])
        if "visible" in c:
            set_component_visible(comp, bool(c["visible"]))
        if c.get("fix") is True:
            fix_component(asm, comp)
        elif c.get("fix") is False:
            float_component(asm, comp)
        report["components"].append({
            "name": _comp_name(comp),
            "path": path,
            "fixed": is_fixed(comp),
        })

    for m in spec.get("mates", []) or []:
        mate_feat, err_code = add_mate_full(
            asm,
            m.get("face1"), m.get("face2"),
            mate_type=m.get("mate_type", "coincident"),
            align=m.get("align", "closest"),
            flip=m.get("flip", False),
            distance_m=float(m.get("distance_m", 0)),
            angle_deg=float(m.get("angle_deg", 0)),
            dist_upper_m=(float(m["dist_upper_m"]) if m.get("dist_upper_m") is not None else None),
            dist_lower_m=(float(m["dist_lower_m"]) if m.get("dist_lower_m") is not None else None),
            angle_upper_deg=(float(m["angle_upper_deg"]) if m.get("angle_upper_deg") is not None else None),
            angle_lower_deg=(float(m["angle_lower_deg"]) if m.get("angle_lower_deg") is not None else None),
            gear_num=int(m.get("gear_num", 1)),
            gear_den=int(m.get("gear_den", 1)),
            lock_rotation=m.get("lock_rotation", False),
            positioning_only=m.get("positioning_only", False),
            width_option=int(m.get("width_option", 0)))
        report["mates"].append({
            "name": sw_core.feature_name(mate_feat),
            "error_code": int(err_code),
        })

    for p in spec.get("patterns", []) or []:
        ptype = p.get("type")
        if ptype == "linear":
            feat = linear_pattern_components(
                asm, p.get("seed_comp"), p.get("direction_spec"),
                d1_spacing_m=float(p.get("d1_spacing_m", 0)),
                d1_instances=int(p.get("d1_instances", 2)),
                direction2_spec=p.get("direction2_spec"),
                d2_spacing_m=float(p.get("d2_spacing_m", 0)),
                d2_instances=int(p.get("d2_instances", 1)))
        elif ptype == "circular":
            feat = circular_pattern_components(
                asm, p.get("seed_comp"), p.get("axis_spec"),
                angle_deg=float(p.get("angle_deg", 360)),
                instances=int(p.get("instances", 2)),
                equal_spacing=p.get("equal_spacing", True))
        elif ptype == "mirror":
            feat = mirror_components(
                asm, p.get("seed_comps"),
                plane_spec=p.get("plane_spec"),
                plane_name=p.get("plane_name"))
        elif ptype == "sketch_driven":
            feat = sketch_driven_pattern_components(
                asm, p.get("seed_comp"), p.get("point_sketch"))
        elif ptype == "derived":
            feat = derived_pattern_components(asm, p.get("seed_comp"))
        else:
            raise RuntimeError(f"run_spec: 不支持的阵列类型 {ptype!r}")
        report["patterns"].append({
            "type": ptype,
            "feature": sw_core.feature_name(feat),
        })

    checks = spec.get("checks", True)
    check_report = {}
    if checks is not False:
        if checks is True or checks is None:
            checks = {}
        if checks.get("rebuild", True):
            check_report["rebuild"] = assembly_rebuild_report(asm)
        if checks.get("interference", True):
            check_report["interference"] = assembly_interference(asm)
        if checks.get("mass_properties", True):
            check_report["mass_properties"] = assembly_mass_properties(asm)
    report["checks"] = check_report

    save_path = spec.get("save")
    if save_path:
        report["save"] = sw_core.save_as(asm, save_path, sw=sw)
    return report


# ---------------------------------------------------------------------------
# 公开 API 列表（DSL 按名调用）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 子装配体管理
# ---------------------------------------------------------------------------

def find_component(asm, name):
    """按 Name2 查找装配体组件（含嵌套级）。"""
    for c in component_list(asm, top_level=False):
        if _comp_name(c) == str(name):
            return c
    raise RuntimeError(f"find_component: 未找到组件 {name!r}")


def insert_subassembly(asm, path, config_name="", x=0, y=0, z=0):
    """插入一个已有装配体作为子装配体（AddComponent4/5 与零件同路径）。"""
    desc = f"insert_subassembly(path={path!r})"
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        return insert_component_full(asm, path, config_option="use_existing",
                                     config_name=config_name, x=x, y=y, z=z)
    except Exception as exc:
        raise RuntimeError(f"{desc}: {exc}") from exc


def dissolve_subassembly(asm, comp):
    """解散选中的子装配体（SW2018: IAssemblyDoc.DissolveSubAssembly）。"""
    desc = f"dissolve_subassembly(comp={comp!r})"
    asm.ClearSelection2(True)
    _select_component(asm, comp, desc, append=False, mark=0)
    try:
        ret = _as_asm(asm).DissolveSubAssembly()
    except Exception as exc:
        raise RuntimeError(f"{desc}: DissolveSubAssembly 失败: {exc}") from exc
    return bool(ret) if ret is not None else True


def edit_subassembly(asm, comp):
    """进入选中子装配体的编辑模式（IAssemblyDoc.EditAssembly）。"""
    desc = f"edit_subassembly(comp={comp!r})"
    asm.ClearSelection2(True)
    _select_component(asm, comp, desc, append=False, mark=0)
    try:
        ret = _as_asm(asm).EditAssembly()
    except Exception as exc:
        raise RuntimeError(f"{desc}: EditAssembly 失败: {exc}") from exc
    return bool(ret) if ret is not None else True


PUBLIC_API = [
    "mate_types",
    "find_component",
    "insert_subassembly",
    "dissolve_subassembly",
    "edit_subassembly",
    "add_mate_full",
    "list_mates",
    "delete_mate",
    "suppress_mate",
    "check_mates_full",
    "component_list",
    "insert_component_full",
    "set_component_suppression",
    "set_component_visible",
    "is_fixed",
    "fix_component",
    "float_component",
    "replace_component",
    "delete_component",
    "move_component",
    "insert_new_virtual_part",
    "insert_new_assembly",
    "save_virtual_component",
    "linear_pattern_components",
    "circular_pattern_components",
    "mirror_components",
    "sketch_driven_pattern_components",
    "derived_pattern_components",
    "assembly_interference",
    "assembly_mass_properties",
    "assembly_rebuild_report",
    "assembly_cut",
    "add_mate_reference",
    "hole_series",
    "run_spec",
]
