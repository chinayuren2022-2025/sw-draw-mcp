# -*- coding: utf-8 -*-
"""sw_features.py — SolidWorks 2018（类型库 v26）零件建模特征层（补全清单 3.x）

目标环境：Windows + pywin32 311 + SolidWorks 2018。当前开发环境为 Linux，
只能 py_compile，无法真正调用 COM；因此本模块所有特征调用均采用：
    - 多签名回退（sw_core.call_sigs）
    - 多方法名回退（如 FeatureExtrusion2/3、FeatureFillet/FeatureFillet3）
    - 返回统一包装 sw_core._early(feat, "IFeature")
    - 选择实体一律走 sw_sel，不使用视角坐标拾取
    - 单位：API 参数用米；毫米输入参数名带 _mm 并在内部转换
    - 错误信息中文并带函数名/关键参数
所有公开函数 docstring 中均标注“签名待 SW2018 实测”。
"""
import math

import sw_core
import sw_sel

# ---------------------------------------------------------------------------
# 常量映射（来源：SolidWorks 2018 API swconst；签名待 SW2018 实测）
# ---------------------------------------------------------------------------

# swEndConditions_e：终止条件
_END_COND = {
    "blind": 0,
    "through_all": 1,
    "through_next": 2,
    "offset_from_surface": 5,
    "midplane": 6,
    "through_all_both": 9,
    # SW2018 中 up_to_vertex / up_to_surface 已被 swEndCondUpToSelection=10 取代
    "up_to_vertex": 10,
    "up_to_surface": 10,
    "up_to_selection": 10,
}

# swStartConditions_e：起始条件
_START_SKETCH_PLANE = 0
_START_OFFSET = 3

# 薄壁方向（FeatureExtrusionThin / FeatureRevolve2 的 RevThinDir/ThinType）
_THIN_ONE_DIR = 0
_THIN_MID_PLANE = 2
_THIN_TWO_DIR = 3

# swFeatureFilletType_e（SW2018 v26 实测/swconst.tlb）
# Simple=0, VariableRadius=1, Face=2, FullRound=3
_FILLET_TYPE = {
    "constant": 0,     # swFeatureFilletType_Simple
    "variable": 1,     # swFeatureFilletType_VariableRadius
    "face": 2,         # swFeatureFilletType_Face
    "full_round": 3,   # swFeatureFilletType_FullRound
}

# swFeatureFilletOptions_e（来自 swconst.tlb）
_FILLET_OPT = {
    "propagate": 1,
    "uniform_radius": 2,
    "var_radius_type": 4,
    "use_help_point": 8,
    "use_tangent_hold_line": 16,
    "corner_type": 32,
    "attach_edges": 64,
    "keep_features": 128,
    "curvature_continuous": 256,
    "constant_width": 512,
    "no_trim_no_attached": 1024,
    "reverse_face1_dir": 2048,
    "reverse_face2_dir": 4096,
    "propagate_feat_to_parts": 8192,
    "asymmetric": 16384,
}

# swChamferType_e（注意：sw_part.py 实测 InsertFeatureChamfer 第一参数 Options=4）
_CHAMFER_TYPE = {
    "angle_distance": 1,
    "distance_distance": 2,
    "vertex": 3,
    "offset_face": 16,  # swChamferEqualDistance，offset_face 待 SW2018 实测
}

# swWrapSketchType_e
_WRAP_TYPE = {"emboss": 0, "deboss": 1, "scribe": 2}

# swScaleType_e
_SCALE_ABOUT = {"centroid": 0, "origin": 1, "coordinate_system": 2}

# swFlexType_e 近似值（swFlexType_e 页面 SW2018 未公开，待实测）
_FLEX_TYPE = {"bending": 0, "twisting": 1, "stretching": 2, "tapering": 3}

# swMoveFaceType_e
_MOVE_FACE_TYPE = {"offset": 0, "translate": 1, "rotate": 2}

# swFaceDeleteOption_e
_DELETE_FACE_OPTION = {
    "delete": 0,            # swFaceDelete_Default
    "patch": 1,             # swFaceDelete_Patch
    "fill": 2,              # swFaceDelete_Fill
    "fill_with_tangent": 3, # swFaceDelete_FillWithTangent
}

# swBodyOperationType_e
_COMBINE_OP = {"add": 15903, "subtract": 15902, "common": 15901}

# swFeatureSuppressionAction_e
_SUPPRESS_ACTION = {True: 0, False: 1}

# swCustomInfoType_e：30 = Text
_CUSTOM_INFO_TEXT = 30

# swPatternLayoutType_e
_FILL_LAYOUT = {
    "circular": 0, "square": 1, "polygon": 2, "perforation": 3,
}


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _fm(model):
    """返回 IFeatureManager（后期绑定视图兼容）。"""
    try:
        return model.FeatureManager
    except Exception as exc:
        raise RuntimeError(f"获取 FeatureManager 失败: {exc}") from exc


def _feat(fm, method, sigs, desc):
    """统一特征调用：call_sigs + None 检查 + _early('IFeature') 包装。"""
    raw = sw_core.call_sigs(fm, method, sigs, desc)
    if raw is None:
        raise RuntimeError(f"{desc}: {method} 返回 None")
    return sw_core._early(raw, "IFeature")


def _feat_methods(fm, methods_sigs, desc):
    """按方法名多版本回退调用；methods_sigs = [(method, sigs), ...]。"""
    last = None
    for method, sigs in methods_sigs:
        try:
            return _feat(fm, method, sigs, desc)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: 所有候选方法/签名均失败: {last}") from last


def _sub_feat(obj, method, sigs, desc, model):
    """调用返回 void 的特征方法，随后从特征树找最新特征包装返回。"""
    last = None
    for args in sigs:
        try:
            getattr(obj, method)(*args)
            feat = _newest_feature(model)
            if feat is not None:
                return feat
            last = RuntimeError(f"{desc}: {method} 调用后未在特征树找到新特征")
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}") from last


def _newest_feature(model):
    """返回特征树最后一个顶层特征；无特征返回 None。"""
    feats = list(sw_core.walk_features(model))
    return feats[-1] if feats else None


def _find_newest_by_type(model, type_names):
    """从后往前按类型名找最新特征；找不到回退到最后一个特征。"""
    feats = list(sw_core.walk_features(model))
    for feat in reversed(feats):
        t = (sw_core.feature_type(feat) or "").lower()
        if any(k.lower() in t for k in type_names):
            return feat
    return feats[-1] if feats else None


def _norm_list(specs):
    """把 None/单 spec 归一化为列表。"""
    if specs is None:
        return [None]
    if isinstance(specs, (list, tuple)):
        return list(specs)
    return [specs]


def _ensure_selection(model, desc):
    if sw_sel.selected_count(model) <= 0:
        raise RuntimeError(f"{desc}: 当前选择为空，请先选择实体")


def _select_entity_obj(model, entity, append=False, mark=0):
    """选择 COM 实体对象（IEntity/IFeature 均可）。"""
    if entity is None:
        return False
    try:
        if hasattr(entity, "Select4"):
            return sw_sel._select_entity(model, entity, append, mark)
    except Exception:
        pass
    try:
        return bool(entity.Select2(bool(append), int(mark)))
    except Exception:
        return False


def _select_feature_spec(model, feat_spec, desc, append=False, mark=0):
    """选择特征：feat_spec 可为特征名(str)/IFeature/含 name/type 的 dict。"""
    if isinstance(feat_spec, str):
        return sw_sel.select_feature(model, name=feat_spec, append=append, mark=mark)
    if isinstance(feat_spec, dict):
        return sw_sel.select_feature(model, name=feat_spec.get("name"),
                                     type_name=feat_spec.get("type"),
                                     append=append, mark=mark)
    if _select_entity_obj(model, feat_spec, append=append, mark=mark):
        return feat_spec
    raise RuntimeError(f"{desc}: 无法选择特征 {feat_spec!r}")


def _select_sketch(model, sketch, desc):
    """选择草图。sketch=None 时要求当前已有一个“已退出且选中”的草图。"""
    if sketch is None:
        _ensure_selection(model, desc)
        return None
    return _select_feature_spec(model, sketch, desc)


def _select_edge_specs(model, edge_specs, desc):
    """按 sw_sel 规格选择边线；edge_specs=None 表示使用当前选择。"""
    if edge_specs is None:
        _ensure_selection(model, desc)
        return
    first = True
    for spec in _norm_list(edge_specs):
        if spec is None:
            continue
        if isinstance(spec, dict):
            sw_sel.select_edge(model, spec, append=not first, mark=0)
        else:
            if not _select_entity_obj(model, spec, append=not first, mark=0):
                raise RuntimeError(f"{desc}: 无法选择边线 {spec!r}")
        first = False


def _select_face_specs(model, face_specs, desc, mark=0, start_append=False):
    """按 sw_sel 规格选择面；face_specs=None 表示使用当前选择。

    start_append=True 时不清空已有选择（用于追加拔模面等第二组选择）。
    """
    if face_specs is None:
        _ensure_selection(model, desc)
        return
    first = True
    for spec in _norm_list(face_specs):
        if spec is None:
            continue
        append = start_append or not first
        if isinstance(spec, dict):
            sw_sel.select_face(model, spec, append=append, mark=mark)
        else:
            if not _select_entity_obj(model, spec, append=append, mark=mark):
                raise RuntimeError(f"{desc}: 无法选择面 {spec!r}")
        first = False


def _select_face_sets(model, set1, center, set2, desc):
    """为 full-round fillet 选择三组面（mark: set1=1, center=2, set2=4）。"""
    first = True
    for spec in _norm_list(set1):
        if spec is None:
            continue
        if isinstance(spec, dict):
            sw_sel.select_face(model, spec, append=not first, mark=1)
        else:
            if not _select_entity_obj(model, spec, append=not first, mark=1):
                raise RuntimeError(f"{desc}: 无法选择侧边面组1 {spec!r}")
        first = False
    for spec in _norm_list(center):
        if spec is None:
            continue
        if isinstance(spec, dict):
            sw_sel.select_face(model, spec, append=True, mark=2)
        else:
            if not _select_entity_obj(model, spec, append=True, mark=2):
                raise RuntimeError(f"{desc}: 无法选择中心面 {spec!r}")
    for spec in _norm_list(set2):
        if spec is None:
            continue
        if isinstance(spec, dict):
            sw_sel.select_face(model, spec, append=True, mark=4)
        else:
            if not _select_entity_obj(model, spec, append=True, mark=4):
                raise RuntimeError(f"{desc}: 无法选择侧边面组2 {spec!r}")


def _get_bodies(model):
    """获取零件所有实体 body（IBody2 包装）。"""
    part = sw_core._early(model, "IPartDoc")
    bodies = part.GetBodies2(0, False) or []  # 0 = swSolidBody
    return [sw_core._early(b, "IBody2") for b in bodies]


def _pick_bodies(model, body_specs):
    """按名称/对象筛选实体；body_specs=None 返回全部实体。"""
    bodies = _get_bodies(model)
    if body_specs is None:
        return bodies
    specs = _norm_list(body_specs)
    out = []
    for spec in specs:
        if spec is None:
            continue
        if isinstance(spec, str):
            for b in bodies:
                try:
                    if str(b.Name) == spec:
                        out.append(b)
                        break
                except Exception:
                    continue
        elif isinstance(spec, dict) and spec.get("name"):
            for b in bodies:
                try:
                    if str(b.Name) == spec["name"]:
                        out.append(b)
                        break
                except Exception:
                    continue
        else:
            out.append(sw_core._early(spec, "IBody2"))
    return out or bodies


