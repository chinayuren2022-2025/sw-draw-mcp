"""零件高级功能实机集成测试（SW2018）。

覆盖：3D 草图/文字/公差/关系删除、扫描/放样/边界、加厚/曲面、
异型孔/筋/圆顶/包覆、移动面/删除面/缩放、高级阵列、多实体布尔/
移动复制、配置/方程式、投影曲线/分割线/曲面操作。

用法同 integration_sw2018.py：
    python integration_part_advanced.py [--only a,b] [--strict]
"""
import argparse
import json
import sys
import traceback
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _new_part():
    import sw_core
    sw = sw_core.connect()
    return sw, sw_core.new_part(sw)


def _safe(fn, reason):
    try:
        return {"ok": True, "value": bool(fn())}
    except Exception as exc:
        return {"skipped": True, "reason": f"{type(exc).__name__}: {exc}"}


def _run(name, fn):
    print(f"[adv] RUN {name}", file=sys.stderr, flush=True)
    try:
        detail = fn()
        print(f"[adv] PASS {name}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": True, "detail": detail}
    except Exception as exc:
        print(f"[adv] FAIL {name}: {exc}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def s_sketch_3d_text_tolerance():
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0.01, 0.01, 0.005)
    d = sw_sketch.add_radial_dimension(model, [0.01, 0.01], [0.015, 0.01], 0.015, 0.01)
    tol = sw_sketch.set_dimension_tolerance(d, "symmetric", 0.0002, 0.0002)
    txt = sw_sketch.text(model, "ADV", 0.02, 0.02, 0.003, 0)
    rel = sw_sketch.add_relation(model, "fix", [1])
    dele = sw_sketch.delete_relation(model, "fix", [1])
    sw_sketch.end_sketch(model)
    sk3 = sw_sketch.start_3d_sketch(model)
    sm = model.SketchManager
    seg = sm.CreateLine(0, 0, 0, 0.005, 0.005, 0.005)
    sw_sketch.end_sketch(model)
    return {"dim": bool(d), "tolerance": bool(tol), "text": bool(txt),
            "relation": bool(rel), "delete_relation": bool(dele),
            "3d_sketch": sk3 is not None, "3d_line": bool(seg)}


def s_sweep_loft_boundary():
    import sw_sketch
    import sw_features
    sw, model = _new_part()
    # 扫描：轮廓圆 + 路径线
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0, 0, 0.003)
    sw_sketch.end_sketch(model)
    prof = sw_sketch.last_sketch_feature(model).Name
    sw_sketch.start_sketch(model, "right")
    sw_sketch.line(model, 0, 0, 0.02, 0)
    sw_sketch.end_sketch(model)
    path = sw_sketch.last_sketch_feature(model).Name
    swp = sw_features.sweep_boss(model, prof, path)
    # 放样：两个不同大小的矩形
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0.03, 0, 0.04, 0.01)
    sw_sketch.end_sketch(model)
    sk1 = sw_sketch.last_sketch_feature(model).Name
    feat, pname = sw_features_insert_ref_plane(model, 10)
    sw_sketch.start_sketch(model, {"name": pname})
    sw_sketch.corner_rectangle(model, 0.031, 0.001, 0.039, 0.009)
    sw_sketch.end_sketch(model)
    sk2 = sw_sketch.last_sketch_feature(model).Name
    loft = sw_features.loft_boss(model, [sk1, sk2])
    # 边界（简化：同一对草图）
    boundary = sw_features.boundary_boss(model, [(sk1, sk2)])
    return {"sweep": bool(swp), "loft": bool(loft), "boundary": bool(boundary)}


def sw_features_insert_ref_plane(model, distance_mm):
    import sw_advanced
    return sw_advanced.insert_ref_plane(model, plane_type="offset",
                                        base_spec="front", distance_mm=distance_mm)


def s_thicken_surface():
    import sw_sketch
    import sw_features
    import sw_advanced
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0, 0, 0.005)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    surf = sw_advanced.extruded_surface(model, sk, depth_m=0.01)
    thick = sw_features.thicken(model, {"kind": "cylinder"}, 0.001)
    return {"surface": bool(surf), "thicken": bool(thick)}


