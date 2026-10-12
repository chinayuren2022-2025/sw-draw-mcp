"""sw_sketch.py — SolidWorks 零件建模插件：完整草图绘制层（SW2018 / 类型库 v26）

设计约定（与 sw_core.py / sw_sel.py 一致）：
    - 对外坐标统一为“米”（SW API 内部单位）；需要毫米输入的函数在参数名
      带 _mm 并在内部用 sw_core.mm() 换算。
    - 不确定的 COM 方法签名统一走 sw_core.call_sigs 做多签名回退，
      每个候选元组前注明来源（SW API 常见签名 / TLB v26 常见签名）。
    - 早绑定：模型/草图/图元等对象经 sw_core._early 包装。
    - 本模块不修改任何既有文件，不 print（只在异常消息中给上下文）。

重要：本文件只在 Linux 上做语法检查，无法真正调用 COM。所有标有
“需在 SW2018 实测核对签名”的调用点，在集成测试时若参数数量/成员名
不符，请按 sw_core.is_arg_count_error 的提示修正候选元组。
"""
import functools
import math

import sw_core
import sw_sel

# ---------------------------------------------------------------------------
# 基础常量与内部工具
# ---------------------------------------------------------------------------

_PLANE_CANDIDATES = {
    "front": ["Front Plane", "前视基准面", "前视"],
    "top": ["Top Plane", "上视基准面", "上视"],
    "right": ["Right Plane", "右视基准面", "右视"],
}

# swSketchSegments_e（SW2018 v26 常见值；segment_info 里做 best-effort 映射）
_SEG_TYPE = {
    0: "line",
    1: "arc",
    2: "ellipse",
    3: "spline",
    4: "text",
    5: "parabola",
    6: "point",   # 部分版本点也可能进入 segments 集合
}

# 几何关系名 → ISketch.Add<Relation>Relation / Add<Relation>Relation2 方法名候选。
# 每个关系都按“更具体的 2 后缀方法”排前面。
_RELATION_METHODS = {
    "horizontal": ("AddHorizontalRelation2", "AddHorizontalRelation"),
    "vertical": ("AddVerticalRelation2", "AddVerticalRelation"),
    "coincident": ("AddCoincidentRelation2", "AddCoincidentRelation"),
    "concentric": ("AddConcentricRelation2", "AddConcentricRelation"),
    "coradial": ("AddCoradialRelation2", "AddCoradialRelation"),
    "parallel": ("AddParallelRelation2", "AddParallelRelation"),
    "perpendicular": ("AddPerpendicularRelation2", "AddPerpendicularRelation"),
    "tangent": ("AddTangentRelation2", "AddTangentRelation"),
    "collinear": ("AddCollinearRelation2", "AddCollinearRelation"),
    "equal": ("AddEqualRelation2", "AddEqualRelation"),
    "symmetric": ("AddSymmetricRelation2", "AddSymmetricRelation"),
    "fix": ("AddFixRelation2", "AddFixRelation"),
    "pierce": ("AddPierceRelation2", "AddPierceRelation"),
    "intersection": ("AddIntersectionRelation2", "AddIntersectionRelation"),
    "midpoint": ("AddMidpointRelation2", "AddMidpointRelation"),
}

# SW2018 v26 实测：关系添加应走 IModelDoc2::SketchAddConstraints(约束串)
_RELATION_SG = {
    "horizontal": "sgHORIZONTAL",
    "vertical": "sgVERTICAL",
    "coincident": "sgCOINCIDENT",
    "concentric": "sgCONCENTRIC",
    "coradial": "sgCORADIAL",
    "parallel": "sgPARALLEL",
    "perpendicular": "sgPERPENDICULAR",
    "tangent": "sgTANGENT",
    "collinear": "sgCOLLINEAR",
    "equal": "sgEQUAL",
    "symmetric": "sgSYMMETRIC",
    "fix": "sgFIX",
    "pierce": "sgPIERCE",
    "intersection": "sgINTERSECTION",
    "midpoint": "sgMIDPOINT",
}


def _fmt(v):
    """异常消息里的参数摘要格式化（不 print，不访问 COM 属性）。"""
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, (list, tuple)):
        head = ", ".join(_fmt(x) for x in list(v)[:6])
        return "[" + head + ("..." if len(v) > 6 else "") + "]"
    if isinstance(v, dict):
        items = list(v.items())[:6]
        head = ", ".join(f"{k}:{_fmt(val)}" for k, val in items)
        return "{" + head + ("..." if len(v) > 6 else "") + "}"
    try:
        return str(v)
    except Exception:
        return type(v).__name__


def _args_summary(args, kwargs):
    parts = [_fmt(a) for a in args[1:]]  # args[0] 是 model/segment 等 COM 对象，摘要太长
    parts += [f"{k}={_fmt(v)}" for k, v in kwargs.items()]
    return ", ".join(parts)


def _public(func):
    """公开函数统一异常包装：任何失败都转成带函数名+参数摘要的 RuntimeError。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"{func.__name__}({_args_summary(args, kwargs)}): {exc}"
            ) from exc
    return wrapper


def _sm(model):
    """取 SketchManager 早绑定视图（若 TLB 里有 ISketchManager）。"""
    return sw_core._early(model.SketchManager, "ISketchManager")


def _active_sketch(model):
    """当前编辑中的草图 ISketch；失败返回 None。"""
    try:
        return sw_core._early(model.SketchManager.ActiveSketch, "ISketch")
    except Exception:
        return None


def _sketch_or_raise(model, fn):
    sk = _active_sketch(model)
    if sk is None:
        raise RuntimeError(f"{fn}: 没有活动草图，请先调用 start_sketch / start_3d_sketch")
    return sk


def _segments(model, fn):
    sk = _sketch_or_raise(model, fn)
    segs = sk.GetSketchSegments() or []
    return [sw_core._early(s, "ISketchSegment") for s in segs]


def _seg_type_code(seg):
    """ISketchSegment.GetType 在 v26 中是属性（调用会报 int not callable）。"""
    try:
        return int(seg.GetType)
    except Exception:
        try:
            return int(seg.GetType())
        except Exception:
            return -1


def _select_data(model, mark):
    sm = sw_core._early(model.SelectionManager, "ISelectionMgr")
    data = sm.CreateSelectData()
    data.Mark = int(mark)
    return data


def _select_entity(model, entity, append, mark):
    """选择 IEntity（草图图元/点/边/面通用）。

    草图图元的 Select4/Select2 在早绑定 ISketchSegment 上可能缺失，
    回退到后期绑定 Dispatch 视图调用。
    """
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


def _clear_and_select(model, entities, mark=1):
    """清空选择并按顺序选择一组实体。"""
    model.ClearSelection2(True)
    for i, ent in enumerate(entities):
        if not _select_entity(model, ent, i > 0, mark):
            raise RuntimeError(f"选择实体失败: 第{i + 1}个实体 mark={mark}")
    return True


def _resolve_active_segments(model, specs, fn):
    """把 entity_specs 解析为活动草图图元列表。

    specs 支持：None（全部图元）、int（1 起 index）、ISketchSegment 对象、
    {"index": n}、以及它们的 list/tuple。
    """
    segs = _segments(model, fn)
    if specs is None:
        return segs
    if not isinstance(specs, (list, tuple)):
        specs = [specs]
    out = []
    for spec in specs:
        if isinstance(spec, int):
            idx = int(spec)
            if idx == 0:
                raise RuntimeError(f"{fn}: 图元 index 从 1 开始，收到 0")
            if idx < 0:
                idx += len(segs) + 1
            if idx < 1 or idx > len(segs):
                raise RuntimeError(f"{fn}: 图元 index={spec} 越界（共 {len(segs)} 个）")
            out.append(segs[idx - 1])
        elif isinstance(spec, dict):
            idx = int(spec.get("index", 0))
            if idx == 0:
                raise RuntimeError(f"{fn}: 图元 spec 缺少 index: {spec}")
            if idx < 0:
                idx += len(segs) + 1
            if idx < 1 or idx > len(segs):
                raise RuntimeError(f"{fn}: 图元 index={idx} 越界（共 {len(segs)} 个）")
            out.append(segs[idx - 1])
        else:
            # 视为 ISketchSegment 兼容对象
            out.append(spec)
    return out


def _select_segment_specs(model, specs, fn, mark=1):
    segs = _resolve_active_segments(model, specs, fn)
    if not segs:
        raise RuntimeError(f"{fn}: 没有可选择的图元")
    _clear_and_select(model, segs, mark=mark)
    return segs


def _segment_anchor_m(seg):
    """取图元参考点（米），用于 circular pattern 半径估算。"""
    try:
        p = seg.GetStartPoint2()
        if p is not None:
            return float(p[0]), float(p[1])
    except Exception:
        pass
    try:
        info = sw_sel.edge_info(seg)
        if "start_mm" in info:
            return info["start_mm"][0] / 1000.0, info["start_mm"][1] / 1000.0
        if "center_mm" in info:
            return info["center_mm"][0] / 1000.0, info["center_mm"][1] / 1000.0
    except Exception:
        pass
    return 0.0, 0.0


def _call_sigs_on_objects(objs, method, sigs, desc):
    """在多个对象上按候选签名回退调用同一方法名。"""
    last = None
    for obj in objs:
        if obj is None:
            continue
        try:
            return sw_core.call_sigs(obj, method, sigs, desc)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: {method} 在候选对象上均失败: {last}")


def _call_any_method(objs, methods, sigs, desc):
    """多方法名 × 多对象 × 多签名回退。"""
    last = None
    for method in methods:
        try:
            return _call_sigs_on_objects(objs, method, sigs, desc)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: 方法候选 {methods} 均失败: {last}")


def _call_sigs_allow_none(obj, method, sigs, desc):
    """同 sw_core.call_sigs，但允许方法成功时返回 None（void 方法）。

    适用于 MoveOrCopy / RotateOrCopy / ScaleOrCopy / SketchMirror 等
    VBA 中不接收返回值的 COM 方法。
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