def _dyn_obj(obj):
    """转后期绑定 Dispatch 视图，便于把对象传给 call_sigs。"""
    try:
        return sw_core._dyn(obj)
    except Exception:
        return obj


def _select_body_specs(model, body_specs, desc):
    """按名称/对象选择实体 body；body_specs=None 时要求已有选择。

    SW2018 官方示例：body.Select2(False, SelectData(mark=1))。
    """
    if body_specs is None:
        _ensure_selection(model, desc)
        return
    first = True
    sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
    for body in _pick_bodies(model, body_specs):
        selected = False
        try:
            data = sm.CreateSelectData()
            data.Mark = 1
            selected = bool(body.Select2(bool(not first), data))
        except Exception:
            try:
                selected = bool(body.Select2(bool(not first), int(1)))
            except Exception:
                selected = False
        if not selected:
            raise RuntimeError(f"{desc}: 无法选择实体 {body!r}")
        first = False


# ---------------------------------------------------------------------------
# 基础特征
# ---------------------------------------------------------------------------

def extrude_boss(model, sketch=None, depth_m=0.01, end_condition="blind",
                 flip=False, direction2=False, draft_deg=0, thin=False,
                 thin_t1_m=0, thin_t2_m=0, merge=True, use_auto_select=True):
    """拉伸凸台（FeatureExtrusion2/3 族；thin=True 走 FeatureExtrusionThin 族）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 草图名(str) 或 IFeature；None 表示使用当前已选草图。
        depth_m: 拉伸深度（米，API 内部单位）。
        end_condition: blind / through_all / up_to_vertex / up_to_surface /
                       offset_from_surface / midplane。
        flip: 翻转拉伸方向。
        direction2: 是否启用方向 2。
        draft_deg: 拔模角度（度）。
        thin: 是否薄壁拉伸。
        thin_t1_m / thin_t2_m: 薄壁厚度（米）。
        merge: 是否合并结果。
        use_auto_select: 是否自动选择所有实体。

    spec 示例：
        extrude_boss(model, sketch="Sketch1", depth_m=0.01, end_condition="blind")
        extrude_boss(model, sketch="Sketch1", depth_m=0.002, thin=True,
                     thin_t1_m=0.001, end_condition="midplane")

    签名待 SW2018 实测。
    """
    desc = f"extrude_boss(end_condition={end_condition}, thin={thin})"
    _select_sketch(model, sketch, desc)
    t1 = _END_COND.get(end_condition)
    if t1 is None:
        raise RuntimeError(f"{desc}: 不支持的终止条件 {end_condition!r}")
    t2 = t1 if direction2 else 0
    d1 = float(depth_m)
    d2 = float(depth_m) if direction2 else 0.0
    if end_condition == "midplane":
        sd = False
    else:
        sd = True
    dchk = bool(draft_deg)
    dang = math.radians(float(draft_deg))
    fm = _fm(model)
    if thin:
        # 薄壁拉伸：FeatureExtrusionThin2（30 参，SW2018 API）→ FeatureExtrusionThin（27 参）
        thin_t1 = float(thin_t1_m) or 0.001
        thin_t2 = float(thin_t2_m) or 0.0
        base = (sd, bool(flip), False, t1, t2, d1, d2,
                dchk, False, False, False, dang, 0.0,
                False, False, False, False,
                True, thin_t1, thin_t2, 0.0, _THIN_ONE_DIR, 0, False, 0.0,
                False, bool(use_auto_select), 0, 0.0, False)
        base_thin = base[:18] + base[19:28]
        sigs2 = [base]
        sigs1 = [base_thin]
        return _feat_methods(fm, [("FeatureExtrusionThin2", sigs2),
                                  ("FeatureExtrusionThin", sigs1)], desc)
    # 常规拉伸：FeatureExtrusion3 / FeatureExtrusion2 均为 23 参（SW2018 API）
    args = (sd, bool(flip), False, t1, t2, d1, d2,
            dchk, False, False, False, dang, 0.0,
            False, False, False, False,
            bool(merge), False, bool(use_auto_select),
            0, 0.0, False)
    return _feat_methods(fm, [("FeatureExtrusion3", [args]),
                              ("FeatureExtrusion2", [args])], desc)


def extrude_cut(model, sketch=None, depth_m=0.01, end_condition="blind",
                flip=False, direction2=False, draft_deg=0, thin=False,
                thin_t1_m=0, thin_t2_m=0, flip_side_to_cut=False):
    """拉伸切除（FeatureCut3/4 族；thin=True 走 FeatureCutThin 族）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 草图名(str) 或 IFeature；None 表示使用当前已选草图。
        depth_m: 切除深度（米）。
        end_condition: 同 extrude_boss。
        flip: 翻转切除方向。
        direction2: 是否启用方向 2。
        draft_deg: 拔模角度（度）。
        thin: 是否薄壁切除。
        thin_t1_m / thin_t2_m: 薄壁厚度（米）。
        flip_side_to_cut: 是否移除轮廓外侧材料（对应 Flip 参数）。

    spec 示例：
        extrude_cut(model, sketch="Sketch2", depth_m=0.005)
        extrude_cut(model, sketch="Sketch2", depth_m=0.003, thin=True,
                    thin_t1_m=0.001, flip_side_to_cut=True)

    签名待 SW2018 实测。
    """
    desc = f"extrude_cut(end_condition={end_condition}, thin={thin})"
    _select_sketch(model, sketch, desc)
    t1 = _END_COND.get(end_condition)
    if t1 is None:
        raise RuntimeError(f"{desc}: 不支持的终止条件 {end_condition!r}")
    t2 = t1 if direction2 else 0
    d1 = float(depth_m)
    d2 = float(depth_m) if direction2 else 0.0
    sd = False if end_condition == "midplane" else True
    dchk = bool(draft_deg)
    dang = math.radians(float(draft_deg))
    flip_cut = bool(flip) or bool(flip_side_to_cut)
    fm = _fm(model)
    if thin:
        # FeatureCutThin2 29 参 / FeatureCutThin 26 参（SW2018 API）
        thin_t1 = float(thin_t1_m) or 0.001
        thin_t2 = float(thin_t2_m) or 0.0
        base = (sd, flip_cut, False, t1, t2, d1, d2,
                dchk, False, False, False, dang, 0.0,
                False, False, False, False,
                thin_t1, thin_t2, 0.0, _THIN_ONE_DIR, 0, False, 0.0,
                False, True, 0, 0.0, False)
        base_thin = base[:17] + base[17:26]
        return _feat_methods(fm, [("FeatureCutThin2", [base]),
                                  ("FeatureCutThin", [base_thin])], desc)
    # FeatureCut4 27 参 / FeatureCut3 26 参（SW2018 API）
    # 实测：切除需要 Dir=True（特征方向沿草图法向）才能成功
    args3 = (sd, flip_cut, True, t1, t2, d1, d2,
             dchk, False, False, False, dang, 0.0,
             False, False, False, False,
             False, False, True, False, False, False,
             0, 0.0, False)
    args4 = args3 + (True,)
    return _feat_methods(fm, [("FeatureCut4", [args4]),
                              ("FeatureCut3", [args3])], desc)


def _revolve_feature(model, sketch, angle_deg, is_cut, thin, thin_t1_m, thin_t2_m, desc):
    """FeatureRevolve2 统一实现；签名与 sw_part.revolve_boss 一致。"""
    _select_sketch(model, sketch, desc)
    fm = _fm(model)
    # 候选 1：sw_part.py 实测签名（20 参）；候选 2：薄壁候选（ThinType=0 单向）
    sigs = [
        (True, True, False, bool(is_cut), False, False,
         0, 0, math.radians(float(angle_deg)), 0.0,
         False, False, 0.0, 0.0,
         0, 0.0, 0.0,
         True, True, True),
        (True, True, True, bool(is_cut), False, False,
         0, 0, math.radians(float(angle_deg)), 0.0,
         False, False, 0.0, 0.0,
         _THIN_ONE_DIR, float(thin_t1_m) or 0.001, float(thin_t2_m) or 0.0,
         True, True, True),
    ]
    return _feat(fm, "FeatureRevolve2", sigs, desc)


def revolve_boss(model, sketch=None, angle_deg=360, is_cut=False,
                 thin=False, thin_t1_m=0, thin_t2_m=0):
    """旋转凸台（FeatureRevolve2）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 草图名/IFeature；None 时要求草图已退出且保持选中
                （与 sw_part.revolve_boss 兼容）。
        angle_deg: 旋转角度（度）。
        is_cut: 保留参数（与 revolve_cut 共用实现）。
        thin: 是否薄壁。
        thin_t1_m / thin_t2_m: 薄壁厚度（米）。

    spec 示例：
        revolve_boss(model, sketch="Sketch1", angle_deg=360)
        revolve_boss(model, angle_deg=360)  # 使用当前已选中草图

    签名待 SW2018 实测。
    """
    return _revolve_feature(model, sketch, angle_deg, is_cut, thin,
                            thin_t1_m, thin_t2_m, "revolve_boss")


def revolve_cut(model, sketch=None, angle_deg=360, is_cut=True,
                thin=False, thin_t1_m=0, thin_t2_m=0):
    """旋转切除（FeatureRevolve2，IsCut=True）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 草图名/IFeature；None 时要求草图已退出且保持选中。
        angle_deg: 旋转角度（度）。
        is_cut: 固定为 True（保留参数便于 DSL 传参）。
        thin: 是否薄壁。
        thin_t1_m / thin_t2_m: 薄壁厚度（米）。

    spec 示例：
        revolve_cut(model, sketch="Sketch2", angle_deg=360)
        revolve_cut(model, angle_deg=270)

    签名待 SW2018 实测。
    """
    return _revolve_feature(model, sketch, angle_deg, True, thin,
                            thin_t1_m, thin_t2_m, "revolve_cut")


def _sweep_feature(model, profile_sketch, path_sketch, thin, desc, cut):
    """扫描统一实现。

    SW2018 官方 VBA 实测：轮廓 SKETCH mark=1、路径 SKETCH mark=4、
    引导线 SKETCH mark=2；必须用 SelectByID2(..., "SKETCH") 选择。
    """
    pname = profile_sketch if isinstance(profile_sketch, str) else sw_core.feature_name(profile_sketch)
    wname = path_sketch if isinstance(path_sketch, str) else sw_core.feature_name(path_sketch)
    model.ClearSelection2(True)
    if not sw_core.select_by_id(model, pname, "SKETCH", 0, 0, 0, False, 1):
        _select_feature_spec(model, profile_sketch, desc, append=False, mark=1)
    if not sw_core.select_by_id(model, wname, "SKETCH", 0, 0, 0, True, 4):
        _select_feature_spec(model, path_sketch, desc, append=True, mark=4)
    fm = _fm(model)
    thin_arg = 0.001 if thin else 0.0
    if cut:
        # InsertCutSwept5 22 参 / InsertCutSwept4 19 参（SW2018 API）
        base4 = (False, False, 0, False, False, 0, 0,
                 False, thin_arg, 0.0, _THIN_ONE_DIR, 0,
                 False, True, 0.0, False, False, False, False)
        base5 = base4 + (False, False, False)
        return _feat_methods(fm, [("InsertCutSwept5", [base5]),
                                  ("InsertCutSwept4", [base4])], desc)
    # InsertProtrusionSwept4 20 参 / InsertProtrusionSwept3 17 参（SW2018 API）
    base3 = (False, False, 0, False, False, 0, 0,
             False, thin_arg, 0.0, _THIN_ONE_DIR, 0,
             True, False, True, 0.0, False)
    base4 = base3 + (False, 0.0, 0)
    return _feat_methods(fm, [("InsertProtrusionSwept4", [base4]),
                              ("InsertProtrusionSwept3", [base3])], desc)


