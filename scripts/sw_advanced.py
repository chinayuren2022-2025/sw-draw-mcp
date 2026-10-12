"""sw_advanced.py — SolidWorks 2018 零件建模插件：参考几何、曲线与曲面层。

设计约束：
    - 目标环境：Windows + pywin32 311 + SolidWorks 2018（类型库次版本 26）。
    - 单位：SW API 内部使用米；函数中毫米输入参数名一律带 _mm，内部用 sw_core.mm() 转换。
    - 选择：一律通过 sw_sel 按几何属性/特征名选择，禁止视角坐标拾取。
    - 多签名回退：不确定签名统一走 sw_core.call_sigs / _sub / _call_bool，
      候选签名元组旁注释来源（SW2018 API 文档或旧版 API）。
    - 库代码不 print；不修改已有文件。
"""

import os
import math

import sw_core
import sw_sel

# ---------------------------------------------------------------------------
# 常量（来源：SolidWorks 2018 API 文档 swconst 枚举）
# ---------------------------------------------------------------------------

# swRefPlaneReferenceConstraints_e（位掩码）
_SW_REFPLANE_PARALLEL = 1
_SW_REFPLANE_PERPENDICULAR = 2
_SW_REFPLANE_COINCIDENT = 4
_SW_REFPLANE_DISTANCE = 8
_SW_REFPLANE_ANGLE = 16
_SW_REFPLANE_TANGENT = 32
_SW_REFPLANE_OPTION_FLIP = 256

# swRefPointType_e
_SW_REFPONT_ALONG_CURVE = 2
_SW_REFPONT_CENTER_EDGE = 3
_SW_REFPONT_FACE_CENTER = 4
_SW_REFPONT_FACE_VERTEX_PROJECTION = 5
_SW_REFPONT_INTERSECTION = 6
_SW_REFPONT_SKETCH_POINT = 7

# swRefPointAlongCurveType_e
_SW_REFPONT_ALONG_DISTANCE = 0
_SW_REFPONT_ALONG_PERCENTAGE = 1
_SW_REFPONT_ALONG_EVENLY = 2

# swHelixDefinedBy_e
_SW_HELIX_BY_PITCH_REVOLUTION = 0
_SW_HELIX_BY_HEIGHT_REVOLUTION = 1
_SW_HELIX_BY_HEIGHT_PITCH = 2
_SW_HELIX_BY_SPIRAL = 3

# swFeatureFillSurfaceOptions_e（位掩码）
_SW_FILL_OPTIMIZE = 1
_SW_FILL_TRY_FORM_SOLID = 2
_SW_FILL_MERGE_RESULT = 4

# swFaceUntrimType_e / swEdgeUntrimType_e
_SW_FACE_UNTRIM_ALL_EDGES = 0
_SW_FACE_UNTRIM_INTERNAL_EDGES = 1
_SW_FACE_UNTRIM_EXTERNAL_EDGES = 2
_SW_EDGE_UNTRIM_CONNECT_ENDPOINTS = 1
_SW_EDGE_UNTRIM_EXTEND_EDGES = 2


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _feat(fm, method, sigs, desc):
    """统一特征调用：call_sigs 多签名回退 + None 检查 + IFeature 早绑定包装。

    fm       IFeatureManager（sw_core._early 包装后的对象）
    method   方法名字符串
    sigs     候选签名元组列表 [(args...), ...]，每个候选旁注释来源
    desc     中文错误上下文
    """
    ret = sw_core.call_sigs(fm, method, sigs, desc)
    if ret is None:
        raise RuntimeError(f"{desc}: {method} 返回 None")
    return sw_core._early(ret, "IFeature")


def _sub(obj, method, sigs, desc):
    """Sub 过程多签名回退（InsertHelix 等无返回值，不能使用 call_sigs 的 None 判定）。

    返回 True 表示调用成功（未抛异常）。参数签名不确定时同样候选回退。
    """
    last = None
    for args in sigs:
        try:
            getattr(obj, method)(*args)
            return True
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}")


def _call_bool(obj, method, sigs, desc):
    """布尔返回值方法多签名回退；返回 False 继续尝试下一候选签名。

    注：call_sigs 会把 False 视为“非 None 成功”，因此布尔方法单独循环处理。
    """
    last = None
    for args in sigs:
        try:
            ret = getattr(obj, method)(*args)
        except Exception as exc:
            last = exc
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
            continue
        if ret is None:
            last = RuntimeError(f"{desc}: {method} 返回 None")
            continue
        if bool(ret):
            return True
        last = RuntimeError(f"{desc}: {method} 返回 False")
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}")


def _clear(model):
    """清空选择集（防御性兼容）。"""
    try:
        model.ClearSelection2(True)
    except Exception:
        sw_core.clear_selection(model)


def _feat_name(feat):
    """统一返回 (IFeature, 名称)。"""
    return sw_core._early(feat, "IFeature"), sw_core.feature_name(feat)