def _call_sigs_on_objects_allow_none(objs, method, sigs, desc):
    """在多个对象上回退调用同一 void 方法名（None 返回视为成功）。"""
    last = None
    for obj in objs:
        if obj is None:
            continue
        try:
            return _call_sigs_allow_none(obj, method, sigs, desc)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: {method} 在候选对象上均失败: {last}")


def _call_any_method_allow_none(objs, methods, sigs, desc):
    """多方法名 × 多对象 × 多签名回退（None 返回视为成功）。"""
    last = None
    for method in methods:
        try:
            return _call_sigs_on_objects_allow_none(objs, method, sigs, desc)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{desc}: 方法候选 {methods} 均失败: {last}")


def _select_corner_point(model, corner_index_or_spec, fn):
    """选择草图角点（Point1/Point2/... 命名，与 VBA 示例一致）。"""
    if isinstance(corner_index_or_spec, int):
        name = f"Point{int(corner_index_or_spec)}"
    elif isinstance(corner_index_or_spec, dict):
        name = corner_index_or_spec.get("name") or f"Point{int(corner_index_or_spec.get('index', 1))}"
    else:
        name = str(corner_index_or_spec)
    model.ClearSelection2(True)
    if not sw_core.select_by_id(model, name, "SKETCHPOINT"):
        raise RuntimeError(f"{fn}: 无法选择草图角点 {name}")
    return name


def _insert_sketch(model):
    """进入草图（AddToDB=True 与 sw_part.start_sketch 行为一致）。"""
    model.SketchManager.InsertSketch(True)
    model.SketchManager.AddToDB = True


# ---------------------------------------------------------------------------
# 草图环境
# ---------------------------------------------------------------------------

@_public
def start_sketch(model, plane="front"):
    """在基准面上开始草图（SW API 坐标单位：米，这里只涉及基准面名）。

    plane 支持：
        - 'front' / 'top' / 'right'（中英文候选）
        - 任意已有基准面名，如 "Plane1" / "基准面1"
        - {"name": "..."} 字典
    返回实际选中的基准面名。AddToDB=True，与 sw_part.start_sketch 一致。

    需在 SW2018 实测核对签名：SelectByID2 的 Callout 参数在部分版本
    必须传空 Dispatch（sw_core.select_by_id 已处理）；InsertSketch 在
    早绑定下若返回 None 不代表失败。
    """
    model.ClearSelection2(True)
    name = plane
    if isinstance(plane, dict):
        name = plane.get("name", "front")
    key = str(name).lower() if isinstance(name, str) else ""
    candidates = _PLANE_CANDIDATES.get(key, [str(name)])
    last = None
    for cand in candidates:
        try:
            if sw_core.select_by_id(model, cand, "PLANE"):
                _insert_sketch(model)
                return cand
        except Exception as exc:
            # 单个候选失败继续下一个；全部失败再汇总抛出
            last = exc
    raise RuntimeError(f"start_sketch: 无法选择基准面 {plane}（最后错误: {last}）")


@_public
def start_sketch_on_face(model, face_spec):
    """用 sw_sel.select_face 选平面/曲面并在其上开始草图。

    返回 (IFace2, face_info)。AddToDB=True。
    """
    face, info = sw_sel.select_face(model, face_spec)
    _insert_sketch(model)
    return face, info


@_public
def start_3d_sketch(model):
    """开始 3D 草图。返回当前活动草图（ISketch 或 None）。"""
    model.ClearSelection2(True)
    sm = _sm(model)
    try:
        sm.Insert3DSketch(True)
    except Exception:
        sm.Insert3DSketch()
    return _active_sketch(model)


@_public
def end_sketch(model):
    """退出草图（草图保持选中状态，供特征命令使用）。"""
    model.SketchManager.AddToDB = False
    model.SketchManager.InsertSketch(True)
    return True


@_public
def active_sketch(model):
    """返回当前活动草图 ISketch；没有活动草图返回 None。"""
    return _active_sketch(model)


# ---------------------------------------------------------------------------
# 基本图元（坐标单位：米）
# ---------------------------------------------------------------------------

@_public
def line(model, x1, y1, x2, y2):
    """直线。CreateLine 返回 None 时按 sw_part.line 行为换向重试。"""
    sm = _sm(model)
    seg = sm.CreateLine(x1, y1, 0.0, x2, y2, 0.0)
    if seg is None:
        seg = sm.CreateLine(x2, y2, 0.0, x1, y1, 0.0)
    if seg is None:
        raise RuntimeError(f"line: CreateLine 失败 ({x1},{y1})->({x2},{y2})")
    return sw_core._early(seg, "ISketchSegment")


@_public
def centerline(model, x1, y1, x2, y2):
    """中心线。"""
    sm = _sm(model)
    seg = sm.CreateCenterLine(x1, y1, 0.0, x2, y2, 0.0)
    if seg is None:
        raise RuntimeError(f"centerline: CreateCenterLine 失败 ({x1},{y1})->({x2},{y2})")
    return sw_core._early(seg, "ISketchSegment")