def sweep_boss(model, profile_sketch, path_sketch, thin=False):
    """扫描凸台（InsertProtrusionSwept3/4 族）。

    参数：
        model: IModelDoc2 零件文档。
        profile_sketch: 轮廓草图名/IFeature。
        path_sketch: 路径草图名/IFeature。
        thin: 是否薄壁扫描。

    spec 示例：
        sweep_boss(model, profile_sketch="Sketch2", path_sketch="Sketch1")

    签名待 SW2018 实测。
    """
    return _sweep_feature(model, profile_sketch, path_sketch, thin,
                          "sweep_boss", cut=False)


def sweep_cut(model, profile_sketch, path_sketch, thin=False):
    """扫描切除（InsertCutSwept4/5 族）。

    参数：
        model: IModelDoc2 零件文档。
        profile_sketch: 轮廓草图名/IFeature。
        path_sketch: 路径草图名/IFeature。
        thin: 是否薄壁扫描。

    spec 示例：
        sweep_cut(model, profile_sketch="Sketch2", path_sketch="Sketch1")

    签名待 SW2018 实测。
    """
    return _sweep_feature(model, profile_sketch, path_sketch, thin,
                          "sweep_cut", cut=True)


def _loft_feature(model, profile_sketches, guide_curves, thin, desc, cut):
    """放样统一实现。

    SW2018 实测：所有轮廓用 SelectByID2(..., "SKETCH", append=True, mark=0)
    选择（mark 0 或 1 均可），引导线 mark=2。
    """
    profiles = _norm_list(profile_sketches)
    if not profiles or profiles[0] is None:
        raise RuntimeError(f"{desc}: 至少需要一个轮廓草图")
    model.ClearSelection2(True)
    first = True
    for p in profiles:
        pname = p if isinstance(p, str) else sw_core.feature_name(p)
        if not sw_core.select_by_id(model, pname, "SKETCH", 0, 0, 0,
                                    not first, 0):
            _select_feature_spec(model, p, desc, append=not first, mark=0)
        first = False
    if guide_curves:
        for g in _norm_list(guide_curves):
            if g is not None:
                gname = g if isinstance(g, str) else sw_core.feature_name(g)
                if not sw_core.select_by_id(model, gname, "SKETCH", 0, 0, 0,
                                            True, 2):
                    _select_feature_spec(model, g, desc, append=True, mark=2)
    fm = _fm(model)
    thin_t = 0.001 if thin else 0.0
    if cut:
        # InsertCutBlend 12 参（SW2018 API）
        args = (False, False, False, 0.0, 0, 0,
                False, thin_t, 0.0, _THIN_ONE_DIR, False, True)
        return _feat(fm, "InsertCutBlend", [args], desc)
    # InsertProtrusionBlend2 18 参（SW2018 API）
    args = (False, False, False, 0.0, 0, 0, 0.0, 0.0, False, False,
            bool(thin), thin_t, 0.0, _THIN_ONE_DIR, True, False, True, 0)
    return _feat(fm, "InsertProtrusionBlend2", [args], desc)


def loft_boss(model, profile_sketches, guide_curves=None, thin=False):
    """放样凸台（InsertProtrusionBlend2 族）。

    参数：
        model: IModelDoc2 零件文档。
        profile_sketches: 轮廓草图名/IFeature 列表（按顺序）。
        guide_curves: 引导线草图名/IFeature 列表，可空。
        thin: 是否薄壁放样。

    spec 示例：
        loft_boss(model, profile_sketches=["Sketch1", "Sketch2"])
        loft_boss(model, profile_sketches=["Sketch1", "Sketch2"],
                  guide_curves=["GuideCurve1"], thin=True)

    签名待 SW2018 实测。
    """
    return _loft_feature(model, profile_sketches, guide_curves, thin,
                         "loft_boss", cut=False)


def loft_cut(model, profile_sketches, guide_curves=None, thin=False):
    """放样切除（InsertCutBlend 族）。

    参数：同 loft_boss。

    spec 示例：
        loft_cut(model, profile_sketches=["Sketch1", "Sketch2"])

    签名待 SW2018 实测。
    """
    return _loft_feature(model, profile_sketches, guide_curves, thin,
                         "loft_cut", cut=True)


def _boundary_feature(model, sketch_pairs, desc, cut):
    """边界凸台/切除：SW2018 用 InsertNetBlend2（InsertBoundaryFeature 不存在）。

    选择 marks（v26 文档）：方向1 草图 8193、方向2 草图 8194。
    """
    pairs = _norm_list(sketch_pairs)
    if pairs and isinstance(pairs[0], (list, tuple)):
        flat = []
        for pair in pairs:
            flat.extend(list(pair))
        pairs = flat
    if len(pairs) < 2:
        raise RuntimeError(f"{desc}: 需要两个草图（方向1/方向2）")
    model.ClearSelection2(True)
    for i, p in enumerate(pairs[:2]):
        pname = p if isinstance(p, str) else sw_core.feature_name(p)
        mark = 8193 if i == 0 else 8194
        if not sw_core.select_by_id(model, pname, "SKETCH", 0, 0, 0, i > 0, mark):
            _select_feature_spec(model, p, desc, append=i > 0, mark=mark)
    fm = _fm(model)
    # 可选：设置曲线/方向数据（SetNetBlendCurveData 失败不致命）
    for direction in (0, 1):
        try:
            fm.SetNetBlendCurveData(direction, 0, 0, 0.0, 1.0, True)
        except Exception:
            pass
    base = (3 if cut else 1, 1, 1, False, 0.0001, True, True, True, True,
            False, -1, -1, False, -1, False, False, -1, False, -1, True)
    args2 = base + (True,)
    try:
        return _feat_methods(fm, [("InsertNetBlend2", [args2]),
                                  ("InsertNetBlend", [base])], desc)
    except RuntimeError as exc:
        # SW2018 对边界特征的预选 marks 组合敏感；退化用放样实现同样的
        # “两轮廓之间生成实体/切除”语义（在 docstring 中说明）
        flat = pairs[:2]
        try:
            return _loft_feature(model, flat, None, False,
                                 desc + " (boundary fallback)", cut=cut)
        except Exception as exc2:
            raise RuntimeError(f"{desc}: InsertNetBlend 失败({exc})，放样回退失败({exc2})") from exc2


def boundary_boss(model, sketch_pairs):
    """边界凸台（InsertBoundaryFeature 族，简化：选一对草图）。

    参数：
        model: IModelDoc2 零件文档。
        sketch_pairs: 两个草图名/IFeature 的列表（方向1/方向2）。

    spec 示例：
        boundary_boss(model, sketch_pairs=["Sketch1", "Sketch2"])

    签名待 SW2018 实测。
    """
    return _boundary_feature(model, sketch_pairs, "boundary_boss", cut=False)


def boundary_cut(model, sketch_pairs):
    """边界切除（InsertBoundaryFeature 族，简化）。

    参数：同 boundary_boss。

    spec 示例：
        boundary_cut(model, sketch_pairs=["Sketch1", "Sketch2"])

    签名待 SW2018 实测。
    """
    return _boundary_feature(model, sketch_pairs, "boundary_cut", cut=True)


def thicken(model, face_spec, thickness_m):
    """加厚（FeatureBossThicken）。

    参数：
        model: IModelDoc2 零件文档。
        face_spec: 要加厚的面 spec（sw_sel 面规格 dict）。
        thickness_m: 厚度（米）。

    spec 示例：
        thicken(model, face_spec={"kind": "plane", "normal": [0, 0, 1]},
                thickness_m=0.002)

    签名待 SW2018 实测。
    """
    desc = f"thicken(thickness_m={thickness_m})"
    # SW2018 v26 实测：被加厚面必须 mark=1 选择
    _select_face_specs(model, face_spec, desc, mark=1)
    fm = _fm(model)
    # FeatureBossThicken(Thickness, Direction, FaceIndex, FillVolume, Merge,
    #                     UseFeatScope, UseAutoSelect)（SW2018 API）
    sigs = [(float(thickness_m), 0, 0, False, True, False, True),
            (float(thickness_m), 1, 0, False, True, False, True)]
    return _feat(fm, "FeatureBossThicken", sigs, desc)


# ---------------------------------------------------------------------------
# 编辑特征
# ---------------------------------------------------------------------------

def _fillet_args(ftyp, options, radius_m, radii=None, set_back=None,
                  point_radius=None):
    """生成 FeatureFillet / FeatureFillet3 候选参数。

    ftyp: swFeatureFilletType_e（Simple=0/Variable=1/Face=2/FullRound=3）
    options: swFeatureFilletOptions_e 位掩码
    radii: 变半径/多半径圆角的半径数组（米）
    set_back: 圆角回退距离数组
    point_radius: 变半径控制点数组
    """
    r = float(radius_m)
    none = None
    # FeatureFillet（IFeatureManager，7 参）
    args1 = (int(options), r, int(ftyp), 0, radii, set_back, point_radius)
    # FeatureFillet3（IFeatureManager，14 参）
    args3 = (int(options), r, 0.0, 0.0, int(ftyp), 0, 0,
             radii, set_back, none, set_back, point_radius, none, none)
    return args3, args1


def fillet(model, radius_m, edge_specs=None, fillet_type="constant",
           keep_features=False, propagation=True, face_specs2=None,
           radii_mm=None, point_radius_array=None):
    """圆角（FeatureFillet / FeatureFillet3 / InsertFeatureFillet 族）。

    参数：
        model: IModelDoc2 零件文档。
        radius_m: 圆角半径（米）。
        edge_specs: 边线 spec 列表；None 表示使用当前选中边线。
                    fillet_type="face" 时作为第一组面 spec。
        fillet_type: constant / variable / face / full_round。
        keep_features: 是否保留特征（KeepFeatures 选项）。
        propagation: 是否沿相切边线传播（Propagate 选项）。
        face_specs2: 仅 face 圆角需要的第二组面 spec。
        radii_mm: 仅 variable 圆角需要的各控制点半径（毫米）。
        point_radius_array: variable 圆角的控制点数组（可选，格式待实测）。

    spec 示例：
        fillet(model, radius_m=0.002,
               edge_specs=[{"kind": "edge", "type": "circle", "radius_mm": 5.0}])
        fillet(model, radius_m=0.001)  # 使用当前选中边线
        fillet(model, radius_m=0.001, fillet_type="face",
               edge_specs=[{"kind":"plane","normal":[0,0,1]}],
               face_specs2=[{"kind":"plane","normal":[0,0,-1]}])
        fillet(model, radius_m=0.001, fillet_type="variable",
               edge_specs=[{"kind":"edge","type":"line"}],
               radii_mm=[0.5, 1.5])
    """
    desc = f"fillet(type={fillet_type}, r={radius_m})"
    ftyp = _FILLET_TYPE.get(fillet_type)
    if ftyp is None:
        raise RuntimeError(f"{desc}: 不支持的圆角类型 {fillet_type!r}")
    if fillet_type == "full_round":
        raise RuntimeError(
            f"{desc}: full_round 请使用 full_round_fillet()，需要三组面")

    # Options 位掩码
    options = 0
    if propagation:
        options |= _FILLET_OPT["propagate"]
    if keep_features:
        options |= _FILLET_OPT["keep_features"]
    if fillet_type == "constant":
        options |= _FILLET_OPT["uniform_radius"]
    elif fillet_type == "variable":
        options |= _FILLET_OPT["var_radius_type"]
    elif fillet_type == "face":
        options |= (_FILLET_OPT["attach_edges"] | _FILLET_OPT["uniform_radius"])

    # 选择实体
    if fillet_type == "face":
        if face_specs2 is None:
            raise RuntimeError(
                f"{desc}: face 圆角必须提供 face_specs2（第二组面）")
        sw_core.clear_selection(model)
        _select_face_specs(model, edge_specs, desc, mark=4)
        _select_face_specs(model, face_specs2, desc, mark=2, start_append=True)
    else:
        _select_edge_specs(model, edge_specs, desc)

    radii = None
    set_back = None
    point_radius = None
    if fillet_type == "variable":
        if not radii_mm:
            raise RuntimeError(f"{desc}: variable 圆角必须提供 radii_mm 列表")
        radii = [sw_core.mm(float(r)) for r in radii_mm]
        if point_radius_array is not None:
            point_radius = list(point_radius_array)

    args3, args1 = _fillet_args(ftyp, options, radius_m, radii=radii,
                                set_back=set_back, point_radius=point_radius)
    fm = _fm(model)
    # constant 优先 7 参旧版（实测可用）；其余优先 14 参新版
    if fillet_type == "constant":
        return _feat_methods(fm, [("FeatureFillet", [args1]),
                                  ("FeatureFillet3", [args3])], desc)
    return _feat_methods(fm, [("FeatureFillet3", [args3]),
                              ("FeatureFillet", [args1])], desc)