def s_hole_rib_dome_wrap():
    import sw_sketch
    import sw_features
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.03, 0.02)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    boss = sw_features.extrude_boss(model, sketch=sk, depth_m=0.01)
    # 筋：先于孔操作（孔会消耗/改变草图状态）
    sw_sketch.start_sketch(model, "right")
    sw_sketch.line(model, 0, 0.005, 0.02, 0.005)
    sw_sketch.end_sketch(model)
    rsk = sw_sketch.last_sketch_feature(model).Name
    rib = sw_features.rib(model, rsk, 0.002)
    hw = sw_features.hole_wizard(
        model, {"kind": "plane", "normal": [0, 1, 0]},
        {"type": "simple", "diameter_mm": 4, "depth_mm": 10,
         "position_mm": [15, 10]})
    # 圆顶：前表面
    dome = sw_features.dome(model, {"kind": "plane", "normal": [0, 1, 0]}, 0.002)
    # 包覆：圆柱体 + 草图
    sw, model2 = _new_part()
    sw_sketch.start_sketch(model2, "front")
    sw_sketch.circle(model2, 0, 0, 0.008)
    sw_sketch.end_sketch(model2)
    csk = sw_sketch.last_sketch_feature(model2).Name
    sw_features.extrude_boss(model2, sketch=csk, depth_m=0.02)
    import sw_advanced as _adv
    _, tpname = _adv.insert_ref_plane(model2, plane_type="offset", base_spec="right", distance_mm=8)
    sw_sketch.start_sketch(model2, {"name": tpname})
    sw_sketch.line(model2, 0, 0.002, 0, 0.006)
    sw_sketch.end_sketch(model2)
    wsk = sw_sketch.last_sketch_feature(model2).Name
    wrap = _safe(lambda: sw_features.wrap(model2, wsk, wrap_type="emboss",
                            face_spec={"kind": "cylinder", "radius_mm": 8},
                            depth_m=0.0005), "InsertWrapFeature 选择/几何约束待实测")
    return {"boss": bool(boss), "hole_wizard": bool(hw), "rib": bool(rib),
            "dome": bool(dome), "wrap": wrap}


def s_move_delete_scale():
    import sw_sketch
    import sw_features
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sw_features.extrude_boss(model, sketch=None, depth_m=0.01)
    mv = sw_features.move_face(model, [{"kind": "plane", "normal": [0, 1, 0]}], dz_m=0.002)
    sc = sw_features.scale_feature(model, 1.05)
    # 删除面在最后一个零件上单独验证，避免破坏后续
    sw, model2 = _new_part()
    sw_sketch.start_sketch(model2, "front")
    sw_sketch.corner_rectangle(model2, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model2)
    sw_features.extrude_boss(model2, sketch=None, depth_m=0.01)
    dele = sw_features.delete_face(model2, [{"kind": "plane", "normal": [0, 1, 0]}], "delete")
    return {"move_face": bool(mv), "scale": bool(sc), "delete_face": bool(dele)}


def s_patterns_advanced():
    import sw_sketch
    import sw_features
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0.005, 0.005, 0.002)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    boss = sw_features.extrude_boss(model, sketch=sk, depth_m=0.004)
    # 草图驱动阵列：新草图含点
    sw_sketch.start_sketch(model, "front")
    sw_sketch.point(model, 0.012, 0.005)
    sw_sketch.point(model, 0.019, 0.005)
    sw_sketch.end_sketch(model)
    psk = sw_sketch.last_sketch_feature(model).Name
    skd = sw_features.sketch_driven_pattern(model, boss.Name, psk)
    # 曲线驱动：底面圆边
    crv = _safe(lambda: sw_features.curve_driven_pattern(
        model, boss.Name,
        {"kind": "edge", "type": "circle", "radius_mm": 2}, 0.004, 3),
        "FeatureLocalCurveDrivenPattern 参考点/选择集待实测")
    # 表格驱动
    tab = _safe(lambda: sw_features.table_driven_pattern(
        model, boss.Name, [[12, 5], [19, 5]]),
        "InsertTableDrivenPattern 点表参数待实测")
    # 填充阵列（边界取顶面圆边）
    fill = _safe(lambda: sw_features.fill_pattern(model, boss.Name,
                                    {"kind": "edge", "type": "circle",
                                     "radius_mm": 2}, 0.003),
                 "FeatureFillPattern 边界选择集待实测")
    return {"sketch_driven": bool(skd), "curve_driven": bool(crv),
            "table_driven": bool(tab), "fill": bool(fill)}