def _feature_snapshot(model):
    """特征树顶层名称快照，用于 Sub 过程创建特征后反查新特征。"""
    return {sw_core.feature_name(f) for f in sw_core.walk_features(model)}


def _new_feature(model, before):
    """在 before 快照之后查找新增特征；找不到抛中文 RuntimeError。"""
    for feat in sw_core.walk_features(model):
        if sw_core.feature_name(feat) not in before:
            return sw_core._early(feat, "IFeature")
    raise RuntimeError("新建特征后未在特征树中找到新增特征（特征树可能未刷新）")


def _preselect(model, spec, mark, append, desc):
    """按 spec 预选一个实体：字符串按特征名选，dict 走 sw_sel 几何属性选，
    COM 对象直接 Select2/Select4。选不到抛中文 RuntimeError。
    """
    if spec is None:
        raise RuntimeError(f"{desc}: 选择 spec 不能为 None（mark={mark}）")
    if isinstance(spec, str):
        low = str(spec).strip().lower()
        if low in ("front", "top", "right"):
            cands = {"front": ["Front Plane", "前视基准面", "前视"],
                     "top": ["Top Plane", "上视基准面", "上视"],
                     "right": ["Right Plane", "右视基准面", "右视"]}[low]
            for cand in cands:
                try:
                    if sw_core.select_by_id(model, cand, "PLANE",
                                            append=append, mark=mark):
                        return True
                except Exception:
                    continue
            raise RuntimeError(f"{desc}: 无法选择标准基准面 {spec!r}")
        return sw_sel.select_feature(model, name=spec, append=append, mark=mark)
    if isinstance(spec, dict):
        ent, _info = sw_sel.select_entity(model, spec, append=append, mark=mark)
        return ent
    # 已解析的 COM 对象（IFeature/IFace2/IEdge/IVertex 等）
    try:
        if bool(spec.Select2(append, mark)):
            return spec
    except Exception:
        pass
    try:
        ent = sw_core._early(spec, "IEntity")
        if sw_sel._select_entity(model, ent, append, mark):
            return ent
    except Exception:
        pass
    raise RuntimeError(f"{desc}: 无法选择实体 spec={spec!r}（mark={mark}）")


def _preselect_all(model, items, desc):
    """items: [(spec, mark), ...]；首个 append=False，后续 append=True。"""
    for idx, (spec, mark) in enumerate(items):
        if spec is None:
            continue
        _preselect(model, spec, mark, append=(idx > 0), desc=desc)