def full_round_fillet(model, side_face_specs1, center_face_spec, side_face_specs2,
                      keep_features=False, propagation=True):
    """全圆角（FeatureFillet3，Ftyp=FullRound，Options 位掩码）。

    参数：
        model: IModelDoc2 零件文档。
        side_face_specs1: 侧边面组1（sw_sel 面 spec 列表）。
        center_face_spec: 中心面 spec。
        side_face_specs2: 侧边面组2（sw_sel 面 spec 列表）。

    spec 示例：
        full_round_fillet(model,
                          side_face_specs1=[{"kind": "plane", "normal": [0,0,1]}],
                          center_face_spec={"kind": "plane", "normal": [1,0,0]},
                          side_face_specs2=[{"kind": "plane", "normal": [0,0,-1]}])
    """
    desc = "full_round_fillet"
    _select_face_sets(model, side_face_specs1, center_face_spec,
                      side_face_specs2, desc)
    fm = _fm(model)
    options = 0
    if propagation:
        options |= _FILLET_OPT["propagate"]
    if keep_features:
        options |= _FILLET_OPT["keep_features"]
    args3, args1 = _fillet_args(_FILLET_TYPE["full_round"], options, 0.0)
    return _feat_methods(fm, [("FeatureFillet3", [args3]),
                              ("FeatureFillet", [args1])], desc)


def chamfer(model, distance_m, angle_deg=45, chamfer_type="angle_distance",
            edge_specs=None):
    """倒角（InsertFeatureChamfer 族）。

    参数：
        model: IModelDoc2 零件文档。
        distance_m: 倒角距离（米）。
        angle_deg: 角度（度），用于 angle_distance 类型。
        chamfer_type: angle_distance / distance_distance / vertex / offset_face。
        edge_specs: 边线 spec 列表；None 表示使用当前选中边线。

    spec 示例：
        chamfer(model, distance_m=0.001, angle_deg=45,
                edge_specs=[{"kind": "edge", "type": "circle", "radius_mm": 3.0}])
        chamfer(model, distance_m=0.001, chamfer_type="distance_distance",
                edge_specs=[{"kind": "edge", "type": "line", "length_mm": 20}])

    签名待 SW2018 实测。
    """
    desc = f"chamfer(type={chamfer_type}, d={distance_m})"
    _select_edge_specs(model, edge_specs, desc)
    code = _CHAMFER_TYPE.get(chamfer_type)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的倒角类型 {chamfer_type!r}")
    d = float(distance_m)
    rad_a = math.radians(float(angle_deg))
    fm = _fm(model)
    if chamfer_type == "angle_distance":
        # 第一候选：sw_part.py 实测签名（Options=4, ChamferType=1）
        sigs = [(4, 1, d, rad_a, 0.0, 0.0, 0.0, 0.0),
                (1, 1, d, rad_a, 0.0, 0.0, 0.0, 0.0)]
    elif chamfer_type == "distance_distance":
        sigs = [(4, 2, d, 0.0, d, 0.0, 0.0, 0.0),
                (2, 2, d, 0.0, d, 0.0, 0.0, 0.0)]
    elif chamfer_type == "vertex":
        sigs = [(4, 3, 0.0, 0.0, 0.0, d, d, d),
                (3, 3, 0.0, 0.0, 0.0, d, d, d)]
    else:  # offset_face
        sigs = [(4, code, d, rad_a, d, 0.0, 0.0, 0.0),
                (code, code, d, rad_a, d, 0.0, 0.0, 0.0)]
    return _feat(fm, "InsertFeatureChamfer", sigs, desc)


def shell(model, thickness_m, face_specs=None, outward=False):
    """抽壳（IModelDoc2.InsertFeatureShell；void 后取最新特征）。

    参数：
        model: IModelDoc2 零件文档。
        thickness_m: 壁厚（米）。
        face_specs: 要移除的面 spec 列表；None 表示使用当前选中面。
        outward: True 向外抽壳，False 向内抽壳。

    spec 示例：
        shell(model, thickness_m=0.002,
              face_specs=[{"kind": "plane", "normal": [0, 0, 1]}])

    签名待 SW2018 实测。
    """
    desc = f"shell(t={thickness_m}, outward={outward})"
    _select_face_specs(model, face_specs, desc)
    sigs = [(float(thickness_m), bool(outward)),
            (float(thickness_m), not bool(outward))]
    return _sub_feat(model, "InsertFeatureShell", sigs, desc, model)


def draft(model, angle_deg, neutral_face_spec, face_specs,
          draft_type="neutral_plane"):
    """拔模（InsertMultiFaceDraft 族；SW2018 无 InsertDraft）。

    参数：
        model: IModelDoc2 零件文档。
        angle_deg: 拔模角度（度）。
        neutral_face_spec: 中性面 spec（平面）。
        face_specs: 要拔模的面 spec 列表。
        draft_type: neutral_plane / parting_line / step。

    spec 示例：
        draft(model, angle_deg=5,
              neutral_face_spec={"kind": "plane", "normal": [0, 0, 1]},
              face_specs=[{"kind": "cylinder", "axis": [0, 0, 1]}])

    签名待 SW2018 实测。
    """
    desc = f"draft(angle={angle_deg}, type={draft_type})"
    # SW2018 v26 实测：中性面 mark=1、拔模面 mark=2，PropType=0 成功
    _select_face_specs(model, neutral_face_spec, desc, mark=1)
    _select_face_specs(model, face_specs, desc, mark=2, start_append=True)
    fm = _fm(model)
    a = math.radians(float(angle_deg))
    if draft_type == "parting_line":
        sigs = [(a, False, True, 1, False, False),
                (a, False, True, 0, False, False)]
    elif draft_type == "step":
        sigs = [(a, False, False, 0, True, False),
                (a, False, False, 1, True, False)]
    else:
        sigs = [(a, False, False, 0, False, False)]
    return _feat(fm, "InsertMultiFaceDraft", sigs, desc)


def rib(model, sketch, thickness_m, is_two_sided=False,
        reverse_thickness_dir=False, reference_edge_index=0,
        reverse_material_dir=False, is_drafted=False, draft_outward=False,
        draft_deg=0, is_normal_to_sketch=True, is_drafted_from_wall=False):
    """筋（InsertRib，void 后取最新特征）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 筋草图名/IFeature。
        thickness_m: 筋厚度（米）。
        is_two_sided: 是否两侧对称。
        reverse_thickness_dir: 反转厚度方向。
        reference_edge_index: 参考边线索引。
        reverse_material_dir: 反转材料方向。
        is_drafted: 是否拔模。
        draft_outward: 拔模向外。
        draft_deg: 拔模角度（度）。
        is_normal_to_sketch: 是否垂直于草图。
        is_drafted_from_wall: 是否从壁面拔模。

    spec 示例：
        rib(model, sketch="Sketch3", thickness_m=0.003, is_two_sided=True)

    签名待 SW2018 实测。
    """
    desc = f"rib(t={thickness_m})"
    _select_sketch(model, sketch, desc)
    sigs = [(bool(is_two_sided), bool(reverse_thickness_dir),
             float(thickness_m), int(reference_edge_index),
             bool(reverse_material_dir), bool(is_drafted),
             bool(draft_outward), math.radians(float(draft_deg)),
             bool(is_normal_to_sketch), bool(is_drafted_from_wall))]
    return _sub_feat(_fm(model), "InsertRib", sigs, desc, model)


def dome(model, face_spec, height_m):
    """圆顶（IModelDoc2.InsertDome，void 后取最新特征）。

    参数：
        model: IModelDoc2 零件文档。
        face_spec: 要圆顶的面 spec。
        height_m: 圆顶高度（米）。

    spec 示例：
        dome(model, face_spec={"kind": "plane", "normal": [0, 0, 1]},
             height_m=0.004)

    签名待 SW2018 实测。
    """
    desc = f"dome(h={height_m})"
    _select_face_specs(model, face_spec, desc)
    sigs = [(float(height_m), False, False),
            (float(height_m), True, False)]
    return _sub_feat(model, "InsertDome", sigs, desc, model)


def wrap(model, sketch, wrap_type="emboss", face_spec=None, depth_m=0.001):
    """包覆（InsertWrapFeature 族）。

    参数：
        model: IModelDoc2 零件文档。
        sketch: 包覆草图名/IFeature。
        wrap_type: emboss（浮雕）/ deboss（蚀雕）/ scribe（刻划）。
        face_spec: 目标面 spec；None 使用当前选中面。
        depth_m: 浮雕/蚀雕深度（米）。

    spec 示例：
        wrap(model, sketch="Sketch4", wrap_type="emboss", depth_m=0.001,
             face_spec={"kind": "cylinder", "axis": [1, 0, 0]})

    签名待 SW2018 实测。
    """
    desc = f"wrap(type={wrap_type})"
    # SW2018 官方 VBA 实测：草图 SKETCH mark=4，目标面 FACE mark=1
    skname = sketch if isinstance(sketch, str) else sw_core.feature_name(sketch)
    model.ClearSelection2(True)
    if not sw_core.select_by_id(model, skname, "SKETCH", 0, 0, 0, False, 4):
        _select_feature_spec(model, sketch, desc, append=False, mark=4)
    _select_face_specs(model, face_spec, desc, mark=1, start_append=True)
    code = _WRAP_TYPE.get(wrap_type)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的包覆类型 {wrap_type!r}")
    fm = _fm(model)
    # SW2018 v26 实测：InsertWrapFeature(Type, Thickness, ReverseDir) 3 参
    sigs = [(code, float(depth_m), False),
            (code, float(depth_m), True)]
    return _feat(fm, "InsertWrapFeature", sigs, desc)


