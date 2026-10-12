"""sw_asm_ref / sw_topo 实机集成测试（需要运行中的 SW2018）。

用法: python scripts/tests/integration_asm_ref.py [输出目录]
构建 带孔方块 + 销，零件中命名面，装配中按"组件+面名"配合并闭环校验。
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import sw_assembly  # noqa: E402
import sw_asm_ref as ar  # noqa: E402
import sw_core as c  # noqa: E402
import sw_topo  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sw_asm_ref_")
os.makedirs(OUT, exist_ok=True)
sw = c.connect()
failures = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def build(name, draw, depth, names):
    model = c.new_part(sw)
    c.select_by_id(model, "前视基准面", "PLANE") or c.select_by_id(model, "Front Plane", "PLANE")
    sm = model.SketchManager
    sm.AddToDB = True
    sm.InsertSketch(True)
    draw(sm)
    sm.AddToDB = False
    sm.InsertSketch(True)
    model.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth, 0, False, False,
                                           False, False, 0, 0, False, False, False, False,
                                           True, True, True, 0, 0, False)
    for label, spec in names.items():
        ent, _ = sw_topo.resolve(model, {"spec": spec})
        sw_topo.name_entity(model, ent, label)
    path = os.path.join(OUT, name + ".SLDPRT")
    c.save_as(model, path, sw)
    topo = sw_topo.topology(model)
    sw.CloseDoc(model.GetTitle())
    return path, topo


block, btopo = build(
    "it_block",
    lambda sm: (sm.CreateCenterRectangle(0, 0, 0, 0.02, 0.02, 0),
                sm.CreateCircleByRadius(0, 0, 0, 0.005)),
    0.01, {"HOLE": {"kind": "cylinder", "radius_mm": 5},
           "TOP": {"kind": "plane", "normal": [0, 0, 1], "directional": True,
                   "root_mm": [0, 0, 10]}})
pin, _ = build("it_pin", lambda sm: sm.CreateCircleByRadius(0, 0, 0, 0.005), 0.03,
               {"PIN_CYL": {"kind": "cylinder", "radius_mm": 5},
                "PIN_END": {"kind": "plane", "normal": [0, 0, -1], "directional": True}})
named = sorted(f.get("name") for f in btopo["faces"] if f.get("name"))
check(named == ["HOLE", "TOP"], f"零件面命名并在拓扑中可见 {named}")
check(all(f.get("persist_id") for f in btopo["faces"]), "每个面都有持久 ID")

asm = c._early(sw_assembly.new_assembly(sw), "IModelDoc2")
ib = ar.insert_component(asm, block, fix=True)
ip = ar.insert_component(asm, pin, at_mm=(50, 30, 20), place="origin")
check(ip["origin_mm"] == [50.0, 30.0, 20.0], f"place=origin 原点精确落位 {ip['origin_mm']}")
check(ib.get("fixed") is True, "第一个组件固定")

r1 = ar.mate(asm, {"component": "it_block", "face": "HOLE"},
             {"component": "it_pin", "face": "PIN_CYL"}, "concentric")
check(r1["ok"], f"同心配合 ok: {r1.get('mate')} {r1.get('error', '')}")
dofs1 = r1["components"][1]["remaining_dofs"]
print("  同心后剩余自由度:", json.dumps(dofs1, ensure_ascii=False))

r2 = ar.mate(asm, {"component": "it_block", "face": "TOP"},
             {"component": "it_pin", "face": "PIN_END"}, "distance", distance_mm=5)
check(r2["ok"], f"距离配合 ok: {r2.get('mate')} {r2.get('error', '')}")
pin_info = r2["components"][1]
print("  距离后:", json.dumps(pin_info, ensure_ascii=False))
check(pin_info["status"] == "under_constrained", "销仍欠定义（可绕轴转）")
dofs2 = pin_info["remaining_dofs"]
check(dofs2 is not None and dofs2["count"] < dofs1["count"], "配合后剩余自由度减少")

# 坐标换算校验：销端面中心在装配坐标里应在方块顶面上方 5mm 处（或下方，取决于距离方向）
faces = ar.comp_faces(asm, "it_pin", kind="plane")
end = [f for f in faces["faces"] if f.get("name") == "PIN_END"][0]
top = [f for f in ar.comp_faces(asm, "it_block", kind="plane")["faces"]
       if f.get("name") == "TOP"][0]
gap = abs(end["box_mm"][2] - top["box_mm"][2])
check(abs(gap - 5) < 1e-3, f"装配坐标换算正确：端面与顶面间距 {gap:.4f} mm")

md = ar.mates(asm)
types = sorted(x.get("type") for x in md)
check(types == ["concentric", "distance"], f"配合读回类型 {types}")
dist = [x for x in md if x.get("type") == "distance"][0]
check(abs(dist.get("value", 0) - 5) < 1e-6, f"距离配合数值读回 {dist.get('value')}")
check(sorted(e["component"] for e in dist["entities"]) == ["it_block-1", "it_pin-1"],
      f"配合两端组件 {dist['entities']}")

d2 = ar.edit_mate(asm, dist["name"], distance_mm=8)
check(abs(d2.get("value", 0) - 8) < 1e-6, f"edit_mate 改距离 -> {d2.get('value')}")

# 冲突配合：再加一个与距离配合矛盾的重合，应报错并回滚
r3 = ar.mate(asm, {"component": "it_block", "face": "TOP"},
             {"component": "it_pin", "face": "PIN_END"}, "coincident")
print("  冲突配合:", json.dumps({k: r3.get(k) for k in ("ok", "error", "rolled_back")},
                              ensure_ascii=False))
check(not r3["ok"], "冲突配合被识别为失败")
check(len(ar.mates(asm)) == 2, "冲突配合已回滚，配合数仍为 2")

rep = ar.check(asm)
check(rep["mate_errors"] == [], "检查：无配合错误")
check(rep["floating"] == ["it_pin-1"], f"检查：欠定义组件 {rep['floating']}")
check(rep.get("interference") == [], f"检查：无干涉 {rep.get('interference')}")

# 基准面配合：把销的右视基准面与方块右视基准面重合 -> 锁住旋转
r4 = ar.mate(asm, {"component": "it_block", "plane": "right"},
             {"component": "it_pin", "plane": "right"}, "coincident")
check(r4["ok"], f"组件基准面配合 ok {r4.get('error', '')}")
check(r4["components"][1]["status"] == "fully_constrained",
      f"销完全定义 {r4['components'][1]['status']}")

c.save_as(asm, os.path.join(OUT, "it_asm.SLDASM"), sw)
sw.CloseDoc(asm.GetTitle())
for p in (block, pin):
    c.close_doc_by_path(sw, p)
print(f"\n{len(failures)} failures; output in {OUT}")
sys.exit(1 if failures else 0)
