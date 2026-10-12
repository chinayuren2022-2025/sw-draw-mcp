"""sw_part.py — 草图层与特征层原子工具（第3层）

特征级抽象（LLM 只应调用 build_lens.py 里的 create_lens）：
    草图层：start_sketch / line / arc / centerline / end_sketch
    特征层：revolve_boss / chamfer_edges / inspect
所有坐标单位：米。
"""
import math

# 基准面中英文候选（SW 2016 按界面语言命名）
_PLANE_CANDIDATES = {
    "front": ["Front Plane", "前视基准面", "前视"],
    "top": ["Top Plane", "上视基准面", "上视"],
    "right": ["Right Plane", "右视基准面", "右视"],
}


def start_sketch(model, plane="front"):
    """在基准面上开始草图，自动适配中英文界面。

    AddToDB=True：绘制期间关闭捕捉/自动关系，防止端点被吸附到
    同平面已有草图的图元上（实测 12.55mm 被吸到 13.5mm 的坑）。
    """
    import sw_core
    model.ClearSelection2(True)
    for name in _PLANE_CANDIDATES[plane.lower()]:
        if sw_core.select_by_id(model, name, "PLANE"):
            model.SketchManager.InsertSketch(True)
            model.SketchManager.AddToDB = True
            return name
    raise RuntimeError(f"无法选择基准面: {plane}")


def end_sketch(model):
    """退出草图（草图保持选中状态，供特征命令使用）。"""
    model.SketchManager.AddToDB = False
    model.SketchManager.InsertSketch(True)


def line(model, x1, y1, x2, y2):
    seg = model.SketchManager.CreateLine(x1, y1, 0.0, x2, y2, 0.0)
    if seg is None:
        # SW 对个别方向（如自垂线端点沿 +X 起笔）会拒绝，换向重试
        seg = model.SketchManager.CreateLine(x2, y2, 0.0, x1, y1, 0.0)
    if seg is None:
        raise RuntimeError(f"CreateLine 失败 ({x1},{y1})->({x2},{y2})")
    return seg


def centerline(model, x1, y1, x2, y2):
    return model.SketchManager.CreateCenterLine(x1, y1, 0.0, x2, y2, 0.0)


def _sketch_segment_count(model):
    """活动草图中图元数；读取失败返回 -1。"""
    try:
        sk = model.SketchManager.ActiveSketch
        return len(sk.GetSketchSegments() or []) if sk is not None else -1
    except Exception:
        return -1


def arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    """圆心+起终点圆弧。direction: 1=逆时针, -1=顺时针。

    SW2018 CreateArc 对“两端点到圆心距离相等”容差极严：实测偏差 0.34µm 时
    返回对象但不入库（GetSketchSegments 数量不变）。这里校验入库数，
    失败时给出两端点半径，便于调用方用精确共圆参数重试。
    """
    before = _sketch_segment_count(model)
    seg = model.SketchManager.CreateArc(cx, cy, 0.0, x1, y1, 0.0, x2, y2, 0.0, direction)
    after = _sketch_segment_count(model)
    if seg is None or (before >= 0 and after <= before):
        r1 = math.hypot(x1 - cx, y1 - cy)
        r2 = math.hypot(x2 - cx, y2 - cy)
        raise RuntimeError(
            f"CreateArc 未入库（seg={seg is not None}, count {before}->{after}）："
            f"c=({cx},{cy}) a=({x1},{y1}) b=({x2},{y2})，"
            f"两端点半径 {r1:.9f}/{r2:.9f}，差 {abs(r1 - r2):.3e} m；"
            "请保证两端点严格在同一圆上")
    return seg


def revolve_boss(model, angle_rad=2 * math.pi, is_cut=False):
    """旋转凸台/切除。要求草图已退出且含且仅含一条中心线（自动识别为轴）。

    注意：轮廓建议贴合中心线（接触轴线）。不接触轴线的偏移轮廓
    需要额外做轮廓选择，本函数不处理（见 build_barrel 的分段切除策略）。
    """
    # 本机 TLB (v26) 实测签名（20 参 + PFeat 返回值，顺序 Dir1Type, Dir2Type, Dir1Angle, Dir2Angle）：
    feat = model.FeatureManager.FeatureRevolve2(
        True, True, False, is_cut, False, False,  # SingleDir..BothDirectionUpToSameEntity
        0, 0, angle_rad, 0.0,                    # Dir1Type, Dir2Type, Dir1Angle, Dir2Angle
        False, False, 0.0, 0.0,                  # OffsetReverse1/2, OffsetDistance1/2
        0, 0.0, 0.0,                             # ThinType, ThinThickness1/2
        True, True, True,                        # Merge, UseFeatScope, UseAutoSelect
    )
    if feat is None:
        raise RuntimeError("FeatureRevolve2 失败（检查草图是否闭合、是否只有一条中心线）")
    return feat


def chamfer_selected(model, distance_m, angle_deg=45.0):
    """对已选中的边线倒角（距离-角度型）。"""
    feat = model.FeatureManager.InsertFeatureChamfer(
        4,                      # swChamferType_e: angle-distance
        1,                      # Propagation
        distance_m,             # Distance
        math.radians(angle_deg),
        0.0, 0.0, 0.0, 0.0,
    )
    return feat


def set_part_material(model, sw_material_db, material_name):
    """赋 SW 材料库材料（若库中存在；光学玻璃一般不在库内，可跳过）。"""
    return model.SetMaterialPropertyName2("", sw_material_db, material_name)