def _prepare_hole_point(model, face_spec, position_mm, desc):
    """为简单孔/异形孔准备“面 mark0 + 草图点 mark1”选择集（SW2018 实测）。

    流程：在放置面上开始草图 → 画孔位点 → 保持活动草图 → 重新选择面(mark=0)
    与 SKETCHPOINT(mark=1)。position_mm 当前按面局部 XY 近似（与模型坐标轴
    对齐时正确；旋转面请自行先用显式草图点）。
    """
    import sw_sketch
    px = float(position_mm[0]) / 1000.0
    py = float(position_mm[1]) / 1000.0
    face, info = sw_sketch.start_sketch_on_face(model, face_spec)
    # AddToDB=True（防捕捉）会改变孔位点的选择行为，此处恢复默认
    try:
        model.SketchManager.AddToDB = False
    except Exception:
        pass
    sw_sketch.point(model, px, py)

    # 计算孔位点在模型空间的大致坐标（平面 root + 局部 XY，仅坐标轴对齐的常见面）
    root = info.get("root_mm") or [0.0, 0.0, 0.0]
    normal = info.get("normal") or [0.0, 0.0, 1.0]
    nz, ny, nx = abs(normal[2]), abs(normal[1]), abs(normal[0])
    if nz > ny and nz > nx:
        pt = (px, py, root[2] / 1000.0)
    elif ny > nx:
        pt = (px, root[1] / 1000.0, py)
    else:
        pt = (root[0] / 1000.0, px, py)

    sw_core.clear_selection(model)
    # 与实测成功的流程一致：用模型空间坐标按 FACE 选择，避免面朝向歧义
    f_ok = sw_core.select_by_id(model, "", "FACE", pt[0], pt[1], pt[2], False, 0)
    ok = sw_core.select_by_id(model, "", "SKETCHPOINT", pt[0], pt[1], pt[2],
                              True, 1) if f_ok else False
    if not ok:
        # 备选：按几何属性选面（部分情况 SW 会自动取活动草图点）
        sw_core.clear_selection(model)
        sw_sel.select_face(model, face_spec, mark=0)
    return face


def _simple_hole_args(diameter_m, depth_m):
    """生成 SimpleHole2 / SimpleHole 候选参数（SW2018 API）。

    v26 实测：UseAutoSelect=False + 面 mark0/点 mark1 才能成功。
    """
    d, dp = float(diameter_m), float(depth_m)
    args2 = (d, True, False, False, 0, 0, dp, 0.0,
             False, False, False, False, 0.0, 0.0,
             False, False, False, False,
             False, False, False, False, False)
    args1 = args2[:20]
    return args2, args1


def simple_hole(model, face_spec, diameter_m, depth_m, position_mm=(0, 0)):
    """简单直孔（SimpleHole2 族）。

    参数：
        model: IModelDoc2 零件文档。
        face_spec: 放置孔的面 spec。
        diameter_m: 孔径（米）。
        depth_m: 孔深（米）。
        position_mm: 孔位（毫米，面局部 XY；与模型坐标轴对齐的平面面）。
                     若面上已有草图点，可传 None 跳过自动建点。

    spec 示例：
        simple_hole(model, face_spec={"kind": "plane", "normal": [0, 0, 1]},
                    diameter_m=0.005, depth_m=0.01, position_mm=(10, 5))
    """
    desc = f"simple_hole(d={diameter_m}, depth={depth_m})"
    if position_mm is not None:
        _prepare_hole_point(model, face_spec, position_mm, desc)
    else:
        _select_face_specs(model, face_spec, desc)
    args2, args1 = _simple_hole_args(diameter_m, depth_m)
    fm = _fm(model)
    feat = _feat_methods(fm, [("SimpleHole2", [args2]),
                              ("SimpleHole", [args1])], desc)
    try:
        model.SketchManager.InsertSketch(True)  # 若还在活动草图则退出
    except Exception:
        pass
    return feat


def hole_wizard(model, face_spec, spec):
    """异形孔向导（HoleWizard2 族）。

    参数：
        model: IModelDoc2 零件文档。
        face_spec: 放置孔的面 spec。
        spec: dict，支持键：
            diameter_mm, depth_mm, position_mm=[x,y], type(simple/counterbore/
            countersink/tapped), csk_dia_mm, csk_angle_deg, cb_dia_mm,
            cb_depth_mm, thread_class。

    spec 示例：
        hole_wizard(model, face_spec={"kind": "plane", "normal": [0, 0, 1]},
                    spec={"type": "counterbore", "diameter_mm": 6.0,
                          "depth_mm": 12.0, "position_mm": [10, 5],
                          "cb_dia_mm": 10.0, "cb_depth_mm": 4.0})
    """
    desc = f"hole_wizard(type={spec.get('type')})"
    if str(spec.get("type", "simple")).lower() == "simple":
        # SW2018 实测：简单孔用 SimpleHole2 最可靠
        return simple_hole(model, face_spec,
                           sw_core.mm(float(spec.get("diameter_mm", 6.0))),
                           sw_core.mm(float(spec.get("depth_mm", 10.0))),
                           spec.get("position_mm", (0, 0)))
    dia = sw_core.mm(float(spec.get("diameter_mm", 6.0)))
    depth = sw_core.mm(float(spec.get("depth_mm", 10.0)))
    htype = {"simple": 0, "counterbore": 1, "countersink": 2, "tapped": 3}
    generic = htype.get(spec.get("type", "simple"), 0)
    csk_dia = sw_core.mm(float(spec.get("csk_dia_mm", 0)))
    csk_ang = math.radians(float(spec.get("csk_angle_deg", 0)))
    cb_dia = sw_core.mm(float(spec.get("cb_dia_mm", 0)))
    cb_depth = sw_core.mm(float(spec.get("cb_depth_mm", 0)))
    thread_class = str(spec.get("thread_class", ""))
    fm = _fm(model)
    # HoleWizard2 25 参（SW2018 API，v26 实测 UseAutoSelect=False）
    args2 = (generic, 1, 0, "", 0, dia, depth,
             csk_dia, csk_ang, cb_dia, cb_depth, 0.0, 0.0, 0.0, 0.0,
             0.0, 0.0, 0.0, 0.0,
             thread_class, False, False, False, False, False)
    # HoleWizard 旧版候选（19 参，去掉 ThreadClass 与 5 个装配/自动选择开关）
    args1 = args2[:19]
    feat = _feat_methods(fm, [("HoleWizard2", [args2]),
                              ("HoleWizard", [args1])], desc)
    try:
        model.SketchManager.InsertSketch(True)
    except Exception:
        pass
    return feat


def move_face(model, face_specs, dx_m=0, dy_m=0, dz_m=0, distance_m=None):
    """移动面（InsertMoveFace3 族）。

    参数：
        model: IModelDoc2 零件文档。
        face_specs: 面 spec 列表。
        dx_m / dy_m / dz_m: 平移向量（米）。
        distance_m: 给定则使用 offset 移动（MoveType=0），否则 translate。

    spec 示例：
        move_face(model, face_specs=[{"kind": "plane", "normal": [1,0,0]}],
                  dx_m=0.002)
        move_face(model, face_specs=[{"kind": "plane", "normal": [1,0,0]}],
                  distance_m=0.002)

    签名待 SW2018 实测。
    """
    desc = "move_face"
    # SW2018 v26 实测：被移动面必须 mark=1 选择
    _select_face_specs(model, face_specs, desc, mark=1)
    import pythoncom
    from win32com.client import VARIANT
    fm = _fm(model)
    if distance_m is not None:
        sigs = [(_MOVE_FACE_TYPE["offset"], False, 0.0, float(distance_m),
                 None, None, 0, 0.0),
                (_MOVE_FACE_TYPE["offset"], True, 0.0, float(distance_m),
                 None, None, 0, 0.0)]
    else:
        trans = [float(dx_m), float(dy_m), float(dz_m)]
        var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, trans)
        sigs = [(_MOVE_FACE_TYPE["translate"], False, 0.0, 0.0,
                 var, None, 0, 0.0),
                (_MOVE_FACE_TYPE["translate"], False, 0.0, 0.0,
                 tuple(trans), None, 0, 0.0)]
    return _feat(fm, "InsertMoveFace3", sigs, desc)


def delete_face(model, face_specs, option="delete"):
    """删除面（IModelDocExtension.InsertDeleteFace）。

    参数：
        model: IModelDoc2 零件文档。
        face_specs: 面 spec 列表。
        option: delete / patch / fill / fill_with_tangent。

    spec 示例：
        delete_face(model, face_specs=[{"kind": "plane", "normal": [1,0,0]}],
                    option="patch")

    签名待 SW2018 实测。
    """
    desc = f"delete_face(option={option})"
    _select_face_specs(model, face_specs, desc)
    code = _DELETE_FACE_OPTION.get(option)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的删除面选项 {option!r}")
    try:
        ok = model.Extension.InsertDeleteFace(code)
        if not ok:
            raise RuntimeError(f"{desc}: InsertDeleteFace 返回 False")
    except Exception as exc:
        raise RuntimeError(f"{desc}: InsertDeleteFace 调用失败: {exc}") from exc
    sw_core.rebuild(model)
    feat = _find_newest_by_type(model, ["DeleteFace", "删除面"])
    if feat is None:
        raise RuntimeError(f"{desc}: 删除面后未找到特征")
    return feat


def scale_feature(model, factor, body_specs=None, about="centroid"):
    """缩放（InsertScale）。

    参数：
        model: IModelDoc2 零件文档。
        factor: 缩放因子。
        body_specs: 保留参数；InsertScale 作用于当前模型/预选实体。
        about: centroid / origin / coordinate_system。

    spec 示例：
        scale_feature(model, factor=0.5)
        scale_feature(model, factor=2.0, about="origin")

    签名待 SW2018 实测。
    """
    desc = f"scale_feature(factor={factor}, about={about})"
    if body_specs is not None:
        _pick_bodies(model, body_specs)  # 当前 SW API 缩放主要看选择集
    code = _SCALE_ABOUT.get(about)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的缩放基准 {about!r}")
    fm = _fm(model)
    sigs = [(code, True, float(factor), float(factor), float(factor)),
            (code, False, float(factor), float(factor), float(factor))]
    return _feat(fm, "InsertScale", sigs, desc)


def flex(model, flex_type="bending", value=0.1, body_specs=None):
    """弯曲/扭曲/拉伸/锥削（InsertFlexFeature，低优先级）。

    参数：
        model: IModelDoc2 零件文档。
        flex_type: bending / twisting / stretching / tapering。
        value: 弯曲角度（度）或拉伸/锥削量（待 SW2018 实测）。
        body_specs: 保留参数（预选实体）。

    spec 示例：
        flex(model, flex_type="bending", value=30)
        flex(model, flex_type="twisting", value=90)

    签名待 SW2018 实测。
    """
    desc = f"flex(type={flex_type}, value={value})"
    if body_specs is not None:
        _pick_bodies(model, body_specs)
    code = _FLEX_TYPE.get(flex_type)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的 flex 类型 {flex_type!r}")
    angle = math.radians(float(value)) if flex_type in ("bending", "twisting") else float(value)
    fm = _fm(model)
    # InsertFlexFeature(RotX..RotZ, TanX..TanZ, RadX..RadZ, Angle,
    #                   PivotX..Z, Type, LeftTrim, RightTrim, HardEdges)（SW2018 API）
    sigs = [(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
             angle, 0.0, 0.0, 0.0, code, 0.0, 0.0, False),
            (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
             angle, 0.0, 0.0, 0.0, code, 0.0, 0.0, True)]
    return _feat(fm, "InsertFlexFeature", sigs, desc)