def _as_list(value):
    """把单个值/元组规范化为 list；None 返回空 list。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _selected_objects(model, mark):
    """读取指定 mark 的已选对象列表（用于 fill surface 等需要显式数组的 API）。"""
    out = []
    try:
        sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
        n = int(sm.GetSelectedObjectCount2(mark))
        for i in range(1, n + 1):
            try:
                out.append(sm.GetSelectedObject6(i, mark))
            except Exception:
                pass
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# 参考几何
# ---------------------------------------------------------------------------

def insert_ref_plane(model, plane_type='offset', base_spec=None, distance_mm=0,
                     angle_deg=0, point_specs=None):
    """插入参考基准面。返回 (IFeature, 名称)。

    plane_type ∈ offset / angle / parallel / through_line_point /
                 three_points / normal_to_curve / on_surface
    base_spec   基准实体（面/平面/边/曲线/点 spec 或特征名）
    point_specs 附加实体 spec 或列表（角度、过线点、三点、法向曲线等需要）

    spec 示例：
        {"kind": "plane", "normal": [0,0,1], "root_mm": [0,0,0]}
        {"kind": "edge", "type": "circle", "radius_mm": 12.5}
        {"kind": "vertex", "near_mm": [0,0,0]}
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)

    pts = _as_list(point_specs)
    plane_type = str(plane_type).lower()

    selections = []   # [(spec, mark)]
    constraints = None  # (c1, c2, c3)
    values = (0.0, 0.0, 0.0)

    if plane_type == 'offset':
        selections = [(base_spec, 0)]
        constraints = (_SW_REFPLANE_DISTANCE, 0, 0)
        values = (sw_core.mm(distance_mm), 0.0, 0.0)
    elif plane_type == 'angle':
        if len(pts) < 1:
            raise RuntimeError("insert_ref_plane(angle) 需要 point_specs 提供转轴/边线实体")
        selections = [(base_spec, 0), (pts[0], 1)]
        constraints = (_SW_REFPLANE_ANGLE, 0, 0)
        values = (sw_core.rad(angle_deg), 0.0, 0.0)
    elif plane_type == 'parallel':
        if len(pts) < 1:
            raise RuntimeError("insert_ref_plane(parallel) 需要 point_specs 提供参考点")
        selections = [(base_spec, 0), (pts[0], 1)]
        constraints = (_SW_REFPLANE_PARALLEL, _SW_REFPLANE_COINCIDENT, 0)
    elif plane_type == 'through_line_point':
        if len(pts) < 1:
            raise RuntimeError("insert_ref_plane(through_line_point) 需要 point_specs 提供参考点")
        selections = [(base_spec, 0), (pts[0], 1)]
        constraints = (_SW_REFPLANE_COINCIDENT, _SW_REFPLANE_COINCIDENT, 0)
    elif plane_type == 'three_points':
        if len(pts) < 2:
            raise RuntimeError("insert_ref_plane(three_points) 需要 point_specs 提供两个附加点")
        selections = [(base_spec, 0), (pts[0], 1), (pts[1], 2)]
        constraints = (_SW_REFPLANE_COINCIDENT, _SW_REFPLANE_COINCIDENT,
                       _SW_REFPLANE_COINCIDENT)
    elif plane_type == 'normal_to_curve':
        if len(pts) < 1:
            raise RuntimeError("insert_ref_plane(normal_to_curve) 需要 point_specs 提供曲线上的点")
        selections = [(base_spec, 0), (pts[0], 1)]
        constraints = (_SW_REFPLANE_PERPENDICULAR, _SW_REFPLANE_COINCIDENT, 0)
    elif plane_type == 'on_surface':
        if len(pts) < 1:
            raise RuntimeError("insert_ref_plane(on_surface) 需要 point_specs 提供曲面上的点")
        selections = [(base_spec, 0), (pts[0], 1)]
        constraints = (_SW_REFPLANE_TANGENT, _SW_REFPLANE_COINCIDENT, 0)
    else:
        raise RuntimeError(f"insert_ref_plane: 不支持的 plane_type={plane_type!r}")

    _preselect_all(model, selections, desc="insert_ref_plane 预选")
    c1, c2, c3 = constraints
    v1, v2, v3 = values
    # 旧版 swPlaneType_e 候选（SW2018 是否保留未知，仅作回退）：
    # OffsetDistance=0, ParallelAtPoint=1, Angle=2, Through3Points=3,
    # ThroughLinePoint=4, OnSurface=5, NormalToCurve=6（6 不确定）
    _legacy_type = {'offset': 0, 'parallel': 1, 'angle': 2,
                    'three_points': 3, 'through_line_point': 4,
                    'on_surface': 5, 'normal_to_curve': 6}.get(plane_type, 0)
    if plane_type == 'offset':
        _legacy_args = (_legacy_type, v1, 0.0, False, True)
    elif plane_type == 'angle':
        _legacy_args = (_legacy_type, 0.0, v1, False, True)
    else:
        _legacy_args = (_legacy_type, 0.0, 0.0, False, True)
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertRefPlane
        # (FirstConstraint, FirstConstraintAngleOrDistance, SecondConstraint,
        #  SecondConstraintAngleOrDistance, ThirdConstraint,
        #  ThirdConstraintAngleOrDistance)，预选 marks: 0/1/2
        (c1, v1, c2, v2, c3, v3),
        # 来源: 旧版 SW API（PlaneType, Distance, Angle, Flip, UseAutoSize）
        _legacy_args,
    ]
    before = _feature_snapshot(model)
    feat = _feat(fm, "InsertRefPlane", sigs, "insert_ref_plane")
    # v26 实测：InsertRefPlane 直接返回值不是可用的 IFeature（Name 会返回数组），
    # 从特征树快照反查新建基准面特征
    new_feat = _new_feature(model, before)
    if new_feat is not None:
        return _feat_name(new_feat)
    return _feat_name(feat)


def insert_axis(model, axis_type='cylinder', base_spec=None, base_spec2=None):
    """插入参考轴。返回 (IFeature, 名称)。

    axis_type ∈ cylinder / edge / two_planes / two_points / line_face / point_face
    选择：圆柱面、边线、两平面、两点、线+面、点+面（由 base_spec/base_spec2 给出）。
    """
    axis_type = str(axis_type).lower()
    _clear(model)

    if axis_type in ('cylinder', 'edge'):
        selections = [(base_spec, 0)]
    elif axis_type in ('two_planes', 'two_points', 'line_face', 'point_face'):
        if base_spec2 is None:
            raise RuntimeError(f"insert_axis({axis_type}) 需要 base_spec2")
        selections = [(base_spec, 0), (base_spec2, 1)]
    else:
        raise RuntimeError(f"insert_axis: 不支持的 axis_type={axis_type!r}")

    _preselect_all(model, selections, desc="insert_axis 预选")
    before = _feature_snapshot(model)
    desc = "insert_axis"
    try:
        # 来源: SW2018 API 文档 IModelDoc2::InsertAxis2(AutoSize As Boolean)
        _call_bool(model, "InsertAxis2", [(True,), (False,)], desc)
    except Exception:
        # 来源: SW2018 API 文档 IModelDoc2::InsertAxis（旧版无参）
        _call_bool(model, "InsertAxis", [()], desc)
    return _feat_name(_new_feature(model, before))