@_public
def arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    """圆心+起终点圆弧。direction: 1=逆时针, -1=顺时针。

    SW2018 实测：CreateArc 对两端点到圆心等距的容差极严（0.34µm 偏差即返回
    对象但不入库）。此处校验入库数并给出两端点半径差，便于调用方精确共圆重试。
    """
    sm = _sm(model)
    before = len(_segments(model, "arc"))
    seg = sm.CreateArc(cx, cy, 0.0, x1, y1, 0.0, x2, y2, 0.0, direction)
    after = len(_segments(model, "arc"))
    if seg is None or after <= before:
        r1 = math.hypot(x1 - cx, y1 - cy)
        r2 = math.hypot(x2 - cx, y2 - cy)
        raise RuntimeError(
            f"arc: CreateArc 未入库 c=({cx},{cy}) a=({x1},{y1}) b=({x2},{y2})，"
            f"两端点半径 {r1:.9f}/{r2:.9f}，差 {abs(r1 - r2):.3e} m")
    return sw_core._early(seg, "ISketchSegment")


@_public
def arc3pt(model, x1, y1, x2, y2, x3, y3):
    """三点圆弧（Create3PointArc）。"""
    sm = _sm(model)
    before = len(_segments(model, "arc3pt"))
    seg = sw_core.call_sigs(
        sm, "Create3PointArc",
        [
            # SW API 常见签名：起点/中间点/终点各带 z
            (x1, y1, 0.0, x2, y2, 0.0, x3, y3, 0.0),
            # 旧版本偶见不带 z 的 6 参签名
            (x1, y1, x2, y2, x3, y3),
        ],
        f"arc3pt: Create3PointArc ({x1},{y1})/({x2},{y2})/({x3},{y3})",
    )
    after = len(_segments(model, "arc3pt"))
    if after <= before:
        raise RuntimeError(f"arc3pt: 三点圆弧未入库，三点可能共线："
                           f"({x1},{y1})/({x2},{y2})/({x3},{y3})")
    return sw_core._early(seg, "ISketchSegment")


@_public
def circle(model, cx, cy, r):
    """圆（CreateCircleByRadius）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateCircleByRadius",
        [
            # SW API 常见签名：圆心 xyz + 半径
            (cx, cy, 0.0, r),
            # 个别早期版本无 z
            (cx, cy, r),
        ],
        f"circle: CreateCircleByRadius c=({cx},{cy}) r={r}",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def circle3pt(model, x1, y1, x2, y2, x3, y3):
    """三点圆（CreateCircle）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateCircle",
        [
            # SW API 常见签名：三点各带 z
            (x1, y1, 0.0, x2, y2, 0.0, x3, y3, 0.0),
            # 旧版本偶见无 z
            (x1, y1, x2, y2, x3, y3),
        ],
        f"circle3pt: CreateCircle ({x1},{y1})/({x2},{y2})/({x3},{y3})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def ellipse(model, cx, cy, rx, ry, angle_deg=0):
    """椭圆。rx/ry 为长/短半轴（米），angle_deg 为长轴角度。

    CreateEllipse 多签名回退：
      1) TLB v26 常见签名：中心 xyz + 长轴端点 xyz + 短半轴长度（标量）。
      2) SW API 常见签名：中心 xyz + 长轴端点 xyz + 短轴端点 xyz。
    两者都需要由 rx/ry/angle_deg 计算长轴端点与短轴端点/半径。
    """
    a = math.radians(float(angle_deg))
    mx = cx + float(rx) * math.cos(a)
    my = cy + float(rx) * math.sin(a)
    nx = cx - float(ry) * math.sin(a)
    ny = cy + float(ry) * math.cos(a)
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateEllipse",
        [
            # TLB v26 / solidworks-automation-skill 参考签名：
            # CreateEllipse(cx,cy,cz, mx,my,mz, r_minor) —— 最后一个是短半轴长度
            (cx, cy, 0.0, mx, my, 0.0, float(ry)),
            # SW API 常见签名：中心 + 长轴端点 + 短轴端点（9 参）
            (cx, cy, 0.0, mx, my, 0.0, nx, ny, 0.0),
            # 无 z 的 6 参旧签名
            (cx, cy, mx, my, nx, ny),
        ],
        f"ellipse: CreateEllipse c=({cx},{cy}) rx={rx} ry={ry} angle={angle_deg}",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def spline(model, points):
    """样条曲线。points 为 [(x,y), ...]。

    SW2018 v26 实测：CreateSpline 的 PointData 必须以
    VARIANT(VT_ARRAY|VT_R8, [x1,y1,z1, ...]) 传递，直接传 list/tuple 返回 None。
    """
    if not points:
        raise RuntimeError("spline: points 为空")
    import pythoncom
    from win32com.client import VARIANT
    flat = []
    for p in points:
        flat.extend([float(p[0]), float(p[1]), 0.0])
    arg = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateSpline",
        [(arg,), (tuple(flat),)],
        f"spline: CreateSpline 共 {len(points)} 个点",
    )
    if seg is None:
        # 极少数版本只有 CreateSpline2(pointsArray, closed)
        seg = sw_core.call_sigs(
            sw_core._dyn(sm), "CreateSpline2",
            [(arg, False), (tuple(flat), False)],
            f"spline: CreateSpline2 回退 共 {len(points)} 个点",
        )
    return sw_core._early(seg, "ISketchSegment")