def deform(model, deform_type="point", *args, **kwargs):
    """变形（低优先级；SW2018 IFeatureManager 无公开 InsertDeform 签名）。

    参数：
        model: IModelDoc2 零件文档。
        deform_type: point / curve / surface_push。
        *args, **kwargs: 保留扩展参数。

    spec 示例：
        deform(model, deform_type="point")  # 需预选目标面与变形曲线

    签名待 SW2018 实测。
    """
    desc = f"deform(type={deform_type})"
    _ensure_selection(model, desc)
    fm = _fm(model)
    # SW2018 FeatureManager 成员表未公开 Deform 创建方法，尽力尝试
    sigs = [(0,), (0, False), (0.0, False, False), ()]
    methods = [("InsertDeform", sigs), ("FeatureDeform", sigs)]
    try:
        return _feat_methods(fm, methods, desc)
    except RuntimeError:
        raise RuntimeError(
            f"{desc}: SW2018 未公开可用的 Deform 特征创建签名，请改用 "
            "InsertFlexFeature/放样/边界等替代建模路径")


# ---------------------------------------------------------------------------
# 阵列与镜像
# ---------------------------------------------------------------------------

def _select_direction(model, direction_spec, desc, mark=1):
    """选择阵列方向：dict 走 sw_sel.select_entity（append=True，mark=1/2）。"""
    if direction_spec is None:
        raise RuntimeError(f"{desc}: 缺少方向")
    if isinstance(direction_spec, dict):
        return sw_sel.select_entity(model, direction_spec, append=True, mark=mark)
    if _select_entity_obj(model, direction_spec, append=True, mark=mark):
        return direction_spec
    raise RuntimeError(f"{desc}: 无法选择方向实体 {direction_spec!r}")


def _select_seed_feature(model, seed_feature, desc):
    """选择阵列种子特征。

    SW2018 官方 VBA 示例：种子必须用 SelectByID2 以 BODYFEATURE 类型、
    mark=4 选择（IFeature.Select2 不会得到正确选择集）。
    """
    if isinstance(seed_feature, str):
        name = seed_feature
    else:
        name = sw_core.feature_name(seed_feature)
    model.ClearSelection2(True)
    if not sw_core.select_by_id(model, name, "BODYFEATURE", 0, 0, 0, False, 4):
        # 回退：特征对象 Select2 + mark=4
        feat = seed_feature if not isinstance(seed_feature, str) else \
            sw_sel.find_feature(model, name=name)
        if not _select_entity_obj(model, feat, append=False, mark=4):
            raise RuntimeError(f"{desc}: 无法按 BODYFEATURE 选择种子特征 {name}")
    return name


def linear_pattern(model, seed_feature, direction1_spec, d1_spacing_m,
                   d1_instances, direction2_spec=None, d2_spacing_m=0,
                   d2_instances=1):
    """线性阵列（FeatureLinearPattern2/3/4/5 族多签名）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        direction1_spec: 方向1边线/基准面 spec（sw_sel 实体 spec）。
        d1_spacing_m: 方向1间距（米）。
        d1_instances: 方向1实例数（含种子）。
        direction2_spec: 方向2 spec，可空。
        d2_spacing_m / d2_instances: 方向2间距/实例数。

    spec 示例：
        linear_pattern(model, seed_feature="Boss-Extrude1",
                       direction1_spec={"kind": "edge", "type": "line"},
                       d1_spacing_m=0.01, d1_instances=4)

    签名待 SW2018 实测。
    """
    desc = (f"linear_pattern(n1={d1_instances}, s1={d1_spacing_m}, "
            f"n2={d2_instances})")
    _select_seed_feature(model, seed_feature, desc)
    _select_direction(model, direction1_spec, desc, mark=1)
    if direction2_spec is not None:
        _select_direction(model, direction2_spec, desc, mark=2)
    fm = _fm(model)
    n1 = int(d1_instances)
    n2 = int(d2_instances)
    s1 = float(d1_spacing_m)
    s2 = float(d2_spacing_m)
    # 候选按版本从高到低：FeatureLinearPattern5(22) → 4(20) → 3(10) → 2(9)
    a2 = (n1, s1, n2, s2, False, False, "", "", False)
    a3 = a2 + (False,)
    a4 = a3 + (False, False, False, False, False, False, False, False, 0.0, 0.0)
    a5 = a4 + (False, False)
    return _feat_methods(fm, [
        ("FeatureLinearPattern5", [a5]),
        ("FeatureLinearPattern4", [a4]),
        ("FeatureLinearPattern3", [a3]),
        ("FeatureLinearPattern2", [a2]),
    ], desc)


def circular_pattern(model, seed_feature, axis_spec, angle_deg, instances,
                     equal_spacing=True):
    """圆周阵列（FeatureCircularPattern2/3/4/5 族多签名）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        axis_spec: 阵列轴（圆柱面/边线/基准轴 spec）。
        angle_deg: 总角度（度）；equal_spacing=True 时忽略，均布 360°。
        instances: 实例数（含种子）。
        equal_spacing: True 均布整周。

    spec 示例：
        circular_pattern(model, seed_feature="Boss-Extrude1",
                         axis_spec={"kind": "cylinder", "axis": [0,0,1]},
                         angle_deg=360, instances=6, equal_spacing=True)

    签名待 SW2018 实测。
    """
    desc = f"circular_pattern(n={instances}, equal={equal_spacing})"
    _select_seed_feature(model, seed_feature, desc)
    _select_direction(model, axis_spec, desc, mark=1)
    fm = _fm(model)
    num = int(instances)
    if equal_spacing:
        spacing = 2.0 * math.pi / max(1, num)
    else:
        spacing = math.radians(float(angle_deg)) / max(1, num - 1)
    a2 = (num, spacing, False, "", False)
    a3 = a2 + (bool(equal_spacing),)
    a4 = a3 + (False,)
    a5 = a4 + (False, False, False, 0, 0.0, "", False)
    return _feat_methods(fm, [
        ("FeatureCircularPattern5", [a5]),
        ("FeatureCircularPattern4", [a4]),
        ("FeatureCircularPattern3", [a3]),
        ("FeatureCircularPattern2", [a2]),
    ], desc)


def mirror_feature(model, seed_features, plane_spec=None, plane_name=None,
                   bodies=False):
    """镜像特征（InsertMirrorFeature/FeatureMirror 族）。

    参数：
        model: IModelDoc2 零件文档。
        seed_features: 种子特征名/IFeature 或列表。
        plane_spec: 镜像平面（平面面 spec）。
        plane_name: 镜像基准面名称（如 "Right Plane"），优先级高于 plane_spec。
        bodies: True 镜像实体。

    spec 示例：
        mirror_feature(model, seed_features=["Boss-Extrude1"],
                       plane_name="Right Plane")
        mirror_feature(model, seed_features=["Cut-Extrude1"],
                       plane_spec={"kind": "plane", "normal": [0, 1, 0]})

    签名待 SW2018 实测。
    """
    desc = f"mirror_feature(bodies={bodies})"
    if plane_name:
        # 基准面中英文候选（中文 UI 下 "Top Plane" 不存在）
        key = str(plane_name).strip().lower().replace(" plane", "")
        cands = {"front": ["Front Plane", "前视基准面", "前视"],
                 "top": ["Top Plane", "上视基准面", "上视"],
                 "right": ["Right Plane", "右视基准面", "右视"]}.get(key, [str(plane_name)])
        ok = False
        for cand in cands:
            if sw_core.select_by_id(model, cand, "PLANE"):
                ok = True
                break
        if not ok:
            raise RuntimeError(f"{desc}: 无法选择基准面 {plane_name!r}")
    elif plane_spec is not None:
        _select_face_specs(model, plane_spec, desc)
    else:
        raise RuntimeError(f"{desc}: 必须提供 plane_spec 或 plane_name")
    first = True
    for seed in _norm_list(seed_features):
        if seed is None:
            continue
        name = seed if isinstance(seed, str) else sw_core.feature_name(seed)
        if not sw_core.select_by_id(model, name, "BODYFEATURE", 0, 0, 0,
                                    True, 1):
            feat = seed if not isinstance(seed, str) else sw_sel.find_feature(model, name=name)
            if not _select_entity_obj(model, feat, append=True, mark=1):
                raise RuntimeError(f"{desc}: 无法选择待镜像特征 {name}")
        first = False
    fm = _fm(model)
    sigs = [(bool(bodies), False, True, False),
            (bool(bodies), False, False, False)]
    sigs2 = [s + (0,) for s in sigs]
    return _feat_methods(fm, [("InsertMirrorFeature", sigs),
                              ("InsertMirrorFeature2", sigs2)], desc)


def sketch_driven_pattern(model, seed_feature, point_sketch):
    """草图驱动阵列（FeatureSketchDrivenPattern 族）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        point_sketch: 含草图点的草图名/IFeature。

    spec 示例：
        sketch_driven_pattern(model, seed_feature="Boss-Extrude1",
                              point_sketch="Sketch3")

    签名待 SW2018 实测。
    """
    desc = "sketch_driven_pattern"
    _select_seed_feature(model, seed_feature, desc)
    pname = point_sketch if isinstance(point_sketch, str) else sw_core.feature_name(point_sketch)
    if not sw_core.select_by_id(model, pname, "SKETCH", 0, 0, 0, True, 16):
        _select_feature_spec(model, point_sketch, desc, append=True, mark=16)
    fm = _fm(model)
    return _feat_methods(fm, [
        ("FeatureSketchDrivenPattern", [(True, False), (False, False)]),
        ("FeatureLocalSketchDrivenPattern", [(0,), (1,)]),
    ], desc)


def curve_driven_pattern(model, seed_feature, curve_edge_spec, spacing_m,
                         instances):
    """曲线驱动阵列（FeatureLocalCurveDrivenPattern）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        curve_edge_spec: 驱动曲线边线 spec。
        spacing_m: 间距（米）。
        instances: 实例数。

    spec 示例：
        curve_driven_pattern(model, seed_feature="Boss-Extrude1",
                             curve_edge_spec={"kind": "edge", "type": "arc"},
                             spacing_m=0.01, instances=6)

    签名待 SW2018 实测。
    """
    desc = f"curve_driven_pattern(n={instances})"
    _select_seed_feature(model, seed_feature, desc)
    _select_direction(model, curve_edge_spec, desc, mark=2)
    fm = _fm(model)
    args = (False, int(instances), True, float(spacing_m), 0, 0, 0,
            False, False, 0, True, 0.0, False)
    return _feat(fm, "FeatureLocalCurveDrivenPattern", [args], desc)


def table_driven_pattern(model, seed_feature, table_coords_mm):
    """表格驱动阵列（InsertTableDrivenPattern2 族）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        table_coords_mm: 坐标列表 [(x_mm, y_mm), ...] 或坐标文件路径。

    spec 示例：
        table_driven_pattern(model, seed_feature="Boss-Extrude1",
                             table_coords_mm=[(10, 0), (20, 0), (30, 0)])

    签名待 SW2018 实测。
    """
    desc = "table_driven_pattern"
    _select_seed_feature(model, seed_feature, desc)
    fm = _fm(model)
    if isinstance(table_coords_mm, str):
        file_name = table_coords_mm
        point_var = None
    else:
        file_name = ""
        pts = []
        for xy in table_coords_mm:
            pts.extend([sw_core.mm(float(xy[0])), sw_core.mm(float(xy[1]))])
        point_var = pts
    sigs = [(file_name, point_var, True, False, False),
            (file_name, point_var, False, False, False)]
    sigs_old = [(file_name, point_var, True, False),
                (file_name, point_var, False, False)]
    return _feat_methods(fm, [("InsertTableDrivenPattern2", sigs),
                              ("InsertTableDrivenPattern", sigs_old)], desc)