def insert_reference_point(model, point_type='face_center', base_spec=None,
                           distance_mm=0, curve_spec=None):
    """插入参考点。返回 (IFeature, 名称)。

    point_type ∈ face_center / center_edge / along_curve / intersection / sketch_point
    distance_mm 仅 along_curve 使用（沿曲线距离）。
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    point_type = str(point_type).lower()

    if point_type == 'face_center':
        selections = [(base_spec, 0)]
        ref_type = _SW_REFPONT_FACE_CENTER
        along_type = _SW_REFPONT_ALONG_DISTANCE
        dist = 0.0
    elif point_type == 'center_edge':
        selections = [(base_spec, 0)]
        ref_type = _SW_REFPONT_CENTER_EDGE
        along_type = _SW_REFPONT_ALONG_DISTANCE
        dist = 0.0
    elif point_type == 'along_curve':
        selections = [(base_spec, 0)]
        ref_type = _SW_REFPONT_ALONG_CURVE
        along_type = _SW_REFPONT_ALONG_DISTANCE
        dist = sw_core.mm(distance_mm)
    elif point_type == 'intersection':
        if curve_spec is None:
            raise RuntimeError("insert_reference_point(intersection) 需要 curve_spec")
        selections = [(base_spec, 0), (curve_spec, 1)]
        ref_type = _SW_REFPONT_INTERSECTION
        along_type = _SW_REFPONT_ALONG_DISTANCE
        dist = 0.0
    elif point_type == 'sketch_point':
        selections = [(base_spec, 0)]
        ref_type = _SW_REFPONT_SKETCH_POINT
        along_type = _SW_REFPONT_ALONG_DISTANCE
        dist = 0.0
    else:
        raise RuntimeError(f"insert_reference_point: 不支持的 point_type={point_type!r}")

    _preselect_all(model, selections, desc="insert_reference_point 预选")
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertReferencePoint
        # (NRefPointType, NRefPointAlongCurveType, DDistance_or_Percent,
        #  NumberOfRefPoints)；NumberOfRefPoints=1
        (ref_type, along_type, dist, 1),
    ]
    ret = sw_core.call_sigs(fm, "InsertReferencePoint", sigs, "insert_reference_point")
    if ret is None:
        raise RuntimeError("insert_reference_point: InsertReferencePoint 返回 None")
    if isinstance(ret, (list, tuple)):
        if len(ret) == 0:
            raise RuntimeError("insert_reference_point: InsertReferencePoint 返回空数组")
        ret = ret[0]
    return _feat_name(ret)


def insert_coordinate_system(model, origin_spec=None, x_axis_spec=None,
                             y_axis_spec=None):
    """插入坐标系。返回 (IFeature, 名称)。

    选择 marks（来源: SW2018 API 文档 InsertCoordinateSystem Remarks）：
        origin=1, x 轴=2, y 轴=4, z 轴=8
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    if origin_spec is None:
        raise RuntimeError("insert_coordinate_system: 需要 origin_spec")
    selections = [(origin_spec, 1)]
    if x_axis_spec is not None:
        selections.append((x_axis_spec, 2))
    if y_axis_spec is not None:
        selections.append((y_axis_spec, 4))
    _preselect_all(model, selections, desc="insert_coordinate_system 预选")
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertCoordinateSystem
        # (XFlippedIn, YFlippedIn, ZFlippedIn)
        (False, False, False),
    ]
    feat = _feat(fm, "InsertCoordinateSystem", sigs, "insert_coordinate_system")
    return _feat_name(feat)


def find_ref_plane(model, name):
    """按名称在特征树中查找基准面特征（GetTypeName2 含 RefPlane）。

    返回 (IFeature, 名称)；找不到抛中文 RuntimeError。
    """
    for feat in sw_core.walk_features(model):
        if "RefPlane" in sw_core.feature_type(feat) and sw_core.feature_name(feat) == name:
            return sw_core._early(feat, "IFeature"), sw_core.feature_name(feat)
    raise RuntimeError(f"find_ref_plane: 未找到基准面 {name!r}")


# ---------------------------------------------------------------------------
# 曲线
# ---------------------------------------------------------------------------

def helix(model, circle_sketch, height_mm, pitch_mm, revolutions=1,
          start_angle_deg=0, clockwise=False, taper_deg=0):
    """插入恒距螺旋线。返回 (IFeature, 名称)。

    参数单位：height_mm/pitch_mm 毫米，revolutions 圈，start_angle_deg/taper_deg 度。
    """
    _clear(model)
    _preselect_all(model, [(circle_sketch, 0)], desc="helix 预选")
    tapered = abs(taper_deg) > 1e-9
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertHelix
        # (Reversed, Clockwised, Tapered, Outward, Helixdef, Height,
        #  Pitch, Revolution, TaperAngle, Startangle)
        (False, bool(clockwise), tapered, taper_deg > 0,
         _SW_HELIX_BY_HEIGHT_PITCH, sw_core.mm(height_mm), sw_core.mm(pitch_mm),
         float(revolutions), sw_core.rad(taper_deg), sw_core.rad(start_angle_deg)),
    ]
    before = _feature_snapshot(model)
    _sub(model, "InsertHelix", sigs, "helix")
    return _feat_name(_new_feature(model, before))