@_public
def corner_rectangle(model, x1, y1, x2, y2):
    """角点矩形（CreateCornerRectangle）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateCornerRectangle",
        [
            # SW API 常见签名：两对角点各带 z
            (x1, y1, 0.0, x2, y2, 0.0),
            # 旧版本无 z
            (x1, y1, x2, y2),
        ],
        f"corner_rectangle: ({x1},{y1})-({x2},{y2})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def center_rectangle(model, cx, cy, x2, y2):
    """中心矩形（CreateCenterRectangle）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateCenterRectangle",
        [
            # SW API 常见签名：中心 xyz + 角点 xyz
            (cx, cy, 0.0, x2, y2, 0.0),
            # 旧版本无 z
            (cx, cy, x2, y2),
        ],
        f"center_rectangle: c=({cx},{cy}) corner=({x2},{y2})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def three_point_corner_rectangle(model, x1, y1, x2, y2, x3, y3):
    """三点角点矩形（Create3PointCornerRectangle）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "Create3PointCornerRectangle",
        [
            # SW API 常见签名：三点各带 z
            (x1, y1, 0.0, x2, y2, 0.0, x3, y3, 0.0),
            # 旧版本无 z
            (x1, y1, x2, y2, x3, y3),
        ],
        f"three_point_corner_rectangle: ({x1},{y1})/({x2},{y2})/({x3},{y3})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def three_point_center_rectangle(model, cx, cy, x1, y1, x2, y2):
    """三点中心矩形（Create3PointCenterRectangle）。

    参数顺序按“中心 → 第一个角点 → 第二点”传递，SW2018 具体顺序
    需在实测中核对（部分版本第二/三点含义相反）。
    """
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "Create3PointCenterRectangle",
        [
            # SW API 常见签名：中心 xyz + 点1 xyz + 点2 xyz
            (cx, cy, 0.0, x1, y1, 0.0, x2, y2, 0.0),
            # 旧版本无 z
            (cx, cy, x1, y1, x2, y2),
        ],
        f"three_point_center_rectangle: c=({cx},{cy}) p1=({x1},{y1}) p2=({x2},{y2})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def parallelogram(model, x1, y1, x2, y2, x3, y3):
    """平行四边形（CreateParallelogram）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreateParallelogram",
        [
            # SW API 常见签名：三点各带 z
            (x1, y1, 0.0, x2, y2, 0.0, x3, y3, 0.0),
            # 旧版本无 z
            (x1, y1, x2, y2, x3, y3),
        ],
        f"parallelogram: ({x1},{y1})/({x2},{y2})/({x3},{y3})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def polygon(model, cx, cy, n, radius, inscribed=True):
    """正多边形。n 为边数，radius 为半径（米），inscribed=True 内切圆/False 外接圆。

    CreatePolygon 多签名回退：
      1) TLB v26 / solidworks-automation-skill 参考签名：
         中心 xyz + 顶点 xyz + 边数 + 是否内切（8 参）。
      2) SW API 常见签名：中心 xyz + 边数 + 半径 + 是否内切（6 参）。
      3) 无 z 的 5 参旧签名。
    """
    vx = cx + float(radius)
    vy = cy
    flag = 1 if inscribed else 0
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreatePolygon",
        [
            # TLB v26 参考：CreatePolygon(cx,cy,cz, vx,vy,vz, sides, inscribed)
            (cx, cy, 0.0, vx, vy, 0.0, int(n), flag),
            # SW API 常见：CreatePolygon(cx,cy,cz, sides, radius, inscribed)
            (cx, cy, 0.0, int(n), float(radius), flag),
            # 旧版本无 z
            (cx, cy, int(n), float(radius), flag),
        ],
        f"polygon: c=({cx},{cy}) n={n} radius={radius} inscribed={inscribed}",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def slot(model, cx, cy, length, width, angle_deg=0):
    """直槽口。优先调用 CreateSketchSlot（line 类型 + CenterCenter 长度类型），
    失败时用四角点近似回退：两条直线 + 两个端部半圆弧。

    length 为两端圆弧中心距（米），width 为槽宽（米）。
    CreateSketchSlot 参数顺序（第 4 参起）：
      Width, X1,Y1,Z1, X2,Y2,Z2, X3,Y3,Z3, CenterArcDirection, AddDimension。
    点1/点2 为中心线两端点；点3 = 点2 + 垂直方向 × width。
    需在 SW2018 实测核对签名：swSketchSlotCreationType_line / 
    swSketchSlotLengthType_CenterCenter 的枚举值在不同版本可能不同。
    """
    a = math.radians(float(angle_deg))
    dx, dy = math.cos(a), math.sin(a)
    hx, hy = length / 2.0 * dx, length / 2.0 * dy
    p1 = (cx - hx, cy - hy)
    p2 = (cx + hx, cy + hy)
    # 宽度方向：中心线垂直方向（逆时针 +90°）
    px, py = -dy, dx
    p3 = (p2[0] + px * width, p2[1] + py * width)
    sm = _sm(model)
    try:
        slot_obj = sw_core.call_sigs(
            sm, "CreateSketchSlot",
            [
                # SW2018 TLB v26 实测参考（thecadcoder VBA 示例）：
                # (CreationType, LengthType, Width, x1,y1,z1, x2,y2,z2,
                #  x3,y3,z3, CenterArcDirection, AddDimension)
                (0, 0, float(width),
                 p1[0], p1[1], 0.0, p2[0], p2[1], 0.0,
                 p3[0], p3[1], 0.0, 0, False),
                # 部分版本无 CenterArcDirection 参数（13 参）
                (0, 0, float(width),
                 p1[0], p1[1], 0.0, p2[0], p2[1], 0.0,
                 p3[0], p3[1], 0.0, False),
            ],
            f"slot: CreateSketchSlot c=({cx},{cy}) length={length} width={width}",
        )
        return slot_obj
    except RuntimeError:
        # 四角点近似直槽：两个端部半圆弧 + 两条直线
        r = width / 2.0
        top1 = (p1[0] + px * r, p1[1] + py * r)
        bot1 = (p1[0] - px * r, p1[1] - py * r)
        top2 = (p2[0] + px * r, p2[1] + py * r)
        bot2 = (p2[0] - px * r, p2[1] - py * r)
        segs = [
            arc(model, p1[0], p1[1], top1[0], top1[1], bot1[0], bot1[1], 1),
            line(model, top1[0], top1[1], top2[0], top2[1]),
            arc(model, p2[0], p2[1], bot2[0], bot2[1], top2[0], top2[1], 1),
            line(model, bot2[0], bot2[1], bot1[0], bot1[1]),
        ]
        return segs


@_public
def point(model, x, y):
    """草图点（CreatePoint）。"""
    sm = _sm(model)
    seg = sw_core.call_sigs(
        sm, "CreatePoint",
        [
            # SW API 常见签名：xyz
            (x, y, 0.0),
            # 旧版本无 z
            (x, y),
        ],
        f"point: ({x},{y})",
    )
    return sw_core._early(seg, "ISketchSegment")


@_public
def set_construction(segment, on=True):
    """设置/读取图元 ConstructionGeometry 属性。返回设置后的布尔值。"""
    seg = sw_core._early(segment, "ISketchSegment")
    sw_core.com_set(seg, "ConstructionGeometry", bool(on))
    return bool(sw_core.com_get(seg, "ConstructionGeometry"))


@_public
def text(model, text, x, y, height_m, angle_deg=0):
    """插入草图文字。

    优先活动草图 InsertSketchText 族，其次 IModelDoc2.InsertSketchText /
    IInsertSketchText；多签名回退。插入后尝试设置 Height/Angle 属性
    （部分版本该属性名为 IHeight/IAngle 或只读，失败不致命）。

    需在 SW2018 实测核对签名：IModelDoc2.InsertSketchText 参数为
    (Ptx,Pty,Ptz,Text,Alignment,FlipDirection,HorizontalMirror,
     WidthFactor,SpaceBetweenChars)，不含字高；字高需通过返回的
    ISketchText.Height 设置，单位很可能为米。
    """
    sk = _active_sketch(model)
    objs = [o for o in (sk, model) if o is not None]
    sigs = [
        # SW2018 VBA 示例签名（WidthFactor=100%, SpaceBetweenChars=100%）
        (x, y, 0.0, str(text), 0, 0, 0, 100, 100),
        (x, y, 0.0, str(text), 0, 0, 0, 100.0, 100.0),
        # 无 Alignment/Flip/Mirror 的简化签名（部分老版本）
        (x, y, 0.0, str(text), 0, 0, 0),
        (x, y, 0.0, str(text)),
    ]
    ret = _call_any_method(
        objs, ["InsertSketchText", "IInsertSketchText"], sigs,
        f"text: InsertSketchText '{str(text)[:20]}' ({x},{y}) h={height_m}",
    )
    if ret is not None:
        for prop in ("Height", "IHeight"):
            try:
                sw_core.com_set(ret, prop, float(height_m))
                break
            except Exception:
                continue
        for prop in ("Angle", "IAngle"):
            try:
                sw_core.com_set(ret, prop, math.radians(float(angle_deg)))
                break
            except Exception:
                continue
    return ret


# ---------------------------------------------------------------------------
# 图元信息与编辑（基于活动草图 ISketch.GetSketchSegments()）
# ---------------------------------------------------------------------------

@_public
def segment_info(seg):
    """返回单个草图图元的信息字典。

    键：index(调用方填入)、type_code、type、以及 sw_sel.edge_info 提供的
    start_mm/end_mm/center_mm/radius_mm/length_mm 等（单位毫米）。
    类型名映射：line/arc/ellipse/spline/text/point/other。
    """
    seg = sw_core._early(seg, "ISketchSegment")
    info = {}
    try:
        info.update(sw_sel.edge_info(seg))
    except Exception as exc:
        info["params_error"] = str(exc)
    tc = _seg_type_code(seg)
    info["type_code"] = tc
    info["type"] = _SEG_TYPE.get(tc, "other")
    if "start_mm" not in info:
        try:
            p = seg.GetStartPoint2()
            if p is not None:
                info["start_mm"] = [float(v) * 1000.0 for v in p]
        except Exception:
            pass
    if "end_mm" not in info:
        try:
            p = seg.GetEndPoint2()
            if p is not None:
                info["end_mm"] = [float(v) * 1000.0 for v in p]
        except Exception:
            pass
    return info


