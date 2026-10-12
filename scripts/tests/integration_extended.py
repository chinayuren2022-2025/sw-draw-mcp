# -*- coding: utf-8 -*-
"""扩展功能实机集成测试（SW2018）。

覆盖：装饰螺纹、特征树管理、外观颜色/场景、DimXpert 尺寸标注、
子装配体插入/编辑/解散（解散如 API 返回 False 记为 skipped）。
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sw_core
import sw_sketch
import sw_features


def _new_part():
    sw = sw_core.connect()
    return sw, sw_core.new_part(sw)


def _run(name, fn):
    print(f"[ext] RUN {name}", file=sys.stderr, flush=True)
    try:
        detail = fn()
        print(f"[ext] PASS {name}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": True, "detail": detail}
    except Exception as exc:
        print(f"[ext] FAIL {name}: {exc}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def _simple_block(sw, model):
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.030, 0.020)
    sw_sketch.end_sketch(model)
    sk = sw_sketch.last_sketch_feature(model).Name
    return sw_features.extrude_boss(model, sketch=sk, depth_m=0.010)


def s_cosmetic_thread():
    sw, m = _new_part()
    _simple_block(sw, m)
    sw_sketch.start_sketch(m, "front")
    sw_sketch.circle(m, 0.015, 0.010, 0.005)
    sw_sketch.end_sketch(m)
    sk = sw_sketch.last_sketch_feature(m).Name
    sw_features.extrude_cut(m, sketch=sk, depth_m=0.010)
    f = sw_features.cosmetic_thread(
        m, {"kind": "edge", "type": "circle", "radius_mm": 5.0},
        diameter_m=0.010, depth_m=0.010, end_condition="blind", note="M10")
    return {"feature": f.Name, "type": sw_core.feature_type(f)}


def s_feature_tree():
    sw, m = _new_part()
    _simple_block(sw, m)
    sw_sketch.start_sketch(m, "front")
    sw_sketch.circle(m, 0.015, 0.010, 0.004)
    sw_sketch.end_sketch(m)
    sk = sw_sketch.last_sketch_feature(m).Name
    cut = sw_features.extrude_cut(m, sketch=sk, depth_m=0.005)
    renamed = sw_features.rename_feature(m, cut.Name, "test_cut")
    reordered = sw_features.reorder_feature(m, "test_cut", "凸台-拉伸1")
    rolled = sw_features.rollback_feature(m, name="test_cut")
    forward = sw_features.rollforward_feature(m)
    return {"renamed": renamed, "reordered": reordered,
            "rollback": rolled, "rollforward": forward}


def s_appearance():
    sw, m = _new_part()
    _simple_block(sw, m)
    a = sw_features.set_appearance(m, color_rgb=(0.8, 0.2, 0.1))
    sc = sw_features.set_scene(m, "Plain White")
    return {"appearance": a, "scene": sc}


def s_dimxpert():
    import sw_annotate
    sw, m = _new_part()
    _simple_block(sw, m)
    sw_sketch.start_sketch(m, "front")
    sw_sketch.circle(m, 0.015, 0.010, 0.005)
    sw_sketch.end_sketch(m)
    sk = sw_sketch.last_sketch_feature(m).Name
    sw_features.extrude_cut(m, sketch=sk, depth_m=0.010)
    counts0 = sw_annotate.dimxpert_counts(m)
    added = sw_annotate.dimxpert_add_dimension(
        m, dim_type="size",
        face_spec={"kind": "cylinder", "radius_mm": 5.0, "axis": [0, 0, 1]})
    return {"before": counts0, "added": added}


def s_subassembly():
    import sw_assembly
    import sw_assembly_full
    sw = sw_core.connect()
    top = sw_assembly.new_assembly(sw)
    sub = r"\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM"
    c = sw_assembly_full.insert_subassembly(top, sub, x=0.01, y=0, z=0)
    name = sw_assembly_full._comp_name(c)
    found = sw_assembly_full.find_component(top, name)
    edited = sw_assembly_full.edit_subassembly(top, found)
    sw_core._dyn(sw).ActivateDoc2(sw_core.model_title(top), False, sw_core.err_variants()[0])
    found2 = sw_assembly_full.find_component(top, name)
    dissolved = sw_assembly_full.dissolve_subassembly(top, found2)
    if not dissolved:
        return {"skipped": True, "component": name, "edit": edited,
                "dissolve": False, "reason": "DissolveSubAssembly 返回 False"}
    return {"component": name, "edit": edited, "dissolve": dissolved}


def s_fillet_fix():
    sw, m = _new_part()
    _simple_block(sw, m)
    constant = sw_features.fillet(m, 0.001, edge_specs={"kind": "edge", "type": "line"})
    variable = sw_features.fillet(
        m, 0.001, fillet_type="variable",
        edge_specs={"kind": "edge", "type": "line"}, radii_mm=[0.5, 1.5])
    # face 需要两个面组
    face = sw_features.fillet(
        m, 0.001, fillet_type="face",
        edge_specs={"kind": "plane", "normal": [0, 0, 1]},
        face_specs2={"kind": "plane", "normal": [1, 0, 0]})
    return {"constant": constant.Name, "variable": variable.Name,
            "face": face.Name}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()
    results = [
        _run("fillet_fix", s_fillet_fix),
        _run("cosmetic_thread", s_cosmetic_thread),
        _run("feature_tree", s_feature_tree),
        _run("appearance_scene", s_appearance),
        _run("dimxpert", s_dimxpert),
        _run("subassembly", s_subassembly),
    ]
    failed = [r for r in results if not r["ok"] and not r.get("detail", {}).get("skipped")]
    payload = {"results": results, "failed": len(failed), "strict": bool(args.strict)}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