def spiral(model, circle_sketch, height_mm, pitch_mm, revolutions=1,
           start_angle_deg=0, clockwise=False):
    """插入螺旋线（Spiral）。返回 (IFeature, 名称)。

    SW2018 通过 IModelDoc2::InsertHelix 的 swHelixDefinedBySpiral(3) 支持；
    需提供 pitch 与圈数。
    """
    _clear(model)
    _preselect_all(model, [(circle_sketch, 0)], desc="spiral 预选")
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertHelix + swHelixDefinedBy_e
        (False, bool(clockwise), False, False, _SW_HELIX_BY_SPIRAL,
         sw_core.mm(height_mm), sw_core.mm(pitch_mm), float(revolutions),
         0.0, sw_core.rad(start_angle_deg)),
    ]
    before = _feature_snapshot(model)
    _sub(model, "InsertHelix", sigs, "spiral")
    return _feat_name(_new_feature(model, before))


def projected_curve(model, sketch, face_specs):
    """把草图投影到面上生成投影曲线。返回 (IFeature, 名称)。

    face_specs 为面 spec 或列表。
    """
    _clear(model)
    selections = [(sketch, 0)]
    for i, spec in enumerate(_as_list(face_specs)):
        selections.append((spec, 1 if i == 0 else 1))
    _preselect_all(model, selections, desc="projected_curve 预选")
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertProjectedSketch2(Reverse As Integer)
        (0,),
        (1,),
    ]
    ret = sw_core.call_sigs(model, "InsertProjectedSketch2", sigs, "projected_curve")
    if ret is None:
        raise RuntimeError("projected_curve: InsertProjectedSketch2 返回 None")
    return _feat_name(ret)


def composite_curve(model, edge_specs):
    """把多条边组合成组合曲线。返回 (IFeature, 名称)。"""
    _clear(model)
    for i, spec in enumerate(_as_list(edge_specs)):
        _preselect(model, spec, 1, append=(i > 0), desc="composite_curve 预选")
    before = _feature_snapshot(model)
    # 来源: SW2018 API 文档 IModelDoc2::InsertCompositeCurve()，边预选 mark=1
    _call_bool(model, "InsertCompositeCurve", [()], "composite_curve")
    return _feat_name(_new_feature(model, before))


def split_line(model, sketch, face_specs):
    """把草图投影到面上生成分割线。返回 (IFeature, 名称)。

    草图预选 mark=4，目标面预选 mark=1（来源: InsertSplitLineProject Remarks）。
    """
    _clear(model)
    selections = [(sketch, 4)]
    for i, spec in enumerate(_as_list(face_specs)):
        selections.append((spec, 1 if i == 0 else 1))
    _preselect_all(model, selections, desc="split_line 预选")
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertSplitLineProject
        # (IsDirectional, FlipDir)
        (False, False),
        (True, False),
        (True, True),
    ]
    before = _feature_snapshot(model)
    _sub(model, "InsertSplitLineProject", sigs, "split_line")
    return _feat_name(_new_feature(model, before))


def curve_through_points(model, points_mm):
    """通过参考点/顶点创建 3D 样条曲线。返回 (IFeature, 名称)。

    points_mm: [(x_mm, y_mm, z_mm), ...]；按 sw_sel 顶点几何属性反查并预选（mark=1）。
    """
    _clear(model)
    pts = _as_list(points_mm)
    if len(pts) < 2:
        raise RuntimeError("curve_through_points: 至少需要 2 个点")
    for i, pt in enumerate(pts):
        spec = {"kind": "vertex", "near_mm": [float(pt[0]), float(pt[1]), float(pt[2])],
                "tol_mm": 0.2}
        _preselect(model, spec, 1, append=(i > 0), desc="curve_through_points 预选")
    before = _feature_snapshot(model)
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::Insert3DSplineCurve(CurveClosed As Boolean)
        (False,),
    ]
    _sub(model, "Insert3DSplineCurve", sigs, "curve_through_points")
    return _feat_name(_new_feature(model, before))