@_public
def segment_list(model):
    """列出活动草图全部图元，返回 [{"index","type","start_mm","end_mm",...}]。

    index 为 1 起（与后续 sketch_* 的 index 参数一致）。
    """
    out = []
    for i, seg in enumerate(_segments(model, "segment_list"), 1):
        rec = segment_info(seg)
        rec["index"] = i
        out.append(rec)
    return out


@_public
def sketch_fillet(model, radius_m, corner_index_or_spec):
    """在指定草图角点处创建圆角。

    实现：先选择角点（int → "PointN"），再调用
    SketchManager.CreateFillet(Radius, ConstrainedCorners)。
    ConstrainedCorners 候选按“删除约束几何/保留几何/交互”排列。

    需在 SW2018 实测核对签名：swConstrainedCornerAction_e 枚举值
    （DeleteGeometry=2 / KeepGeometry=1 / Interact=0）。
    """
    _select_corner_point(model, corner_index_or_spec, "sketch_fillet")
    sm = _sm(model)
    ret = sw_core.call_sigs(
        sm, "CreateFillet",
        [
            # SW API 常见签名：(Radius, ConstrainedCorners)
            (float(radius_m), 2),   # 2 = swConstrainedCornerDeleteGeometry
            (float(radius_m), 1),   # 1 = swConstrainedCornerKeepGeometry
            (float(radius_m), 0),   # 0 = swConstrainedCornerInteract
        ],
        f"sketch_fillet: radius_m={radius_m} corner={corner_index_or_spec}",
    )
    return ret


@_public
def sketch_chamfer(model, d1_m, d2_m, corner_index_or_spec):
    """在指定草图角点处创建倒角（距离-距离型）。

    实现：选择角点后调用 SketchManager.CreateChamfer(Type, Distance, AngleOrDist)。
    Type 候选：0 = swSketchChamfer_DistanceDistance，2 = DistanceEqual 兜底。

    需在 SW2018 实测核对签名：swSketchChamferType_e 枚举值。
    """
    _select_corner_point(model, corner_index_or_spec, "sketch_chamfer")
    sm = _sm(model)
    ret = sw_core.call_sigs(
        sm, "CreateChamfer",
        [
            # SW API 常见签名：(Type, Distance, AngleOrDist)
            (0, float(d1_m), float(d2_m)),  # 0 = swSketchChamfer_DistanceDistance
            (2, float(d1_m), float(d2_m)),  # 2 = swSketchChamfer_DistanceEqual 兜底
        ],
        f"sketch_chamfer: d1={d1_m} d2={d2_m} corner={corner_index_or_spec}",
    )
    return ret


@_public
def sketch_trim(model, x, y, z):
    """草图剪裁。先选中要剪裁的图元，再调用 SketchManager.SketchTrim(x,y,z)。

    需在 SW2018 实测核对签名：SketchTrim 参数在多数版本中不被使用。
    """
    sm = _sm(model)
    return bool(sm.SketchTrim(float(x), float(y), float(z)))


@_public
def sketch_extend(model, x, y, z):
    """草图延伸。先选中要延伸的图元，再调用 SketchManager.SketchExtend(x,y,z)。

    需在 SW2018 实测核对签名：SketchExtend 参数在多数版本中不被使用。
    """
    sm = _sm(model)
    return bool(sm.SketchExtend(float(x), float(y), float(z)))


@_public
def sketch_offset(model, distance_m, both_sides=False, make_construction=False):
    """等距实体。先选择活动草图图元，再调用 SketchOffset。

    SW2018 v26 实测签名：
      - ISketchManager.SketchOffset(Offset, BothDirections, Chain, CapEnds,
                                    MakeConstruction, AddDimensions) 6 参；
      - IModelDoc2.SketchOffset(Offset, ContourMode) 2 参。
    """
    if sw_sel.selected_count(model) <= 0:
        _select_segment_specs(model, None, "sketch_offset", mark=0)
    sm = _sm(model)
    try:
        ret = sw_core.call_sigs(
            sm, "SketchOffset",
            [((float(distance_m), bool(both_sides), False, False,
               bool(make_construction), False))],
            f"sketch_offset(sm): distance_m={distance_m}")
        return bool(ret)
    except Exception as exc_sm:
        try:
            ret = sw_core.call_sigs(
                model, "SketchOffset",
                [((float(distance_m), 0)), ((float(distance_m), 1))],
                f"sketch_offset(model): distance_m={distance_m}")
            return bool(ret)
        except Exception as exc_model:
            raise RuntimeError(
                f"sketch_offset: SketchOffset 失败 distance_m={distance_m}；"
                f"sm 错误: {exc_sm}；model 错误: {exc_model}") from exc_model


@_public
def sketch_mirror(model, entity_specs, axis_entity_spec):
    """草图镜像。axis_entity_spec 选中心线（mark=2），entity_specs 选要镜像
    的图元（mark=1），然后调用 ModelDoc2.SketchMirror / SketchManager.SketchMirror。

    entity_specs/axis_entity_spec 支持 int（1 起）、{"index": n}、
    ISketchSegment 及其列表。

    需在 SW2018 实测核对签名：SketchMirror 在 IModelDoc2 上为无参方法，
    且要求中心线 mark=2、图元 mark=1。
    """
    axis_segs = _resolve_active_segments(model, axis_entity_spec, "sketch_mirror")
    ent_segs = _resolve_active_segments(model, entity_specs, "sketch_mirror")
    if not axis_segs or not ent_segs:
        raise RuntimeError("sketch_mirror: 中心线或待镜像图元为空")
    model.ClearSelection2(True)
    # 先选中心线（mark=2），再追加待镜像图元（mark=1）
    if not _select_entity(model, axis_segs[0], False, 2):
        raise RuntimeError("sketch_mirror: 无法选择镜像中心线")
    for i, seg in enumerate(ent_segs):
        if not _select_entity(model, seg, True, 1):
            raise RuntimeError(f"sketch_mirror: 无法选择第 {i + 1} 个待镜像图元")
    ret = _call_any_method_allow_none(
        [model, _sm(model)], ["SketchMirror"], [()],
        f"sketch_mirror: entities={_fmt(entity_specs)} axis={_fmt(axis_entity_spec)}",
    )
    return bool(ret)


@_public
def sketch_linear_pattern(model, entity_specs, dx_m, dy_m, n_x, n_y):
    """草图线性阵列。先选择图元（mark=1），再调用
    SketchManager.CreateLinearSketchStepAndRepeat。

    参数顺序：NumX, NumY, SpacingX, SpacingY, AngleX, AngleY,
    DeleteInstances, XSpacingDim, YSpacingDim, AngleDim,
    CreateNumOfInstancesDimInXDir, CreateNumOfInstancesDimInYDir。

    需在 SW2018 实测核对签名：12 参为常见签名，旧版本可能只有 10 参。
    """
    _select_segment_specs(model, entity_specs, "sketch_linear_pattern", mark=1)
    sm = _sm(model)
    ret = sw_core.call_sigs(
        sm, "CreateLinearSketchStepAndRepeat",
        [
            # SW2018 VBA 常见 12 参签名
            (int(n_x), int(n_y), float(dx_m), float(dy_m),
             0, 0, "", False, False, False, False, False),
            # 旧版本 10 参签名（无最后两个实例数尺寸开关）
            (int(n_x), int(n_y), float(dx_m), float(dy_m),
             0, 0, "", False, False, False),
        ],
        f"sketch_linear_pattern: dx={dx_m} dy={dy_m} nx={n_x} ny={n_y}",
    )
    return bool(ret)