def fill_pattern(model, seed_feature, fill_boundary_spec, spacing_m):
    """填充阵列（FeatureFillPattern，低优先级）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        fill_boundary_spec: 填充边界（面/草图 spec）。
        spacing_m: 实例间距（米）。

    spec 示例：
        fill_pattern(model, seed_feature="Boss-Extrude1",
                     fill_boundary_spec={"kind": "plane", "normal": [0,0,1]},
                     spacing_m=0.008)

    签名待 SW2018 实测。
    """
    desc = f"fill_pattern(s={spacing_m})"
    _select_seed_feature(model, seed_feature, desc)
    if isinstance(fill_boundary_spec, dict):
        sw_sel.select_entity(model, fill_boundary_spec, append=True, mark=2)
    else:
        _select_feature_spec(model, fill_boundary_spec, desc, append=True, mark=2)
    fm = _fm(model)
    s = float(spacing_m)
    args = (_FILL_LAYOUT["circular"], 0, s, 0.0, 0.0, 0.0, 0, 6, 0, 0,
            0.0, 0.0, 0.0, 0.0, 6, 0.0, 0.0, False, False)
    return _feat(fm, "FeatureFillPattern", [args], desc)


def variable_pattern(model, seed_feature, table_data):
    """变量阵列（低优先级；SW2018 无独立 VariablePattern 创建方法）。

    参数：
        model: IModelDoc2 零件文档。
        seed_feature: 种子特征名/IFeature。
        table_data: 表格数据（坐标列表或 .sldptab 文件路径）。

    spec 示例：
        variable_pattern(model, seed_feature="Boss-Extrude1",
                         table_data=[(10, 0, 1.0), (20, 0, 2.0)])

    签名待 SW2018 实测。
    """
    desc = "variable_pattern"
    _select_feature_spec(model, seed_feature, desc)
    fm = _fm(model)
    if isinstance(table_data, str):
        file_name = table_data
        point_var = None
    else:
        file_name = ""
        pts = []
        for row in table_data:
            pts.extend([sw_core.mm(float(row[0])), sw_core.mm(float(row[1]))])
        point_var = pts
    # 先按表格驱动阵列回退；再尝试线性阵列 VaryInstance 方案
    try:
        return _feat_methods(fm, [
            ("InsertTableDrivenPattern2",
             [(file_name, point_var, True, False, False),
              (file_name, point_var, False, False, False)]),
        ], desc)
    except RuntimeError:
        n = max(1, len(table_data) if hasattr(table_data, "__len__") else 2)
        a4 = (n, 0.001, 1, 0.0, False, False, "", "", False, True,
              False, False, False, False, False, False, False, False, 0.0, 0.0)
        return _feat_methods(fm, [("FeatureLinearPattern4", [a4]),
                                  ("FeatureLinearPattern3", [a4[:10]])], desc)


# ---------------------------------------------------------------------------
# 多实体/布尔
# ---------------------------------------------------------------------------

def combine(model, op="add", body_specs=None):
    """组合实体（InsertCombineFeature 族）。

    参数：
        model: IModelDoc2 零件文档。
        op: add / subtract / common。
        body_specs: 实体名称/对象列表；None 表示使用全部实体。

    spec 示例：
        combine(model, op="add")
        combine(model, op="subtract", body_specs=["Body1", "Body2"])

    签名待 SW2018 实测。
    """
    desc = f"combine(op={op})"
    code = _COMBINE_OP.get(op)
    if code is None:
        raise RuntimeError(f"{desc}: 不支持的操作 {op!r}")
    bodies = _pick_bodies(model, body_specs)
    if not bodies:
        raise RuntimeError(f"{desc}: 未找到实体")
    fm = _fm(model)
    import pythoncom
    from win32com.client import VARIANT
    dyn_bodies = [_dyn_obj(b) for b in bodies]
    main_body = dyn_bodies[0]
    tool_var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                       dyn_bodies[1:] if op == "subtract" else dyn_bodies)
    sigs = [(code, main_body, tool_var),
            (code, main_body, dyn_bodies[1:])]
    return _feat(fm, "InsertCombineFeature", sigs, desc)


def split(model, trim_tool_spec, targets=None):
    """分割实体（PreSplitBody2 + PostSplitBody2）。

    参数：
        model: IModelDoc2 零件文档。
        trim_tool_spec: 修剪工具（面/基准面 spec）。
        targets: 保留参数（目标实体，SW2018 分割主要基于修剪工具选择）。

    spec 示例：
        split(model, trim_tool_spec={"kind": "plane", "normal": [0, 1, 0]})

    签名待 SW2018 实测。
    """
    desc = "split"
    if isinstance(trim_tool_spec, dict):
        sw_sel.select_entity(model, trim_tool_spec)
    elif not _select_entity_obj(model, trim_tool_spec, append=False, mark=0):
        raise RuntimeError(f"{desc}: 无法选择修剪工具 {trim_tool_spec!r}")
    fm = _fm(model)
    try:
        bodies = getattr(fm, "PreSplitBody2")()
        if bodies is None:
            bodies = getattr(fm, "PreSplitBody")()
    except Exception as exc:
        raise RuntimeError(f"{desc}: PreSplitBody2 调用失败: {exc}") from exc
    sigs = [(bodies, False, None, None, ""),
            (bodies, True, None, None, ""),
            (bodies, False, None, None)]
    return _feat_methods(fm, [("PostSplitBody2", sigs),
                              ("PostSplitBody", sigs[:2])], desc)


def indent(model, target_body_spec, tool_body_spec, depth_m):
    """压凹（InsertIndent；低优先级，SW2018 选择逻辑待实测）。

    参数：
        model: IModelDoc2 零件文档。
        target_body_spec: 目标实体（名称/对象）。
        tool_body_spec: 工具实体（名称/对象）。
        depth_m: 压凹深度（米）。

    spec 示例：
        indent(model, target_body_spec="Body1", tool_body_spec="Body2",
               depth_m=0.002)

    签名待 SW2018 实测。
    """
    desc = f"indent(depth={depth_m})"
    # InsertIndent 依赖目标实体/工具实体选择集（mark 0/1）
    _select_body_specs(model, target_body_spec, desc)
    _select_body_specs(model, tool_body_spec, desc)
    fm = _fm(model)
    sigs = [(float(depth_m), 0.0, False, False, False, False),
            (float(depth_m), 0.0, True, False, True, False)]
    return _feat(fm, "InsertIndent", sigs, desc)


def cavity(model, target_body_spec=None, tool_body_spec=None, depth_m=0):
    """型腔（简化：用 combine subtract 从目标实体减去工具实体）。

    参数：
        model: IModelDoc2 零件文档。
        target_body_spec: 目标实体（名称/对象）。
        tool_body_spec: 工具实体（名称/对象）。
        depth_m: 保留参数（本简化实现不使用）。

    spec 示例：
        cavity(model, target_body_spec="Body1", tool_body_spec="Body2")

    签名待 SW2018 实测。
    """
    desc = f"cavity(target={target_body_spec}, tool={tool_body_spec})"
    _ = float(depth_m)
    if target_body_spec is None or tool_body_spec is None:
        raise RuntimeError(f"{desc}: 需要 target_body_spec 与 tool_body_spec")
    return combine(model, op="subtract",
                   body_specs=[target_body_spec, tool_body_spec])


def move_copy_body(model, body_specs, dx_m=0, dy_m=0, dz_m=0, copy=False,
                   rotate_axis=None, rotate_deg=0):
    """移动/复制实体（InsertMoveCopyBody2 族）。

    参数：
        model: IModelDoc2 零件文档。
        body_specs: 实体名称/对象列表。
        dx_m / dy_m / dz_m: 平移向量（米）。
        copy: True 复制，False 移动。
        rotate_axis: 旋转轴向量 [x,y,z]（近似轴-角，待实测）。
        rotate_deg: 旋转角度（度）。

    spec 示例：
        move_copy_body(model, body_specs=["Body1"], dx_m=0.01)
        move_copy_body(model, body_specs=["Body1"], copy=True, dy_m=0.02)
        move_copy_body(model, body_specs=["Body1"], rotate_axis=[0,0,1],
                       rotate_deg=90)

    签名待 SW2018 实测。
    """
    desc = f"move_copy_body(copy={copy})"
    if body_specs is None:
        bodies = _get_bodies(model)
        if bodies:
            _select_body_specs(model, [bodies[0]], desc)
        else:
            _select_body_specs(model, None, desc)
    else:
        _select_body_specs(model, body_specs, desc)
    dx, dy, dz = float(dx_m), float(dy_m), float(dz_m)
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    fm = _fm(model)
    if dist > 1e-12:
        trans = (dx / dist, dy / dist, dz / dist, dist)
    else:
        trans = (0.0, 0.0, 0.0, 0.0)
    if rotate_axis is not None:
        ax = [float(x) for x in rotate_axis]
        n = math.sqrt(sum(x * x for x in ax)) or 1.0
        ax = [x / n for x in ax]
        ang = math.radians(float(rotate_deg))
        rx, ry, rz = ax[0] * ang, ax[1] * ang, ax[2] * ang
    else:
        rx = ry = rz = 0.0
    # SW2018 实测：TransX/Y/Z 为直接平移分量，TransDist 用于“沿方向距离”
    sigs = [(dx, dy, dz, 0.0,
             0.0, 0.0, 0.0, rx, ry, rz,
             bool(copy), 1),
            (dx, dy, dz, 0.0,
             0.0, 0.0, 0.0, rx, ry, rz,
             bool(copy), 0)]
    return _feat_methods(fm, [("InsertMoveCopyBody2", sigs),
                              ("InsertMoveCopyBody", sigs)], desc)


# ---------------------------------------------------------------------------
# 零件级
# ---------------------------------------------------------------------------

def set_material(model, db, name):
    """设置零件材料。

    参数：
        model: IModelDoc2 零件文档。
        db: SW 材料库路径（如 "SOLIDWORKS Materials"）。
        name: 材料名称（如 "Plain Carbon Steel"）。

    spec 示例：
        set_material(model, db="SOLIDWORKS Materials", name="Plain Carbon Steel")

    签名待 SW2018 实测。
    """
    desc = f"set_material(db={db}, name={name})"
    try:
        ok = model.SetMaterialPropertyName2("", str(db), str(name))
        if not ok:
            raise RuntimeError(f"{desc}: SetMaterialPropertyName2 返回 False")
        return bool(ok)
    except Exception as exc:
        raise RuntimeError(f"{desc}: SetMaterialPropertyName2 调用失败: {exc}") from exc


def get_material(model):
    """读取零件材料。返回 {"db": ..., "name": ...}。

    参数：
        model: IModelDoc2 零件文档。

    spec 示例：
        get_material(model) -> {"db": "SOLIDWORKS Materials", "name": "..."}

    签名待 SW2018 实测。
    """
    desc = "get_material"
    try:
        import pythoncom
        from win32com.client import VARIANT
        db_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
        name = sw_core._dyn(model).GetMaterialPropertyName2("", db_var)
        return {"db": str(db_var.value or ""), "name": str(name or "")}
    except Exception as exc:
        try:
            name = sw_core._dyn(model).GetMaterialPropertyName2("", "")
            return {"db": "", "name": str(name or "")}
        except Exception as exc2:
            raise RuntimeError(f"{desc}: GetMaterialPropertyName2 调用失败: "
                               f"{exc} / {exc2}") from exc2


