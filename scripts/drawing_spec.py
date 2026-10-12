# -*- coding: utf-8 -*-
"""drawing_spec.py — 将 drawing_spec JSON 转换为确定性的 SolidWorks 建模操作。

支持的 op（当前子集，够绘图类零件使用）：
  - extrude_boss / extrude_cut
  - simple_hole
  - mirror_feature
  - fillet_all
  - offset_plane

草图实体：line / arc3pt / circle / corner_rectangle。
所有输入坐标/尺寸单位：毫米（内部转米）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_core
import sw_sel
import sw_sketch
import sw_features
import sw_advanced

_PLANE_NAME_OK = {"front", "top", "right"}


def _mm(v):
    return sw_core.mm(float(v))


def _m(v):
    return float(v) / 1000.0


def draw_entities(model, entities):
    for ent in entities:
        t = ent["type"]
        if t == "line":
            p1, p2 = ent["p1"], ent["p2"]
            sw_sketch.line(model, _m(p1[0]), _m(p1[1]), _m(p2[0]), _m(p2[1]))
        elif t == "arc3pt":
            p1, p2, mid = ent["p1"], ent["p2"], ent["mid"]
            sw_sketch.arc3pt(model, _m(p1[0]), _m(p1[1]), _m(p2[0]), _m(p2[1]),
                             _m(mid[0]), _m(mid[1]))
        elif t == "circle":
            c, r = ent["center"], ent["r"]
            sw_sketch.circle(model, _m(c[0]), _m(c[1]), _m(r))
        elif t == "corner_rectangle":
            p1, p2 = ent["p1"], ent["p2"]
            sw_sketch.corner_rectangle(model, _m(p1[0]), _m(p1[1]),
                                       _m(p2[0]), _m(p2[1]))
        else:
            raise RuntimeError(f"drawing_spec: 未知草图实体 {t}")


def create_sketch(model, spec):
    name = spec.get("name") or f"sketch_{id(spec)}"
    plane = spec.get("plane", "front")
    sw_sketch.start_sketch(model, plane)
    draw_entities(model, spec.get("entities", []))
    sw_sketch.end_sketch(model)
    feat = sw_sketch.last_sketch_feature(model)
    # 通过命名让后续特征可引用
    try:
        feat.Name = name
    except Exception:
        pass
    return name


def make_plane(model, spec):
    base = spec.get("base", "front")
    distance = spec.get("distance_mm", 0)
    if base not in ("front", "top", "right"):
        raise RuntimeError(f"drawing_spec: 参考面 {base} 不支持")
    ret = sw_advanced.insert_ref_plane(model, plane_type="offset",
                                       base_spec=base, distance_mm=distance)
    name = ret[1] if isinstance(ret, tuple) else ret
    # 不重命名，避免 SelectByID2 按原名找不到
    return name


def build_from_spec(sw, spec):
    model = sw_core.new_part(sw)
    results = {}
    # 先创建所有草图（顺序保留）
    sketch_names = {}
    for sk in spec.get("sketches", []):
        name = create_sketch(model, sk)
        sketch_names[sk.get("id", name)] = name

    sk_by_ref = lambda ref: sketch_names.get(ref, ref)

    for feat in spec.get("features", []):
        op = feat["op"]
        key = feat.get("id", f"feat_{len(results)}")
        if op == "extrude_boss":
            sk = sk_by_ref(feat["sketch"])
            r = sw_features.extrude_boss(
                model, sketch=sk, depth_m=_m(feat.get("depth_mm", 10)),
                end_condition=feat.get("end_condition", "blind"),
                flip=feat.get("flip", False), direction2=feat.get("direction2", False))
            results[key] = {"feature": r.Name, "sketch": sk}
        elif op == "extrude_cut":
            sk = sk_by_ref(feat["sketch"])
            r = sw_features.extrude_cut(
                model, sketch=sk, depth_m=_m(feat.get("depth_mm", 10)),
                end_condition=feat.get("end_condition", "blind"),
                flip=feat.get("flip", False), direction2=feat.get("direction2", False))
            results[key] = {"feature": r.Name, "sketch": sk}
        elif op == "simple_hole":
            r = sw_features.simple_hole(
                model, feat["face"], diameter_m=_m(feat["diameter_mm"]),
                depth_m=_m(feat.get("depth_mm", 10)),
                position_mm=tuple(feat["position_mm"]))
            results[key] = {"feature": r.Name}
        elif op == "mirror_feature":
            seed_key = feat.get("seed")
            seed_name = results[seed_key]["feature"] if seed_key in results else seed_key
            plane_name = None
            if feat.get("plane_name"):
                plane_name = feat["plane_name"]
            elif feat.get("plane_offset"):
                plane_name = make_plane(model, feat["plane_offset"])
            r = sw_features.mirror_feature(model, seed_features=[seed_name],
                                           plane_name=plane_name)
            results[key] = {"feature": r.Name, "plane": plane_name}
        elif op == "fillet_all":
            sw_core.clear_selection(model)
            first = True
            for e in sw_sel._edges(model):
                sw_sel._select_entity(model, e, not first, 0)
                first = False
            r = sw_features.fillet(model, _m(feat["radius_mm"]), edge_specs=None)
            results[key] = {"feature": r.Name}
        elif op == "offset_plane":
            name = make_plane(model, feat)
            results[key] = {"plane": name}
        else:
            raise RuntimeError(f"drawing_spec: 未知 op {op}")
        print("  built", key, "->", results[key], flush=True)
    return model, results


def run_spec(spec, save=None):
    """按 spec 建模并保存，返回结果 dict。"""
    sw = sw_core.connect()
    model, results = build_from_spec(sw, spec)
    save_path = save or spec.get("output") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", spec.get("name", "drawing_part") + ".SLDPRT")
    saved = sw_core.save_as(model, save_path, sw=sw)
    return {"saved": saved,
            "features": {k: v["feature"] for k, v in results.items() if "feature" in v},
            "results": results}


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="按 drawing_spec.json 在 SolidWorks 建模")
    ap.add_argument("spec")
    ap.add_argument("--save", help="保存路径，默认 spec 的 output")
    args = ap.parse_args()
    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)
    sw = sw_core.connect()
    model, results = build_from_spec(sw, spec)
    save_path = args.save or spec.get("output") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", spec.get("name", "drawing_part") + ".SLDPRT")
    saved = sw_core.save_as(model, save_path, sw=sw)
    print("saved:", saved, flush=True)


if __name__ == "__main__":
    main()