@_public
def sketch_circular_pattern(model, entity_specs, cx_m, cy_m, angle_deg, n, equal=True):
    """草图圆周阵列。先选择图元（mark=1），再调用
    SketchManager.CreateCircularSketchStepAndRepeat。

    ArcRadius 由第一个图元参考点到 (cx_m,cy_m) 的距离估算；
    equal=True 时 PatternSpacing = angle_deg/(n-1)（总角均分），
    equal=False 时 PatternSpacing = angle_deg（单步角）。

    需在 SW2018 实测核对签名：
    (ArcRadius, ArcAngle, PatternNum, PatternSpacing, PatternRotate,
     DeleteInstances, RadiusDim, AngleDim, CreateNumOfInstancesDim)。
    """
    segs = _select_segment_specs(model, entity_specs, "sketch_circular_pattern", mark=1)
    ax, ay = _segment_anchor_m(segs[0])
    radius = math.hypot(ax - cx_m, ay - cy_m)
    if radius <= 1e-12:
        radius = 1e-3  # 防御：半径不能为 0，实测需确认 SW 是否接受极小值
    spacing = (float(angle_deg) / max(1, int(n) - 1)) if equal else float(angle_deg)
    sm = _sm(model)
    ret = sw_core.call_sigs(
        sm, "CreateCircularSketchStepAndRepeat",
        [
            # SW2018 VBA 常见 9 参签名
            (float(radius), 0.0, int(n), float(spacing), True,
             "", True, True, True),
        ],
        f"sketch_circular_pattern: c=({cx_m},{cy_m}) angle={angle_deg} n={n} equal={equal}",
    )
    return bool(ret)


@_public
def sketch_move_copy(model, entity_specs, dx_m, dy_m, copy=True):
    """移动/复制草图图元。选择图元后调用
    Extension.MoveOrCopy(Copy, NumCopies, KeepRelations, BaseX, BaseY, BaseZ,
    DestX, DestY, DestZ)。

    需在 SW2018 实测核对签名：MoveOrCopy 常见 9 参。
    """
    _select_segment_specs(model, entity_specs, "sketch_move_copy", mark=1)
    ext = model.Extension
    ret = _call_sigs_allow_none(
        sw_core._dyn(ext), "MoveOrCopy",
        [
            # SW API 常见签名：(Copy, NumCopies, KeepRelations, BaseX/Y/Z, DestX/Y/Z)
            (bool(copy), 1, True, 0.0, 0.0, 0.0, float(dx_m), float(dy_m), 0.0),
            # 旧版本无 KeepRelations / Base 的简化签名（少见）
            (bool(copy), 1, float(dx_m), float(dy_m), 0.0),
        ],
        f"sketch_move_copy: dx={dx_m} dy={dy_m} copy={copy}",
    )
    return bool(ret)


@_public
def sketch_rotate_copy(model, entity_specs, cx_m, cy_m, angle_deg, copy=True):
    """旋转/复制草图图元。选择图元后调用
    Extension.RotateOrCopy(Copy, NumCopies, KeepRelations, BaseX/Y/Z,
    DestX/Y/Z, Angle)。

    DestX/Y/Z = (0,0,1) 表示绕 Z 轴（草图平面法向）。

    需在 SW2018 实测核对签名：RotateOrCopy 常见 10 参。
    """
    _select_segment_specs(model, entity_specs, "sketch_rotate_copy", mark=1)
    ext = model.Extension
    ret = _call_sigs_allow_none(
        sw_core._dyn(ext), "RotateOrCopy",
        [
            # SW API 常见签名：(Copy, NumCopies, KeepRelations, BaseX/Y/Z,
            # DestX/Y/Z, Angle)
            (bool(copy), 1, True, float(cx_m), float(cy_m), 0.0,
             0.0, 0.0, 1.0, math.radians(float(angle_deg))),
        ],
        f"sketch_rotate_copy: c=({cx_m},{cy_m}) angle={angle_deg} copy={copy}",
    )
    return bool(ret)


@_public
def sketch_scale(model, entity_specs, factor, cx_m=0, cy_m=0):
    """缩放草图图元。选择图元后调用
    Extension.ScaleOrCopy(Copy, NumCopies, KeepRelations, BaseX/Y/Z, ScaleFactor)。

    需在 SW2018 实测核对签名：ScaleOrCopy 常见 7 参（基点为缩放中心）。
    """
    _select_segment_specs(model, entity_specs, "sketch_scale", mark=1)
    ext = model.Extension
    ret = _call_sigs_allow_none(
        sw_core._dyn(ext), "ScaleOrCopy",
        [
            # SW API 常见签名：(Copy, NumCopies, KeepRelations, BaseX/Y/Z, Factor)
            (False, 1, True, float(cx_m), float(cy_m), 0.0, float(factor)),
        ],
        f"sketch_scale: factor={factor} base=({cx_m},{cy_m})",
    )
    return bool(ret)


@_public
def sketch_convert_entities(model, edge_specs):
    """转换实体引用。先用 sw_sel.select_edge 选择实体边，再调用
    SketchManager.SketchUseEdge2。

    edge_specs 为 sw_sel.select_edge 的面/边 spec 或 spec 列表。
    需在 SW2018 实测核对签名：SketchUseEdge2 参数可能是 (True)/(True,True)/无参。
    """
    if edge_specs is None:
        raise RuntimeError("sketch_convert_entities: edge_specs 为空")
    if not isinstance(edge_specs, (list, tuple)):
        edge_specs = [edge_specs]
    model.ClearSelection2(True)
    for i, spec in enumerate(edge_specs):
        edge, _ = sw_sel.select_edge(model, spec, append=(i > 0), mark=0)
        if edge is None:
            raise RuntimeError(f"sketch_convert_entities: 第 {i + 1} 条边选择失败")
    sm = _sm(model)
    ret = _call_sigs_on_objects_allow_none(
        [sm, model], "SketchUseEdge2",
        [
            # SW API 常见签名：SketchUseEdge2(ConvertAllEntities)
            (True,),
            # 部分版本：SketchUseEdge2(ConvertAllEntities, SelectInnerLoops)
            (True, True),
            # 极旧版本无参
            (),
        ],
        f"sketch_convert_entities: {_fmt(edge_specs)}",
    )
    return bool(ret)


@_public
def sketch_intersection_curve(model, face_specs):
    """交叉曲线。先用 sw_sel.select_face 选择曲面，再调用
    SketchManager.SketchIntersectionCurve / IntersectCurves。

    需在 SW2018 实测核对签名：方法名与参数个数均需实测确认。
    """
    if face_specs is None:
        raise RuntimeError("sketch_intersection_curve: face_specs 为空")
    if not isinstance(face_specs, (list, tuple)):
        face_specs = [face_specs]
    model.ClearSelection2(True)
    for i, spec in enumerate(face_specs):
        face, _ = sw_sel.select_face(model, spec, append=(i > 0), mark=0)
        if face is None:
            raise RuntimeError(f"sketch_intersection_curve: 第 {i + 1} 个面选择失败")
    sm = _sm(model)
    ret = _call_any_method_allow_none(
        [sm, model], ["SketchIntersectionCurve", "IntersectCurves"],
        [
            # 常见：无参或一个布尔开关
            (),
            (True,),
            (False,),
        ],
        f"sketch_intersection_curve: {_fmt(face_specs)}",
    )
    return bool(ret)