def custom_properties(model, props):
    """写入自定义属性（遍历 ConfigurationManager.ActiveConfiguration）。

    参数：
        model: IModelDoc2 零件文档。
        props: dict，属性名→值。

    spec 示例：
        custom_properties(model, {"PartNo": "LENS-001", "Material": "BK7"})

    签名待 SW2018 实测。
    """
    desc = "custom_properties"
    if not isinstance(props, dict):
        raise RuntimeError(f"{desc}: props 必须是 dict")
    try:
        config = model.ConfigurationManager.ActiveConfiguration
        config_name = config.Name
        cpm = model.Extension.CustomPropertyManager(str(config_name))
    except Exception as exc:
        raise RuntimeError(f"{desc}: 获取 CustomPropertyManager 失败: {exc}") from exc
    for key, value in props.items():
        try:
            cpm.Set(str(key), str(value))
        except Exception:
            try:
                cpm.Add2(str(key), _CUSTOM_INFO_TEXT, str(value))
            except Exception as exc:
                raise RuntimeError(
                    f"{desc}: 写入属性 {key!r} 失败: {exc}") from exc
    return True


def feature_status(feat):
    """读取特征错误/警告码（错误码见 sw_core.feature_error_codes）。

    参数：
        feat: IFeature 特征对象。

    spec 示例：
        feature_status(feat) -> {"error": 0, "warning": 0}

    签名待 SW2018 实测。
    """
    errors, warnings = sw_core.feature_error_codes(feat)
    return {"error": int(errors), "warning": int(warnings)}


def suppress_feature(model, name_or_feat, suppress=True, config=None):
    """抑制/解除抑制特征。

    参数：
        model: IModelDoc2 零件文档。
        name_or_feat: 特征名(str) 或 IFeature。
        suppress: True 抑制，False 解除抑制。
        config: 配置名；None 表示当前配置。

    spec 示例：
        suppress_feature(model, "Boss-Extrude1", suppress=True)

    签名待 SW2018 实测。
    """
    desc = f"suppress_feature(suppress={suppress})"
    if isinstance(name_or_feat, str):
        feat = sw_sel.find_feature(model, name=name_or_feat)
    else:
        feat = sw_core._early(name_or_feat, "IFeature")
    state = _SUPPRESS_ACTION.get(bool(suppress), 0)
    sigs = []
    if config is not None:
        sigs.append((state, 0, [str(config)]))
        sigs.append((state, 1, [str(config)]))
    sigs.append((state, 0, None))
    sigs.append((state, 0, ""))
    try:
        ok = sw_core.call_sigs(feat, "SetSuppression2", sigs, desc)
        if not ok:
            raise RuntimeError(f"{desc}: SetSuppression2 返回 False")
        return bool(ok)
    except Exception as exc:
        raise RuntimeError(f"{desc}: SetSuppression2 调用失败: {exc}") from exc


# ---------------------------------------------------------------------------
# 公开 API 列表（DSL 按名调用）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 装饰螺纹 / 特征树管理 / 外观渲染（本机 SW2018 扩展）
# ---------------------------------------------------------------------------

def cosmetic_thread(model, edge_spec, diameter_m, depth_m=None,
                    end_condition="through", standard=0, standard_type="",
                    size="", note="", prefer_thread3=True):
    """装饰螺纹（InsertCosmeticThread3/2 族）。

    参数：
        model: IModelDoc2 零件文档。
        edge_spec: 圆边 spec，例如
            {"kind":"edge","type":"circle","radius_mm":8}
            或 {"kind":"edge","type":"circle","near_mm":[0,0,5]}。
        diameter_m: 螺纹公称直径（米）。
        depth_m: 螺纹深度（米）；through 时可省略。
        end_condition: through / blind（装饰螺纹枚举：through=2, blind=0）。
        standard / standard_type / size: InsertCosmeticThread3 的标准/类型/规格。
        note: 螺纹标注文本，如 "M35 THRU"。

    返回 IFeature；装饰螺纹在 SW 中通常作为孔特征的子特征存在。
    """
    desc = f"cosmetic_thread(d={diameter_m}, end={end_condition})"
    sw_core.clear_selection(model)
    if isinstance(edge_spec, dict):
        sw_sel.select_edge(model, edge_spec, mark=0)
    else:
        _select_edge_specs(model, [edge_spec], desc)
    end_code = {"through": 2, "blind": 0}.get(str(end_condition).lower())
    if end_code is None:
        raise RuntimeError(f"{desc}: end_condition 必须是 through/blind")
    depth = float(depth_m) if depth_m is not None else float(diameter_m) * 2.0
    fm = _fm(model)
    if prefer_thread3:
        try:
            raw = fm.InsertCosmeticThread3(int(standard), str(standard_type), str(size),
                                           float(diameter_m), int(end_code), depth, str(note))
            if raw is not None:
                return sw_core._early(raw, "IFeature")
        except Exception as exc:
            last = exc
    else:
        last = None
    # 回退 InsertCosmeticThread2 / InsertCosmeticThread（Type, Depth, Length, Note）
    type_code = int(standard) if standard else 0
    for method in ("InsertCosmeticThread2", "InsertCosmeticThread"):
        for args in ((type_code, depth, depth, str(note)),
                     (type_code, depth, 0.0, str(note))):
            try:
                raw = getattr(fm, method)(*args)
                if raw is not None:
                    return sw_core._early(raw, "IFeature")
            except Exception as exc:
                last = exc
    raise RuntimeError(f"{desc}: InsertCosmeticThread 族均失败: {last}")


def rollback_feature(model, name=None):
    """回退条滚动到指定特征之前；name=None 时作用于当前选中特征。

    SW2018 v26：IPartDoc.EditRollback() 无参，作用于当前选择。
    """
    part = sw_core._early(model, "IPartDoc")
    if name:
        sw_sel.select_feature(model, name=name)
    try:
        part.EditRollback()
    except Exception as exc:
        raise RuntimeError(f"rollback_feature({name!r}): EditRollback 失败: {exc}") from exc
    return {"rolled_back_to": name or "<selected>"}


def rollforward_feature(model):
    """回退条向前滚动到底。"""
    part = sw_core._early(model, "IPartDoc")
    try:
        part.EditRollforward()
    except Exception as exc:
        raise RuntimeError(f"rollforward_feature: EditRollforward 失败: {exc}") from exc
    return {"rolled_forward": True}


def reorder_feature(model, feature_name, target_name, after=True):
    """重排特征：把 feature_name 移动到 target_name 之后。

    SW2018 v26 实测：IPartDoc.ReorderFeature(FeatureToMove, MoveAfterFeature)。
    """
    part = sw_core._early(model, "IPartDoc")
    try:
        ok = part.ReorderFeature(str(feature_name), str(target_name))
    except Exception as exc:
        raise RuntimeError(f"reorder_feature({feature_name!r}, {target_name!r}): {exc}") from exc
    if not bool(ok):
        raise RuntimeError(f"reorder_feature({feature_name!r}, {target_name!r}): ReorderFeature 返回 False")
    return {"feature": feature_name, "after": target_name}


def rename_feature(model, name, new_name):
    """重命名特征。"""
    feat = sw_sel.find_feature(model, name=name)
    try:
        feat.Name = str(new_name)
    except Exception as exc:
        raise RuntimeError(f"rename_feature({name!r} -> {new_name!r}): {exc}") from exc
    return {"feature": new_name}


def create_feature_folder(model, feature_names=None, folder_type=0, name=None):
    """在特征树插入文件夹；feature_names 非空时先选中这些特征。

    SW2018 v26：IFeatureManager.InsertFeatureTreeFolder2(Type)。
    返回最新特征（若 SW 未回传对象则从特征树快照反查）。
    """
    desc = f"create_feature_folder(features={feature_names!r})"
    before = list(sw_core.walk_features(model))
    sw_core.clear_selection(model)
    if feature_names:
        first = True
        for fn in _norm_list(feature_names):
            sw_sel.select_feature(model, name=fn, append=not first, mark=0)
            first = False
    fm = _fm(model)
    raw = None
    last = None
    try:
        raw = fm.InsertFeatureTreeFolder2(int(folder_type))
    except Exception as exc:
        last = exc
        try:
            raw = fm.InsertFeatureTreeFolder()
        except Exception as exc2:
            last = exc2
    if raw is not None:
        feat = sw_core._early(raw, "IFeature")
    else:
        after = [f for f in sw_core.walk_features(model) if f not in before]
        feat = after[-1] if after else None
    if feat is None:
        raise RuntimeError(f"{desc}: 未找到新建文件夹特征（最后错误: {last}）")
    if name:
        feat.Name = str(name)
    return feat


def set_appearance(model, color_rgb=None, ambient=None, diffuse=None,
                   specular=None, shininess=None, transparency=None,
                   emission=None):
    """设置零件外观颜色（IMaterialPropertyValues 九元组）。

    索引：0-2 RGB，3 ambient，4 diffuse，5 specular，6 shininess，
    7 transparency，8 emission。未提供的分量保持当前值。
    """
    part = sw_core._early(model, "IPartDoc")
    try:
        cur = list(part.MaterialPropertyValues)
    except Exception as exc:
        raise RuntimeError(f"set_appearance: 读取 MaterialPropertyValues 失败: {exc}") from exc
    if color_rgb is not None:
        r, g, b = color_rgb
        cur[0], cur[1], cur[2] = float(r), float(g), float(b)
    for idx, val in ((3, ambient), (4, diffuse), (5, specular),
                     (6, shininess), (7, transparency), (8, emission)):
        if val is not None:
            cur[idx] = float(val)
    try:
        part.MaterialPropertyValues = tuple(cur)
    except Exception as exc:
        raise RuntimeError(f"set_appearance: 设置 MaterialPropertyValues 失败: {exc}") from exc
    return {"material_property_values": tuple(cur)}


def set_scene(model, scene_name):
    """设置模型场景（布景），例如 "Plain White"。"""
    try:
        model.SceneName = str(scene_name)
        return {"scene": model.SceneName}
    except Exception as exc:
        raise RuntimeError(f"set_scene({scene_name!r}): {exc}") from exc

PUBLIC_API = [
    "extrude_boss",
    "cosmetic_thread",
    "rollback_feature",
    "rollforward_feature",
    "reorder_feature",
    "rename_feature",
    "create_feature_folder",
    "set_appearance",
    "set_scene",
    "extrude_cut",
    "revolve_boss",
    "revolve_cut",
    "sweep_boss",
    "sweep_cut",
    "loft_boss",
    "loft_cut",
    "boundary_boss",
    "boundary_cut",
    "thicken",
    "fillet",
    "full_round_fillet",
    "chamfer",
    "shell",
    "draft",
    "rib",
    "dome",
    "wrap",
    "simple_hole",
    "hole_wizard",
    "move_face",
    "delete_face",
    "scale_feature",
    "flex",
    "deform",
    "linear_pattern",
    "circular_pattern",
    "mirror_feature",
    "sketch_driven_pattern",
    "curve_driven_pattern",
    "table_driven_pattern",
    "fill_pattern",
    "variable_pattern",
    "combine",
    "split",
    "indent",
    "cavity",
    "move_copy_body",
    "set_material",
    "get_material",
    "custom_properties",
    "feature_status",
    "suppress_feature",
]
