"""v2 MCP 工具冒烟测试：直接调用 mcp_server 中的工具函数（需要运行中的 SW2018）。

用法: python scripts/tests/integration_mcp_v2.py <integration_asm_ref.py 的输出目录>
依赖 integration_asm_ref.py 先生成 it_block / it_pin / it_asm。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import mcp_server as s  # noqa: E402

D = sys.argv[1]
BLOCK = os.path.join(D, "it_block.SLDPRT")
ASM = os.path.join(D, "it_asm.SLDASM")
failures = []


def ok(name, res, cond=None):
    bad = isinstance(res, dict) and "error" in res and cond is None
    passed = (not bad) and (cond(res) if cond else True)
    short = json.dumps(res, ensure_ascii=False, default=str)[:220] if not isinstance(res, list) else str(res[0])
    print(("PASS " if passed else "FAIL ") + f"{name}: {short}")
    if not passed:
        failures.append(name)
    return res


ok("doc_open part", s.doc_open(BLOCK))
topo = ok("part_topology", s.part_topology(BLOCK), lambda r: r["face_total"] >= 7)
bottom = [f for f in topo["faces"] if f.get("kind") == "plane" and f["normal"][2] < -0.99][0]
ok("entity_name by persist_id", s.entity_name({"persist_id": bottom["persist_id"]}, "BOTTOM",
                                              BLOCK, save=False))
cyl = [f for f in topo["faces"] if f.get("kind") == "cylinder"][0]
ok("entity_name rejects renaming a named face",
   s.entity_name({"persist_id": cyl["persist_id"]}, "HOLE2", BLOCK, save=False),
   lambda r: "已命名为 'HOLE'" in r.get("error", ""))
ok("measure hole radius", s.measure({"name": "HOLE"}, file=BLOCK),
   lambda r: abs(r.get("radius_mm", 0) - 5) < 1e-6)
ok("measure top-bottom distance",
   s.measure({"name": "TOP"}, {"spec": {"kind": "plane", "normal": [0, 0, -1],
                                        "directional": True}}, BLOCK),
   lambda r: abs(r.get("distance_mm", 0) - 10) < 1e-6)
ok("mass_properties", s.mass_properties(BLOCK),
   lambda r: abs(r["volume_mm3"] - (40 * 40 * 10 - 3.14159265 * 25 * 10)) < 1)
feats = ok("feature_list", s.feature_list(BLOCK), lambda r: len(r["features"]) > 0)
dims = ok("dimension_list", s.dimension_list(BLOCK), lambda r: len(r["dimensions"]) >= 1)
ext = [d for d in dims["dimensions"] if abs(d["value"] - 10) < 1e-6]
if ext:
    ok("dimension_set 10->12", s.dimension_set(ext[0]["name"], 12, BLOCK),
       lambda r: abs(r["new"] - 12) < 1e-6)
    ok("mass after dimension_set", s.mass_properties(BLOCK),
       lambda r: abs(r["bbox_mm"][5] - r["bbox_mm"][2] - 12) < 1e-3)
    ok("undo", s.undo(1, BLOCK))
boss = [f["name"] for f in feats["features"] if "Extrude" in f["type"] or "Boss" in f["type"]]
if boss:
    ok("feature_suppress", s.feature_suppress(boss[0], True, BLOCK), lambda r: r["suppressed"])
    ok("feature_unsuppress", s.feature_suppress(boss[0], False, BLOCK),
       lambda r: not r["suppressed"])
ok("custom_properties set", s.custom_properties(BLOCK, {"材料": "6061", "Designer": "AI"}),
   lambda r: r["properties"].get("Designer") == "AI")
ok("doc_export step", s.doc_export(os.path.join(D, "it_block.step"), BLOCK),
   lambda r: r["bytes"] > 1000)
img = s.view_capture(BLOCK, "isometric", 640, 480, os.path.join(D, "it_block_iso.png"))
ok("view_capture", img, lambda r: isinstance(r, list) and len(r) == 2)
ok("doc_close part (discard)", s.doc_close(BLOCK, save=False))

ok("doc_open asm", s.doc_open(ASM))
comps = ok("asm_components", s.asm_components(ASM),
           lambda r: {c["name"] for c in r["components"]} == {"it_block-1", "it_pin-1"})
ok("asm_component_faces", s.asm_component_faces("it_pin", ASM, kind="cylinder"),
   lambda r: r["faces"] and r["faces"][0].get("name") == "PIN_CYL")
ok("asm measure (assembly refs)",
   s.measure({"component": "it_block", "face": "TOP"},
             {"component": "it_pin", "face": "PIN_END"}, ASM),
   lambda r: abs(r.get("normal_distance_mm", 0) - 8) < 1e-6)
mates = ok("asm_mates", s.asm_mates(ASM), lambda r: len(r["mates"]) == 3)
ok("asm_check", s.asm_check(ASM), lambda r: r["ok"] and r["floating"] == [])
ok("view_capture asm", s.view_capture(ASM, "front", 640, 480,
                                      os.path.join(D, "it_asm_front.png")),
   lambda r: isinstance(r, list))
ok("doc_list", s.doc_list(), lambda r: len(r["documents"]) >= 1)
ok("doc_close asm", s.doc_close(ASM, save=False))

print(f"\n{len(failures)} failures: {failures}")
sys.exit(1 if failures else 0)