# ---------------------------------------------------------------------------
# 尺寸（ISketch.AddDimension2 族 / IModelDoc2.Add*Dimension2 族）
# ---------------------------------------------------------------------------

@_public
def add_dimension2(model, x1, y1, x2, y2, text_x, text_y, dim_type):
    """raw 封装：在活动草图上添加尺寸。

    优先尝试 ISketch.AddDimension2(x1,y1,z1,x2,y2,z2,textx,texty,textz,type)；
    失败回退 IModelDoc2.AddDimension2(textx,texty,textz)（选择集方式）。

    需在 SW2018 实测核对签名：ISketch.AddDimension2 与
    IModelDoc2.AddDimension2 参数个数/含义可能不同。
    """
    sk = _active_sketch(model)
    sigs = [
        # SW API 常见签名：两点 + 文本位置 + 类型
        (x1, y1, 0.0, x2, y2, 0.0, text_x, text_y, 0.0, int(dim_type)),
        # 无类型参数
        (x1, y1, 0.0, x2, y2, 0.0, text_x, text_y, 0.0),
        # IModelDoc2 常见签名：仅文本位置（选择集方式）
        (text_x, text_y, 0.0),
    ]
    objs = [o for o in (sk, model) if o is not None]
    ret = _call_any_method(
        objs, ["AddDimension2"], sigs,
        f"add_dimension2: ({x1},{y1})-({x2},{y2}) text=({text_x},{text_y}) type={dim_type}",
    )
    return ret


def _select_segment_for_point(model, x, y, fn):
    """选择端点/中点最靠近 (x,y) 的草图图元（用于尺寸选择）。"""
    segs = _segments(model, fn)
    best, best_d = None, None
    for seg in segs:
        info = segment_info(seg)
        cands = []
        for key in ("start_mm", "end_mm", "center_mm"):
            v = info.get(key)
            if v is not None and len(v) >= 2:
                cands.append((v[0] / 1000.0, v[1] / 1000.0))
        for cx, cy in cands:
            d = math.hypot(cx - x, cy - y)
            if best_d is None or d < best_d:
                best, best_d = seg, d
    if best is None:
        raise RuntimeError(f"{fn}: 找不到靠近 ({x},{y}) 的草图图元")
    return best


@_public
def add_linear_dimension(model, x1, y1, x2, y2, horizontal=True):
    """线性尺寸。按 (x1,y1)/(x2,y2) 就近选择两个草图图元后调用
    AddHorizontalDimension2 / AddVerticalDimension2。

    需在 SW2018 实测核对签名：AddHorizontalDimension2(textx,texty,textz)
    为 IModelDoc2 选择集方式。
    """
    seg1 = _select_segment_for_point(model, x1, y1, "add_linear_dimension")
    seg2 = _select_segment_for_point(model, x2, y2, "add_linear_dimension")
    _clear_and_select(model, [seg1, seg2], mark=0)
    text_x, text_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    method = "AddHorizontalDimension2" if horizontal else "AddVerticalDimension2"
    ret = _call_any_method(
        [model], [method],
        [
            # SW API 常见签名：文本位置 xyz
            (text_x, text_y, 0.0),
        ],
        f"add_linear_dimension: ({x1},{y1})-({x2},{y2}) horizontal={horizontal}",
    )
    return ret


@_public
def add_horizontal_dimension(model, x1, y1, x2, y2):
    """水平尺寸。"""
    return add_linear_dimension(model, x1, y1, x2, y2, horizontal=True)


@_public
def add_vertical_dimension(model, x1, y1, x2, y2):
    """竖直尺寸。"""
    return add_linear_dimension(model, x1, y1, x2, y2, horizontal=False)


def _select_arc_near(model, cx, cy, fn):
    """选择中心最靠近 (cx,cy) 的圆弧/圆图元。"""
    segs = _segments(model, fn)
    best, best_d = None, None
    for seg in segs:
        info = segment_info(seg)
        center = info.get("center_mm")
        if center is None:
            continue
        d = math.hypot(center[0] / 1000.0 - cx, center[1] / 1000.0 - cy)
        if best_d is None or d < best_d:
            best, best_d = seg, d
    if best is None:
        raise RuntimeError(f"{fn}: 找不到靠近 ({cx},{cy}) 的圆弧/圆")
    return best


@_public
def add_radial_dimension(model, arc_center, arc_point, text_x, text_y):
    """半径尺寸。选择中心最靠近 arc_center 的圆弧/圆后调用
    AddRadialDimension2(textx,texty,textz)。

    需在 SW2018 实测核对签名：AddRadialDimension2 为选择集方式。
    """
    seg = _select_arc_near(model, arc_center[0], arc_center[1], "add_radial_dimension")
    _clear_and_select(model, [seg], mark=0)
    ret = _call_any_method(
        [model], ["AddRadialDimension2", "IAddRadialDimension2"],
        [
            # SW API 常见签名：文本位置 xyz
            (float(text_x), float(text_y), 0.0),
        ],
        f"add_radial_dimension: center={_fmt(arc_center)} point={_fmt(arc_point)}",
    )
    return ret


@_public
def add_diameter_dimension(model, arc_center, arc_point, text_x, text_y):
    """直径尺寸。选择圆弧/圆后调用 AddDiameterDimension2。

    需在 SW2018 实测核对签名：AddDiameterDimension2 为选择集方式。
    """
    seg = _select_arc_near(model, arc_center[0], arc_center[1], "add_diameter_dimension")
    _clear_and_select(model, [seg], mark=0)
    ret = _call_any_method(
        [model], ["AddDiameterDimension2", "IAddDiameterDimension2"],
        [
            # SW API 常见签名：文本位置 xyz
            (float(text_x), float(text_y), 0.0),
        ],
        f"add_diameter_dimension: center={_fmt(arc_center)} point={_fmt(arc_point)}",
    )
    return ret


@_public
def add_angular_dimension(model, p1, p2, p3, p4, text_x, text_y):
    """角度尺寸。选择两条线（分别由 (p1,p2) 与 (p3,p4) 就近匹配）后调用
    IModelDoc2.AddDimension2(textx,texty,textz)（选择集方式）。

    需在 SW2018 实测核对签名：角度尺寸可能需选择两条直线而不是点。
    """
    seg1 = _select_segment_for_point(model, p1[0], p1[1], "add_angular_dimension")
    seg2 = _select_segment_for_point(model, p3[0], p3[1], "add_angular_dimension")
    _clear_and_select(model, [seg1, seg2], mark=0)
    ret = _call_any_method(
        [model], ["AddDimension2"],
        [
            # IModelDoc2 常见签名：仅文本位置
            (float(text_x), float(text_y), 0.0),
        ],
        f"add_angular_dimension: ({_fmt(p1)}-{_fmt(p2)})/({_fmt(p3)}-{_fmt(p4)})",
    )
    return ret


@_public
def set_dimension_driven(dim, driven=True):
    """设置尺寸为驱动/从动（Driven 属性）。返回设置后的值。"""
    sw_core.com_set(dim, "Driven", bool(driven))
    return bool(sw_core.com_get(dim, "Driven"))


@_public
def dimension_name(dim):
    """读取尺寸名称。优先 Name 属性，其次 GetName()。"""
    try:
        return str(sw_core.com_get(dim, "Name"))
    except Exception:
        return str(sw_core.com_get(dim, "GetName"))


# ---------------------------------------------------------------------------
# 几何关系
# ---------------------------------------------------------------------------

