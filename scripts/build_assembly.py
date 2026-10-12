"""build_assembly.py — 装配编排 CLI（v1 框架）

输入一份 JSON 装配规格，确定性地完成：插入零部件 → 反查配合实体 → 加配合 → 校验 → 保存。
LLM 的全部职责只是产出这份 JSON（每个零件路径 + 每个配合的几何描述），不参与任何执行。

spec 示例：
{
  "components": [
    {"path": "D:/.../barrel.SLDPRT", "at": [0, 0, 0]},
    {"path": "D:/.../lens.SLDPRT",   "at": [0.05, 0.05, 0.05]}
  ],
  "mates": [
    {"type": "concentric", "align": "closest",
     "comp1": 0, "face1": {"kind": "cylinder", "radius_mm": 12.55},
     "comp2": 1, "face2": {"kind": "cylinder", "radius_mm": 12.5}},
    {"type": "coincident", "align": "anti",
     "comp1": 0, "face1": {"kind": "plane", "normal": [0,-1,0], "select": "largest"},
     "comp2": 1, "face2": {"kind": "plane", "normal": [0,-1,0], "select": "largest"}}
  ],
  "save": "D:/.../lens_barrel.SLDASM"
}

CLI:
  python build_assembly.py --spec spec.json
  python build_assembly.py --spec-json '{...}'
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_assembly
import sw_core


def run(spec):
    sw = sw_core.connect()
    asm = sw_assembly.new_assembly(sw)
    steps = []

    comps = []
    for i, c in enumerate(spec["components"]):
        comp = sw_assembly.insert_component(asm, c["path"], tuple(c.get("at", (0, 0, 0))), sw=sw)
        comps.append(comp)
        steps.append(f"insert[{i}]: {os.path.basename(c['path'])} → {comp.Name2}")

    mate_reports = []
    for j, m in enumerate(spec.get("mates", [])):
        c1, c2 = comps[m["comp1"]], comps[m["comp2"]]
        f1, d1 = sw_assembly.find_face(c1, select=m["face1"].get("select", "first"), **{k: v for k, v in m["face1"].items() if k != "select"})
        f2, d2 = sw_assembly.find_face(c2, select=m["face2"].get("select", "first"), **{k: v for k, v in m["face2"].items() if k != "select"})
        if f1 is None or f2 is None:
            mate_reports.append({"mate": j, "type": m["type"], "ok": False,
                                 "error": f"实体未找到: face1={d1} face2={d2}"})
            continue
        mate, err = sw_assembly.add_mate(asm, f1, f2, m["type"],
                                         align=m.get("align", "closest"),
                                         distance_m=m.get("distance_m", 0.0),
                                         flip=m.get("flip", False))
        ok = (mate is not None) and err == 1  # swAddMateError_NoError = 1
        mate_reports.append({"mate": j, "type": m["type"], "ok": ok, "error_code": err,
                             "name": mate.Name if mate else None,
                             "face1": d1, "face2": d2})
        steps.append(f"mate[{j}] {m['type']}: {'OK' if ok else 'FAIL err=' + str(err)}")

    status = sw_assembly.check_mates(asm)
    saved = None
    if spec.get("save"):
        saved = sw_core.save_as(asm, spec["save"], sw=sw)

    # 零部件最终位置（验证配合是否把零件解算到位）
    positions = []
    for comp in comps:
        t = comp.Transform2
        arr = t.ArrayData if t is not None else None
        positions.append([round(v * 1000, 3) for v in arr[9:12]] if arr else None)

    report = {"steps": steps, "mates": mate_reports, "mate_status": status,
              "component_positions_mm": positions, "saved": saved}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--spec", help="装配规格 JSON 文件路径")
    g.add_argument("--spec-json", help="装配规格 JSON 字符串")
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8")) if args.spec else json.loads(args.spec_json)
    try:
        run(spec)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
