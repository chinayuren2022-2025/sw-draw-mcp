"""装配体功能实机集成测试（SW2018，经 pwsh 桥接运行）。

覆盖 sw_assembly_full：全配合类型/编辑删除抑制、零部件状态管理、
组件阵列/镜像、干涉/质量/重建检查、装配切除、配合参考、虚拟零件、替换删除。
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = r"\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output"
BLOCK = os.path.join(OUT, "asm_block.SLDPRT")
PIN = os.path.join(OUT, "asm_pin.SLDPRT")


def _new_asm():
    import sw_core
    import sw_assembly
    sw = sw_core.connect()
    asm = sw_assembly.new_assembly(sw)
    return sw, asm


def _build_parts():
    if os.path.exists(BLOCK) and os.path.exists(PIN):
        return BLOCK, PIN
    import sw_core
    import sw_features
    import sw_sketch
    sw = sw_core.connect()
    # 方块 20x10x5 mm
    model = sw_core.new_part(sw)
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sw_features.extrude_boss(model, sketch=None, depth_m=0.005)
    sw_core.save_as(model, BLOCK, sw=sw)
    # 圆柱 r5 h10 mm
    model2 = sw_core.new_part(sw)
    sw_sketch.start_sketch(model2, "front")
    sw_sketch.circle(model2, 0, 0, 0.005)
    sw_sketch.end_sketch(model2)
    sw_features.extrude_boss(model2, sketch=None, depth_m=0.010)
    sw_core.save_as(model2, PIN, sw=sw)
    return BLOCK, PIN


def _run(name, fn):
    print(f"[asm] RUN {name}", file=sys.stderr, flush=True)
    try:
        detail = fn()
        print(f"[asm] PASS {name}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": True, "detail": detail}
    except Exception as exc:
        print(f"[asm] FAIL {name}: {exc}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def _insert(asm, path, x=0, y=0, z=0):
    import sw_assembly_full
    return sw_assembly_full.insert_component_full(asm, path, x=x, y=y, z=z)


def s_setup_parts():
    return {"parts": _build_parts()}


def s_mates_coincident_distance():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    c2 = _insert(asm, BLOCK, x=0.021)
    f1 = sw_assembly.find_face(c1, kind="plane", normal=[1, 0, 0])[0]
    f2 = sw_assembly.find_face(c2, kind="plane", normal=[-1, 0, 0])[0]
    mate, err = sw_assembly_full.add_mate_full(asm, f1, f2, "coincident", align="closest")
    lst = sw_assembly_full.list_mates(asm)
    supp = sw_assembly_full.suppress_mate(asm, mate.Name, True)
    del_ok = sw_assembly_full.delete_mate(asm, mate.Name)
    return {"mate": mate.Name, "err": err, "mates": [m["name"] for m in lst],
            "suppress": supp, "delete": del_ok}


def s_mates_parallel_distance():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    c2 = _insert(asm, BLOCK, x=0.021)
    f1 = sw_assembly.find_face(c1, kind="plane", normal=[1, 0, 0])[0]
    f2 = sw_assembly.find_face(c2, kind="plane", normal=[1, 0, 0])[0]
    mate1, e1 = sw_assembly_full.add_mate_full(asm, f1, f2, "distance", distance_m=0.001)
    f3 = sw_assembly.find_face(c1, kind="plane", normal=[0, 1, 0])[0]
    f4 = sw_assembly.find_face(c2, kind="plane", normal=[0, 1, 0])[0]
    mate2, e2 = sw_assembly_full.add_mate_full(asm, f3, f4, "parallel")
    return {"distance": (mate1.Name, e1), "parallel": (mate2.Name, e2)}


def s_component_state():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    fixed = sw_assembly_full.is_fixed(c1)
    fl = sw_assembly_full.fix_component(asm, c1)
    fixed2 = sw_assembly_full.is_fixed(c1)
    vis = sw_assembly_full.set_component_visible(c1, False)
    vis2 = sw_assembly_full.set_component_visible(c1, True)
    sup = sw_assembly_full.set_component_suppression(c1, "suppressed")
    res = sw_assembly_full.set_component_suppression(c1, "resolved")
    mv = sw_assembly_full.move_component(asm, c1, dx_m=0.001)
    return {"fixed": fixed, "fix": fl, "fixed2": fixed2, "vis": vis,
            "vis2": vis2, "suppress": sup, "resolve": res, "move": mv}


def s_patterns_components():
    import sw_assembly_full
    import sw_core as _c
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    c2 = _insert(asm, PIN, x=0.008, y=0.005)
    edges = _c.com_get(c1.GetBody(), "GetEdges") or []
    edge = edges[0] if edges else None
    lin = sw_assembly_full.linear_pattern_components(
        asm, c2, edge, 0.006, 2)
    mir = sw_assembly_full.mirror_components(asm, [c2], plane_name="Top Plane")
    return {"linear": bool(lin), "mirror": bool(mir)}


def s_checks():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    c2 = _insert(asm, BLOCK, x=0.010)  # 与 c1 重叠，干涉
    inter = sw_assembly_full.assembly_interference(asm)
    mp = sw_assembly_full.assembly_mass_properties(asm)
    rep = sw_assembly_full.assembly_rebuild_report(asm)
    return {"interference": inter, "mass": {k: mp.get(k) for k in
            ("volume_m3", "mass_kg")}, "rebuild": rep["rebuild_ok"]}


def s_assembly_cut():
    import sw_assembly_full
    import sw_sketch
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    sw_sketch.start_sketch(asm, "front")
    sw_sketch.circle(asm, 0.010, 0.005, 0.003)
    sw_sketch.end_sketch(asm)
    sk = sw_sketch.last_sketch_feature(asm).Name
    cut = sw_assembly_full.assembly_cut(asm, sk, 0.005, affected_components=[c1])
    return {"cut": bool(cut)}


def s_mate_reference():
    import sw_assembly_full
    import sw_core
    import sw_features
    import sw_sketch
    sw = sw_core.connect()
    model = sw_core.new_part(sw)
    sw_sketch.start_sketch(model, "front")
    sw_sketch.corner_rectangle(model, 0, 0, 0.02, 0.01)
    sw_sketch.end_sketch(model)
    sw_features.extrude_boss(model, sketch=None, depth_m=0.005)
    ref = sw_assembly_full.add_mate_reference(
        model, "Ref-A", {"kind": "plane", "normal": [0, 1, 0]})
    return {"mate_reference": bool(ref)}


def s_virtual_part():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    comp = sw_assembly_full.insert_new_virtual_part(asm)
    saved = None
    if comp is not None and not isinstance(comp, int):
        saved = sw_assembly_full.save_virtual_component(comp, os.path.join(OUT, "virtual_part.SLDPRT"))
    return {"virtual": bool(comp), "saved": saved}


def s_replace_delete():
    import sw_assembly
    import sw_assembly_full
    sw, asm = _new_asm()
    c1 = _insert(asm, BLOCK)
    c2 = _insert(asm, BLOCK, x=0.021)
    rep = sw_assembly_full.replace_component(asm, c2, PIN, reattach_mates=False)
    dele = sw_assembly_full.delete_component(asm, c1)
    comps = [c.Name2 for c in sw_assembly_full.component_list(asm)]
    return {"replace": bool(rep), "delete": dele, "components": comps}


SCENARIOS = {
    "setup_parts": s_setup_parts,
    "mates_coincident_distance": s_mates_coincident_distance,
    "mates_parallel_distance": s_mates_parallel_distance,
    "component_state": s_component_state,
    "patterns_components": s_patterns_components,
    "checks": s_checks,
    "assembly_cut": s_assembly_cut,
    "mate_reference": s_mate_reference,
    "virtual_part": s_virtual_part,
    "replace_delete": s_replace_delete,
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