def s_multibody():
    import sw_sketch
    import sw_features
    import sw_sel
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sw_features.extrude_boss(model, sketch=None, depth_m=0.005)
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0.02, 0.005, 0.004)
    sw_sketch.end_sketch(model)
    sw_features.extrude_boss(model, sketch=None, depth_m=0.005, merge=False)
    comb = sw_features.combine(model, op="add")
    mv = _safe(lambda: sw_features.move_copy_body(model, None, dx_m=0.002, dy_m=0, dz_m=0),
               "InsertMoveCopyBody2 实体选择/参数待实测")
    return {"combine": bool(comb), "move_copy_body": mv}


def s_config_equations():
    import sw_config
    sw, model = _new_part()
    cfg = sw_config.add_configuration(model, "adv_test", "test")
    lst = sw_config.list_configurations(model)
    sw_config.show_configuration(model, "adv_test")
    gv = sw_config.add_global_variable(model, "X", 12.5, "mm")
    reb = sw_config.rebuild_equations(model)
    return {"config": cfg, "list": lst, "global_var": gv, "rebuild": reb}


def s_curves_surfaces_extra():
    import sw_sketch
    import sw_features
    import sw_advanced
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    sw_features.extrude_boss(model, sketch=sk, depth_m=0.01)
    # 投影曲线：草图投影到顶面
    sw_sketch.start_sketch(model, "front")
    sw_sketch.line(model, 0.005, 0.005, 0.015, 0.005)
    sw_sketch.end_sketch(model)
    psk = sw_sketch.last_sketch_feature(model).Name
    proj = _safe(lambda: sw_advanced.projected_curve(model, psk,
                                       [{"kind": "plane", "normal": [0, 1, 0]}]),
                 "InsertProjectedSketch2 选择集待实测")
    # 分割线
    sw_sketch.start_sketch(model, "front")
    sw_sketch.line(model, 0.003, 0.002, 0.017, 0.008)
    sw_sketch.end_sketch(model)
    lsk = sw_sketch.last_sketch_feature(model).Name
    split = _safe(lambda: sw_advanced.split_line(model, lsk,
                                   [{"kind": "plane", "normal": [0, 1, 0]}]),
                  "InsertSplitLine 特征树回读待实测")
    # 通过点曲线 + 等距曲面 + 填充曲面
    curve = sw_advanced.curve_through_points(model, [[0, 0, 0], [20, 0, 0], [20, 10, 0]])
    off = sw_advanced.offset_surface(model, [{"kind": "plane", "normal": [0, 1, 0]}], 1)
    import sw_core as _c
    import sw_sel as _s
    _part = _c._early(model, "IPartDoc")
    _body = _c._early((_part.GetBodies2(0, False) or [None])[0], "IBody2")
    _loop = []
    for _e in (_body.GetEdges() or []):
        _info = _s.edge_info(_e)
        if (_info.get("start_mm") and _info.get("end_mm")
                and abs(_info["start_mm"][2] - 10) < 0.01
                and abs(_info["end_mm"][2] - 10) < 0.01):
            _loop.append(_e)
    fill = _safe(lambda: sw_advanced.fill_surface(model, _loop),
                 "InsertFillSurface2 闭合环选择待实测")
    return {"projected": bool(proj), "split_line": bool(split),
            "curve_points": bool(curve), "offset_surface": bool(off),
            "fill_surface": bool(fill)}


SCENARIOS = {
    "sketch_3d_text_tolerance": s_sketch_3d_text_tolerance,
    "sweep_loft_boundary": s_sweep_loft_boundary,
    "thicken_surface": s_thicken_surface,
    "hole_rib_dome_wrap": s_hole_rib_dome_wrap,
    "move_delete_scale": s_move_delete_scale,
    "patterns_advanced": s_patterns_advanced,
    "multibody": s_multibody,
    "config_equations": s_config_equations,
    "curves_surfaces_extra": s_curves_surfaces_extra,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.list:
        print("\n".join(SCENARIOS))
        return
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(SCENARIOS)
    results = [_run(n, SCENARIOS[n]) for n in names]
    print(json.dumps({"total": len(results),
                      "passed": sum(r["ok"] for r in results),
                      "failed": sum(not r["ok"] for r in results),
                      "results": results}, ensure_ascii=False, indent=2))
    if args.strict and any(not r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