def curve_from_xyz_file(model, path):
    """从 XYZ 文本文件创建自由曲线。返回 (IFeature, 名称)。

    文件每行 "x y z"，单位按 SW API 内部单位：米。
    调用序列（来源: SW2018 API 文档）：
        InsertCurveFileBegin -> InsertCurveFilePoint * N -> InsertCurveFileEnd
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    points = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.replace(",", " ").split()
            if len(parts) < 3:
                continue
            points.append((float(parts[0]), float(parts[1]), float(parts[2])))
    if not points:
        raise RuntimeError(f"curve_from_xyz_file: 文件 {path} 中没有可用点")

    before = _feature_snapshot(model)
    _sub(model, "InsertCurveFileBegin", [()], "curve_from_xyz_file: InsertCurveFileBegin")
    for x, y, z in points:
        _sub(model, "InsertCurveFilePoint",
             [(float(x), float(y), float(z))], "curve_from_xyz_file: InsertCurveFilePoint")
    _call_bool(model, "InsertCurveFileEnd", [()], "curve_from_xyz_file: InsertCurveFileEnd")
    return _feat_name(_new_feature(model, before))


# ---------------------------------------------------------------------------
# 曲面
# ---------------------------------------------------------------------------

def extruded_surface(model, sketch, depth_m, direction2=False):
    """从草图拉伸曲面。返回 (IFeature, 名称)。

    depth_m 单位：米；direction2=True 时双向等深拉伸。
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    _preselect_all(model, [(sketch, 4)], desc="extruded_surface 预选")
    d1 = float(depth_m)
    d2 = float(depth_m) if direction2 else 0.0
    before = _feature_snapshot(model)
    # 优先 FeatureExtruRefSurface3（来源: SW2018 API 文档 IFeatureManager）。
    args3 = (True, direction2, 0, 0.0, 0, 0, d1, d2,
             False, False, False, False, 0.0, 0.0,
             False, False, False, False, False, False, False, False)
    # 旧版 FeatureExtruRefSurface2（IFeatureManager，多 Flip 参数，少 StartCond/OffsetVal）
    args2 = (True, False, direction2, 0, 0, d1, d2,
             False, False, False, False, 0.0, 0.0,
             False, False, False, False, False, False, False, False)
    # 旧版 IModelDoc2::FeatureExtruRefSurface2（17 参数）
    args2_model = (True, False, direction2, 0, 0, d1, d2,
                   False, False, False, False, 0.0, 0.0,
                   False, False, False, False)
    try:
        _sub(fm, "FeatureExtruRefSurface3", [args3], "extruded_surface")
    except Exception as exc:
        if not sw_core.is_arg_count_error(exc):
            raise
        try:
            _sub(fm, "FeatureExtruRefSurface2", [args2], "extruded_surface")
        except Exception:
            _sub(model, "FeatureExtruRefSurface2", [args2_model], "extruded_surface")
    return _feat_name(_new_feature(model, before))


def revolved_surface(model, sketch, angle_deg=360):
    """旋转曲面。返回 (IFeature, 名称)。"""
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    _preselect_all(model, [(sketch, 4)], desc="revolved_surface 预选")
    angle = sw_core.rad(angle_deg)
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertRevolvedRefSurface
        # (Angle, ReverseDir, Angle2, RevType)；RevType 0=单侧
        (angle, False, 0.0, 0),
        # 来源: 同上，RevType 1=中面旋转
        (angle, False, 0.0, 1),
    ]
    feat = _feat(fm, "InsertRevolvedRefSurface", sigs, "revolved_surface")
    return _feat_name(feat)


def lofted_surface(model, profile_sketches, guide_curves=None):
    """放样曲面。返回 (IFeature, 名称)。

    profile_sketches: 轮廓草图名/IFeature/列表；guide_curves 可选，mark=2。
    """
    _clear(model)
    profiles = _as_list(profile_sketches)
    if len(profiles) < 1:
        raise RuntimeError("lofted_surface: 至少需要 1 个轮廓")
    selections = []
    for i, spec in enumerate(profiles):
        selections.append((spec, 1))
    for i, spec in enumerate(_as_list(guide_curves)):
        selections.append((spec, 2))
    _preselect_all(model, selections, desc="lofted_surface 预选")
    before = _feature_snapshot(model)
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertLoftRefSurface2
        # (Closed, KeepTangency, ForceNonRational, TessToleranceFactor,
        #  StartMatchingType, EndMatchingType)
        (False, False, False, 1.0, 0, 0),
    ]
    _sub(model, "InsertLoftRefSurface2", sigs, "lofted_surface")
    return _feat_name(_new_feature(model, before))