@_public
def add_relation(model, relation, targets, add_to_db=True):
    """在活动草图中添加几何关系。

    relation ∈ horizontal/vertical/coincident/concentric/coradial/parallel/
    perpendicular/tangent/collinear/equal/symmetric/fix/pierce/
    intersection/midpoint。

    targets 为图元 index、ISketchSegment 或选择 spec（见
    _resolve_active_segments）。内部先选择目标，再依次回退
    ISketch.Add<Relation>Relation / Add<Relation>Relation2 方法。

    需在 SW2018 实测核对签名：这些 Add*Relation* 方法是否存在、是否需要
    传 AddToDB 参数，均需实测；若不存在，DSL 侧应改用
    model.SketchAddConstraints("sgHORIZONTAL") 的替代路径。
    """
    rel = str(relation).lower()
    if rel not in _RELATION_METHODS:
        raise RuntimeError(f"add_relation: 未知关系 {relation}")
    segs = _resolve_active_segments(model, targets, "add_relation")
    if not segs:
        raise RuntimeError("add_relation: targets 为空")
    _clear_and_select(model, segs, mark=0)
    # 首选：IModelDoc2.SketchAddConstraints（void，SW2018 v26 实测可用）
    sg = _RELATION_SG[rel]
    try:
        model.SketchAddConstraints(sg)
        return True
    except Exception as exc_sg:
        # 回退：ISketch.Add<Relation>Relation 族（部分版本不存在）
        sk = _sketch_or_raise(model, "add_relation")
        methods = list(_RELATION_METHODS[rel])
        sigs = [(bool(add_to_db),), (True,), ()]
        try:
            ret = _call_any_method_allow_none(
                [sk], methods, sigs,
                f"add_relation: {rel} targets={_fmt(targets)}",
            )
            return bool(ret)
        except Exception as exc_legacy:
            raise RuntimeError(
                f"add_relation: {rel} 失败；SketchAddConstraints 错误: {exc_sg}；"
                f"旧式关系方法错误: {exc_legacy}") from exc_legacy


@_public
def find_sketch_feature_by_name(model, name):
    """按名称遍历特征树查找草图特征（ProfileFeature）。未找到返回 None。"""
    for feat in sw_core.walk_features(model):
        if sw_core.feature_type(feat) != "ProfileFeature":
            continue
        if sw_core.feature_name(feat) == name:
            return feat
    return None


@_public
def last_sketch_feature(model):
    """返回特征树中最近一个草图特征（ProfileFeature）；没有返回 None。"""
    last = None
    for feat in sw_core.walk_features(model):
        if sw_core.feature_type(feat) == "ProfileFeature":
            last = feat
    return last


@_public
def delete_relation(model, relation, targets):
    """删除几何关系（补全清单 3.4.2）。

    relation 取值同 add_relation；targets 解析方式同 add_relation。
    实现：选择目标图元后依次回退 ISketch / ISketchManager 的
    DeleteRelation / DeleteRelation2 / DeleteRelation 族。

    需在 SW2018 实测核对签名：删除关系在部分版本只接受 ISketchRelation
    对象，若本函数失败请先遍历关系对象再删除。
    """
    rel = str(relation).lower()
    segs = _resolve_active_segments(model, targets, "delete_relation")
    if not segs:
        raise RuntimeError("delete_relation: targets 为空")
    _clear_and_select(model, segs, mark=0)
    # SW2018 v26：删除关系走 IModelDoc2.SketchConstraintsDel(索引, 约束串)
    sg = _RELATION_SG.get(rel, "")
    try:
        model.SketchConstraintsDel(0, sg)
        return True
    except Exception as exc_sg:
        try:
            model.SketchConstraintsDel(0, "")
            return True
        except Exception:
            pass
    objs = [o for o in (_sketch_or_raise(model, "delete_relation"), _sm(model))
            if o is not None]
    sigs = []
    if len(segs) >= 2:
        sigs.append((segs[0], segs[1]))
    for s in segs:
        sigs.append((s,))
    sigs.append(())
    try:
        ret = _call_any_method_allow_none(
            objs, ["DeleteRelation2", "DeleteRelation"], sigs,
            f"delete_relation: {rel} targets={_fmt(targets)}",
        )
        return bool(ret)
    except Exception as exc_legacy:
        raise RuntimeError(
            f"delete_relation: {rel} 删除失败；SketchConstraintsDel 错误: {exc_sg}；"
            f"旧式方法错误: {exc_legacy}") from exc_legacy


_TOL_TYPES = {"none": 0, "basic": 1, "bilateral": 2, "limit": 3,
              "symmetric": 4, "min": 5, "max": 6, "fit": 7,
              "fit_with_tolerance": 8, "fit_min": 9}


@_public
def set_dimension_tolerance(dim, tol_type="symmetric", max_m=0.0, min_m=0.0):
    """设置尺寸公差（补全清单 3.3.5，P3）。

    SW2018 v26 实测：AddRadialDimension2 返回的 DisplayDimension 没有
    Tolerance 属性；需先 GetDimension2()/GetDimension 取得 IDimension，
    再访问其 Tolerance（IDimensionTolerance）。
    """
    code = _TOL_TYPES.get(str(tol_type).lower())
    if code is None:
        raise RuntimeError(f"set_dimension_tolerance: 未知公差类型 {tol_type}")
    dimobj = None
    for getter in ("GetDimension2", "GetDimension"):
        try:
            v = sw_core.com_get(dim, getter)  # 属性/方法二义
            if v is None:
                continue
            if getattr(v, "Tolerance", None) is not None:
                dimobj = v
                break
        except Exception:
            continue
    if dimobj is None:
        raise RuntimeError("set_dimension_tolerance: 无法取得 IDimension/IDimensionTolerance")
    try:
        tol = dimobj.Tolerance
    except Exception as exc:
        raise RuntimeError(f"set_dimension_tolerance: 无法取得 IDimensionTolerance: {exc}") from exc
    try:
        tol.Type = int(code)
    except Exception as exc:
        raise RuntimeError(f"set_dimension_tolerance: 设置 Type 失败: {exc}") from exc
    for attr in ("MaximumVariation", "MaxVariation"):
        try:
            setattr(tol, attr, float(max_m))
            break
        except Exception:
            continue
    for attr in ("MinimumVariation", "MinVariation"):
        try:
            setattr(tol, attr, float(min_m))
            break
        except Exception:
            continue
    return tol


# ---------------------------------------------------------------------------
# 导出清单
# ---------------------------------------------------------------------------

PUBLIC_API = [
    "start_sketch",
    "start_sketch_on_face",
    "start_3d_sketch",
    "end_sketch",
    "active_sketch",
    "line",
    "centerline",
    "arc",
    "arc3pt",
    "circle",
    "circle3pt",
    "ellipse",
    "spline",
    "corner_rectangle",
    "center_rectangle",
    "three_point_corner_rectangle",
    "three_point_center_rectangle",
    "parallelogram",
    "polygon",
    "slot",
    "point",
    "set_construction",
    "text",
    "segment_list",
    "segment_info",
    "sketch_fillet",
    "sketch_chamfer",
    "sketch_trim",
    "sketch_extend",
    "sketch_offset",
    "sketch_mirror",
    "sketch_linear_pattern",
    "sketch_circular_pattern",
    "sketch_move_copy",
    "sketch_rotate_copy",
    "sketch_scale",
    "sketch_convert_entities",
    "sketch_intersection_curve",
    "add_dimension2",
    "add_linear_dimension",
    "add_horizontal_dimension",
    "add_vertical_dimension",
    "add_radial_dimension",
    "add_diameter_dimension",
    "add_angular_dimension",
    "set_dimension_driven",
    "dimension_name",
    "add_relation",
    "delete_relation",
    "set_dimension_tolerance",
    "find_sketch_feature_by_name",
    "last_sketch_feature",
]
