"""SW2018 Windows 实机集成测试（必须在 Windows + SolidWorks 2018 执行节点运行）。

用法：
    python tests/integration_sw2018.py            # 跑全部场景（每个场景新建零件）
    python tests/integration_sw2018.py --list     # 只列场景
    python tests/integration_sw2018.py --only sketch_entities,extrude_flange
    python tests/integration_sw2018.py --strict   # 任一失败即退出码 1

本脚本是补全清单 8.2 的可执行回归集。每个场景 try/except 后继续，输出
JSON 报告；失败信息里区分“签名不匹配 / 选择失败 / 几何失败”，用于后续修正
各模块的候选签名。
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _new_part():
    import sw_core
    sw = sw_core.connect()
    model = sw_core.new_part(sw)
    return sw, model


def _run(name, fn):
    print(f"[integration] RUN {name}", file=sys.stderr, flush=True)
    try:
        detail = fn()
        print(f"[integration] PASS {name}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": True, "detail": detail}
    except Exception as exc:
        print(f"[integration] FAIL {name}: {exc}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


# ---------- 场景 ----------

def s_status():
    import sw_core
    sw = sw_core.connect()
    return {"revision": str(sw.RevisionNumber()), "tlb_minor": sw_core.tlb_minor_for_sw(sw)}


def s_sketch_entities():
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    n = {}
    n["line"] = bool(sw_sketch.line(model, 0, 0, 0.01, 0))
    n["centerline"] = bool(sw_sketch.centerline(model, 0, -0.002, 0, 0.02))
    n["arc"] = bool(sw_sketch.arc(model, 0, 0, 0.01, 0, 0, 0.01, 1))
    n["circle"] = bool(sw_sketch.circle(model, 0.02, 0.02, 0.005))
    n["corner_rectangle"] = bool(sw_sketch.corner_rectangle(model, -0.01, -0.01, -0.005, -0.005))
    n["center_rectangle"] = bool(sw_sketch.center_rectangle(model, 0.02, -0.02, 0.025, -0.015))
    n["ellipse"] = bool(sw_sketch.ellipse(model, -0.02, 0.02, 0.008, 0.004, 0))
    n["polygon"] = bool(sw_sketch.polygon(model, -0.02, -0.02, 6, 0.006, True))
    n["slot"] = bool(sw_sketch.slot(model, 0.03, 0.03, 0.02, 0.006, 0))
    n["point"] = bool(sw_sketch.point(model, 0.03, -0.03))
    n["spline"] = bool(sw_sketch.spline(model, [(0.03, -0.02), (0.032, -0.024), (0.034, -0.02)]))
    segs = sw_sketch.segment_list(model)
    sw_sketch.end_sketch(model)
    return {"entities": n, "segment_count": len(segs)}


def s_sketch_dims_relations():
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    d1 = sw_sketch.add_linear_dimension(model, 0, 0, 0.02, 0, horizontal=True)
    d2 = sw_sketch.add_vertical_dimension(model, 0.02, 0, 0.02, 0.01)
    r1 = sw_sketch.add_relation(model, "horizontal", [1])
    sw_sketch.end_sketch(model)
    return {"dim1": bool(d1), "dim2": bool(d2), "relation": bool(r1)}


def s_sketch_edit():
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    off = sw_sketch.sketch_offset(model, 0.002, both_sides=False)
    sw_sketch.end_sketch(model)
    return {"offset": bool(off)}


def s_extrude_flange():
    import sw_part_dsl
    sw, model = _new_part()
    spec = {
        "sketches": [{"name": "sk1", "plane": "front",
                      "entities": [{"type": "corner_rectangle", "x1": 0, "y1": 0,
                                    "x2": 20, "y2": 10},
                                   {"type": "circle", "cx": 5, "cy": 5, "r": 2}],
                      "dims": [], "relations": []}],
        "features": [{"op": "extrude_boss", "sketch": "sk1", "depth_mm": 5},
                     {"op": "fillet", "radius_mm": 1,
                      "edge_specs": {"type": "line", "near_mm": [20, 0, 0]}},
                     {"op": "simple_hole", "face_spec": {"kind": "plane", "normal": [0, 0, 1]},
                      "diameter_mm": 3, "depth_mm": 5, "position_mm": [10, 5]}],
    }
    report = sw_part_dsl.build_part(spec, out_path=None, sw=sw, do_checks=True)
    return {"volume_mm3": report.get("volume_mm3_sw"),
            "steps": report.get("steps")}


def s_revolve():
    import sw_part_dsl
    sw, model = _new_part()
    spec = {
        "sketches": [{"name": "s", "plane": "front",
                      "entities": [{"type": "centerline", "x1": 0, "y1": -1, "x2": 0, "y2": 11},
                                   {"type": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 0},
                                   {"type": "line", "x1": 5, "y1": 0, "x2": 5, "y2": 8},
                                   {"type": "line", "x1": 5, "y1": 8, "x2": 0, "y2": 10}],
                      "dims": [], "relations": []}],
        "features": [{"op": "revolve_boss", "sketch": "s", "angle_deg": 360}],
    }
    report = sw_part_dsl.build_part(spec, out_path=None, sw=sw, do_checks=True)
    return {"volume_mm3": report.get("volume_mm3_sw")}


def s_patterns_mirror():
    import sw_features
    import sw_sketch
    sw, model = _new_part()
    # 线性阵列 + 镜像：矩形块用直线边做方向
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.01, 0.005)
    sw_sketch.end_sketch(model)
    sk1 = sw_sketch.last_sketch_feature(model).Name
    boss = sw_features.extrude_boss(model, sketch=sk1, depth_m=0.004)
    lin = sw_features.linear_pattern(
        model, boss.Name,
        {"kind": "edge", "type": "line", "near_mm": [5, 0, 0]},
        0.01, 2)
    mir = sw_features.mirror_feature(model, [boss.Name], plane_name="Top Plane")
    # 圆周阵列：圆柱体用圆柱面做轴
    sw, model2 = _new_part()
    sw_sketch.start_sketch(model2, "front")
    sw_sketch.circle(model2, 0.005, 0.005, 0.002)
    sw_sketch.end_sketch(model2)
    sk2 = sw_sketch.last_sketch_feature(model2).Name
    boss2 = sw_features.extrude_boss(model2, sketch=sk2, depth_m=0.004)
    cir = sw_features.circular_pattern(model2, boss2.Name,
                                       {"kind": "cylinder", "radius_mm": 2}, 90, 3)
    return {"boss": bool(boss), "linear": bool(lin), "circular": bool(cir),
            "mirror": bool(mir)}


def s_ref_geometry():
    import sw_advanced
    import sw_features
    sw, model = _new_part()
    import sw_sketch
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0, 0, 0.005)
    sw_sketch.end_sketch(model)
    feat = sw_sketch.last_sketch_feature(model)
    sw_features.extrude_boss(model, sketch=feat.Name, depth_m=0.005)
    plane, pname = sw_advanced.insert_ref_plane(model, plane_type="offset",
                                                base_spec="front", distance_mm=3)
    axis, aname = sw_advanced.insert_axis(
        model, axis_type="cylinder",
        base_spec={"kind": "cylinder", "radius_mm": 5})
    point = sw_advanced.insert_reference_point(
        model, point_type="face_center",
        base_spec={"kind": "cylinder", "radius_mm": 5})
    return {"plane": pname, "axis": aname, "point": bool(point)}


def s_curves_surfaces():
    import sw_advanced
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0, 0, 0.005)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    h = sw_advanced.helix(model, sk, height_mm=10, pitch_mm=4, revolutions=2.5)
    surf = sw_advanced.extruded_surface(model, sk, depth_m=0.005)
    return {"helix": bool(h), "surface": bool(surf)}


def s_shell_draft_hole():
    import sw_sketch
    import sw_features
    # 抽壳：空心块
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    sw_features.extrude_boss(model, sketch=sk, depth_m=0.01)
    sh = sw_features.shell(model, 0.001,
                           face_specs=[{"kind": "plane", "normal": [0, 0, 1]}])
    # 拔模：单独在实心块上验证（壳体内外侧面多义会挂起）
    sw, model2 = _new_part()
    sw_sketch.start_sketch(model2, "front")
    sw_sketch.corner_rectangle(model2, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model2)
    sk2 = sw_sketch.last_sketch_feature(model2).Name
    sw_features.extrude_boss(model2, sketch=sk2, depth_m=0.01)
    dr = sw_features.draft(model2, 2,
                           {"kind": "plane", "normal": [0, 0, 1]},
                           [{"kind": "plane", "normal": [0, 1, 0]}])
    return {"shell": bool(sh), "draft": bool(dr)}


def s_deep_check():
    import sw_check
    import sw_sketch
    sw, model = _new_part()
    sw_sketch.start_sketch(model, "front")
    sw_sketch.circle(model, 0, 0, 0.005)
    sw_sketch.end_sketch(model)
    report = sw_check.deep_check(model)
    return {"summary": report["summary"]}


def s_legacy_lens():
    import build_lens
    return build_lens.run({"type": "plano_convex", "D": 25, "f": 50,
                           "material": "BK7", "tolerance": "standard"},
                          os.path.join(os.path.dirname(__file__), "_it_lens.SLDPRT"),
                          dry_run=True)


def s_legacy_barrel():
    import build_barrel
    return build_barrel.derive({"outer_d": 27, "bore_d": 25.1, "seat_depth": 3,
                                "hole_d": 23, "length": 8})


SCENARIOS = {
    "status": s_status,
    "sketch_entities": s_sketch_entities,
    "sketch_dims_relations": s_sketch_dims_relations,
    "sketch_edit": s_sketch_edit,
    "extrude_flange": s_extrude_flange,
    "revolve": s_revolve,
    "patterns_mirror": s_patterns_mirror,
    "ref_geometry": s_ref_geometry,
    "curves_surfaces": s_curves_surfaces,
    "shell_draft_hole": s_shell_draft_hole,
    "deep_check": s_deep_check,
    "legacy_lens": s_legacy_lens,
    "legacy_barrel": s_legacy_barrel,
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