def boundary_surface(model, sketch_pairs):
    """边界曲面。返回 (IFeature, 名称)。

    sketch_pairs: [(dir1_spec, dir2_spec), ...] 或 [dir1_spec, ...]（仅方向 1）。
    方向 1 预选 marks: 8193/16385/24577；方向 2: 8194/16386/24578
    （来源: SW2018 API 文档 InsertNetBlend2 Remarks）。
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)

    pairs = list(sketch_pairs) if isinstance(sketch_pairs, (list, tuple)) else [sketch_pairs]
    if not pairs:
        raise RuntimeError("boundary_surface: sketch_pairs 不能为空")
    dir1, dir2 = [], []
    if pairs and isinstance(pairs[0], (list, tuple)):
        for a, b in pairs:
            dir1.append(a)
            dir2.append(b)
    else:
        dir1 = pairs

    selections = []
    for i, spec in enumerate(dir1):
        selections.append((spec, 8193 + i * 8192))
    for i, spec in enumerate(dir2):
        selections.append((spec, 8194 + i * 8192))
    _preselect_all(model, selections, desc="boundary_surface 预选")

    # 为每条曲线设置无相切数据（来源: SetNetBlendCurveData Remarks）
    for i in range(len(dir1)):
        _feat(fm, "SetNetBlendCurveData",
              [(0, i, 0, 0.0, 1.0, True)], "boundary_surface: SetNetBlendCurveData dir1")
    for i in range(len(dir2)):
        _feat(fm, "SetNetBlendCurveData",
              [(1, i, 0, 0.0, 1.0, True)], "boundary_surface: SetNetBlendCurveData dir2")
    if dir1:
        _feat(fm, "SetNetBlendDirectionData",
              [(0, 0, 0, False, False)], "boundary_surface: SetNetBlendDirectionData dir1")
    if dir2:
        _feat(fm, "SetNetBlendDirectionData",
              [(1, 0, 0, False, False)], "boundary_surface: SetNetBlendDirectionData dir2")

    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertNetBlend2
        # (Type=2 Surface, NCurvesDir1, NCurvesDir2, HasCenterline,
        #  TessTolFactor, WantsSolid, MergeBody, FeatureScope, AutoSelect,
        #  Thin, Thickness1, Thickness2, ReverseThickness, ThinSolidType,
        #  UseSharedThickness, CapEnds, EndThickness, AutoFillet,
        #  FilletRadius, ForceNonRational, CreateSolid)
        (2, len(dir1), len(dir2), False, 0.0001, False, True, True, True,
         False, -1, -1, False, -1, False, False, -1, False, -1, True, True),
    ]
    feat = _feat(fm, "InsertNetBlend2", sigs, "boundary_surface")
    return _feat_name(feat)


def planar_surface(model, sketch_or_face_spec):
    """从草图/面边界创建平面曲面。返回 (IFeature, 名称)。"""
    _clear(model)
    _preselect_all(model, [(sketch_or_face_spec, 1)], desc="planar_surface 预选")
    before = _feature_snapshot(model)
    # 来源: SW2018 API 文档 IModelDoc2::InsertPlanarRefSurface()，边界预选 mark=1
    _call_bool(model, "InsertPlanarRefSurface", [()], "planar_surface")
    return _feat_name(_new_feature(model, before))


def fill_surface(model, edge_specs, merge=True, try_form_solid=False):
    """填充曲面。返回 (IFeature, 名称)。

    edge_specs: 边界边/草图 spec 或列表；预选 mark=1（无相切控制）。
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    edges = _as_list(edge_specs)
    for i, spec in enumerate(edges):
        _preselect(model, spec, 1, append=(i > 0), desc="fill_surface 预选")
    boundaries = _selected_objects(model, 1)
    if not boundaries:
        raise RuntimeError("fill_surface: 未选到任何边界实体")
    if len(boundaries) < 3:
        raise RuntimeError(f"fill_surface: 边界必须构成闭合环（当前 {len(boundaries)} 条）")
    import pythoncom
    from win32com.client import VARIANT
    contact_types = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, [0] * len(boundaries))
    bnd_var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, boundaries)
    options = _SW_FILL_OPTIMIZE
    if merge:
        options |= _SW_FILL_MERGE_RESULT
    if try_form_solid:
        options |= _SW_FILL_TRY_FORM_SOLID
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertFillSurface2
        # (Resolutions, Options, VPatchBoundaries, VCurvatureControlType,
        #  VFaces, VConstraintCurves)；v26 实测需 VARIANT 数组
        (2, options, bnd_var, contact_types, None, None),
    ]
    feat = _feat(fm, "InsertFillSurface2", sigs, "fill_surface")
    return _feat_name(feat)


def offset_surface(model, face_specs, distance_mm):
    """等距曲面。返回 (IFeature, 名称)。"""
    _clear(model)
    for i, spec in enumerate(_as_list(face_specs)):
        _preselect(model, spec, 0, append=(i > 0), desc="offset_surface 预选")
    before = _feature_snapshot(model)
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertOffsetSurface
        # (Thickness, Reverse)，Thickness 单位：米
        (sw_core.mm(distance_mm), False),
        (sw_core.mm(distance_mm), True),
    ]
    _sub(model, "InsertOffsetSurface", sigs, "offset_surface")
    return _feat_name(_new_feature(model, before))


def extend_surface(model, edge_specs, distance_m, end_type='distance'):
    """延伸曲面。返回 (IFeature, 名称)。

    end_type ∈ distance / point / surface（对应 EndCondition 0/1/2）。
    """
    _clear(model)
    for i, spec in enumerate(_as_list(edge_specs)):
        _preselect(model, spec, 0, append=(i > 0), desc="extend_surface 预选")
    end_type = str(end_type).lower()
    end_cond = {"distance": 0, "point": 1, "surface": 2}.get(end_type)
    if end_cond is None:
        raise RuntimeError(f"extend_surface: 不支持的 end_type={end_type!r}")
    before = _feature_snapshot(model)
    sigs = [
        # 来源: SW2018 API 文档 IModelDoc2::InsertExtendSurface
        # (ExtendLinear, EndCondition, Distance)
        (True, end_cond, float(distance_m)),
    ]
    _sub(model, "InsertExtendSurface", sigs, "extend_surface")
    return _feat_name(_new_feature(model, before))


def trim_surface(model, trim_tool_spec, keep_spec):
    """剪裁曲面。返回 (IFeature, 名称)。

    API 序列（来源: SW2018 API 文档 PreTrimSurface/PostTrimSurface）：
        PreTrimSurface -> 选剪裁工具 + 保留面 -> PostTrimSurface
    """
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    # PreTrimSurface(BMutualTrim, BSplitSystem, BSplitLinear, BRemovePicked)
    # 来源: SW2018 API 文档 IFeatureManager::PreTrimSurface
    _call_bool(fm, "PreTrimSurface",
               [(False, True, False, True)], "trim_surface: PreTrimSurface")
    _preselect_all(model, [(trim_tool_spec, 0)], desc="trim_surface 预选工具")
    keeps = _as_list(keep_spec)
    for i, spec in enumerate(keeps):
        _preselect(model, spec, 1, append=(i > 0), desc="trim_surface 预选保留面")
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::PostTrimSurface(BSewSurfaceIn)
        (False,),
        (True,),
    ]
    feat = _feat(fm, "PostTrimSurface", sigs, "trim_surface")
    return _feat_name(feat)


def untrim_surface(model, face_specs):
    """取消剪裁曲面。返回 (IFeature, 名称)。"""
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    for i, spec in enumerate(_as_list(face_specs)):
        _preselect(model, spec, 0, append=(i > 0), desc="untrim_surface 预选")
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertUntrimSurface
        # (FaceUntrimType, EdgeUntrimType, Distance, BMerge)
        (_SW_FACE_UNTRIM_ALL_EDGES, _SW_EDGE_UNTRIM_EXTEND_EDGES, 0.0, True),
        (_SW_FACE_UNTRIM_ALL_EDGES, _SW_EDGE_UNTRIM_CONNECT_ENDPOINTS, 0.0, True),
    ]
    feat = _feat(fm, "InsertUntrimSurface", sigs, "untrim_surface")
    return _feat_name(feat)


def knit_surface(model, face_specs, try_form_solid=False):
    """缝合曲面。返回 (IFeature, 名称)。"""
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    for i, spec in enumerate(_as_list(face_specs)):
        _preselect(model, spec, 1, append=(i > 0), desc="knit_surface 预选")
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertSewRefSurface
        # (UseGapFilters, TryToFormSolid, MergeEntities, KnitTolerance,
        #  MaxValueForGapRange)
        (True, bool(try_form_solid), True, 0.0001, 0.0001),
    ]
    feat = _feat(fm, "InsertSewRefSurface", sigs, "knit_surface")
    return _feat_name(feat)


def cut_with_surface(model, surface_face_spec, flip=False):
    """用曲面/平面切除实体。返回 (IFeature, 名称)。"""
    fm = sw_core._early(model.FeatureManager, "IFeatureManager")
    _clear(model)
    _preselect_all(model, [(surface_face_spec, 0)], desc="cut_with_surface 预选")
    import pythoncom
    from win32com.client import VARIANT
    err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    sigs = [
        # 来源: SW2018 API 文档 IFeatureManager::InsertCutSurface
        # (Flip, KeepPieceIndex, UseFeatScope, UseAutoSelect, Bodies, ByRef Error)
        (bool(flip), -1, False, True, [], err_var),
    ]
    feat = _feat(fm, "InsertCutSurface", sigs, "cut_with_surface")
    return _feat_name(feat)


def replace_face(model, target_face_spec, replacement_face_spec):
    """替换面。返回 (IFeature, 名称)。

    目标面预选 mark=1，替换曲面预选 mark=2（来源: InsertFeatureReplaceFace Remarks）。
    """
    _clear(model)
    _preselect_all(model, [(target_face_spec, 1), (replacement_face_spec, 2)],
                   desc="replace_face 预选")
    before = _feature_snapshot(model)
    # 来源: SW2018 API 文档 IModelDoc2::InsertFeatureReplaceFace()
    _sub(model, "InsertFeatureReplaceFace", [()], "replace_face")
    return _feat_name(_new_feature(model, before))


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

PUBLIC_API = [
    # 参考几何
    "insert_ref_plane",
    "insert_axis",
    "insert_reference_point",
    "insert_coordinate_system",
    "find_ref_plane",
    # 曲线
    "helix",
    "spiral",
    "projected_curve",
    "composite_curve",
    "split_line",
    "curve_through_points",
    "curve_from_xyz_file",
    # 曲面
    "extruded_surface",
    "revolved_surface",
    "lofted_surface",
    "boundary_surface",
    "planar_surface",
    "fill_surface",
    "offset_surface",
    "extend_surface",
    "trim_surface",
    "untrim_surface",
    "knit_surface",
    "cut_with_surface",
    "replace_face",
]
