"""derive_assembly.py — 装配 spec 自动推导 + 构建 + 验证（功能二加强层）

LLM 只给意图：谁装进谁（两个零件路径 + 保存路径）。其余全部确定性执行：
  1. 读取两零件几何（圆柱面/平面，零件局部空间，视角无关）
  2. 间隙配对：找 0.0005mm < r_载体 - r_被插件 < 0.5mm 且轴平行的圆柱面对 → concentric
  3. 座面识别：载体上"沉孔底"平面（⊥轴、位于孔轴向内端、不是端面）→ distance d=0
  4. 被插件配合面：位于轴向端部的 ⊥轴平面（多个取面积大者）
  5. 朝向判定（确定性，不用 closest 猜）：主体必须伸向开口侧，否则 concentric align=anti
  6. 生成 spec → 调 build_assembly 构建 → 用最终位置验证（贴合 + 主体在座面→开口侧）

CLI：
  python derive_assembly.py --intent '{"action":"insert","insert":"lens.SLDPRT","into":"barrel.SLDPRT","save":"asm.SLDASM"}'
  python derive_assembly.py --insert lens.SLDPRT --into barrel.SLDPRT --save asm.SLDASM
  python derive_assembly.py ... --spec-only        # 只推导输出 spec，不构建
  python derive_assembly.py ... --dir <目录>       # 相对文件名的解析目录（默认 ../output）

假设（v1）：两零件轴向平行（本工具链生成的回转体零件均满足）；装入方向由座面几何唯一确定。
教训（2026-07-27）：配合"求解成功"≠几何正确——曾把透镜装到通孔侧造成干涉，
必须做主体侧向验证（本脚本 verify_positions）。
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pythoncom
from win32com.client import VARIANT

import build_assembly
import sw_core
import sw_sketch_check


class DeriveError(Exception):
    pass


def _save_inplace(sw, model):
    """原路径保存（fix 草图后落盘）。"""
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    sw_core._dyn(model).Save3(1, errs, warns)  # 1 = swSaveAsOptions_Silent


def sketch_gate(sw, model, policy):
    """装配前置约束检查。policy: warn(报告但继续) / fix(自动补全并保存) / strict(不良则中止)。"""
    if policy == "fix":
        dyn_sw = sw_core._dyn(sw)
        errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        dyn_sw.ActivateDoc2(sw_core.com_get(model, "GetTitle"), False, errs)
        sw_sketch_check.fix_part(model)
        _save_inplace(sw, model)
    rep = sw_sketch_check.check_part(model)
    if policy == "strict" and (rep["under_defined"] or rep["over_defined"] or rep["no_solution"]):
        raise DeriveError(
            f"零件「{rep['title']}」草图未完全定义：{rep['summary']}。"
            "可用 --sketch-policy fix 自动补全后重试")
    return rep


# ---------- 几何读取 ----------

def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return [x / n for x in v] if n > 1e-12 else list(v)


def _open_part(sw, path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise DeriveError(f"零件不存在: {path}")
    # 已打开则复用
    doc = sw.GetFirstDocument()
    while doc is not None:
        d = sw_core._early(doc, "IModelDoc2")
        pn = sw_core.com_get(d, "GetPathName")
        if pn and os.path.abspath(str(pn)).lower() == path.lower():
            return d
        doc = d.GetNext()
    dyn_sw = sw_core._dyn(sw)
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = dyn_sw.OpenDoc6(path, 1, 0, "", errs, warns)  # 1 = swDocPART
    if model is None:
        raise DeriveError(f"无法打开零件: {path} (err={errs.value})")
    return sw_core._early(model, "IModelDoc2")


def _classify_faces(model):
    """读取零件全部实体面 → {"cylinders": [...], "planes": [...]}（毫米，零件局部空间）"""
    part = sw_core._early(model, "IPartDoc")
    bodies = part.GetBodies2(0, False) or []  # 0 = swSolidBody
    cylinders, planes = [], []
    for b in bodies:
        b = sw_core._early(b, "IBody2")
        for f in (b.GetFaces() or []):
            face = sw_core._early(f, "IFace2")
            surf = sw_core._early(face.GetSurface(), "ISurface")
            if surf.IsCylinder():
                p = surf.CylinderParams  # [root xyz, axis xyz, radius]
                axis = _unit([float(v) for v in p[3:6]])
                rng = None
                try:
                    box = face.GetBox()  # [x0,y0,z0,x1,y1,z1] 米
                    corners = [[box[i] * 1000.0, box[j] * 1000.0, box[k] * 1000.0]
                               for i in (0, 3) for j in (1, 4) for k in (2, 5)]
                    ts = [_dot(c, axis) for c in corners]
                    rng = (min(ts), max(ts))
                except Exception:
                    pass
                cylinders.append({"r_mm": float(p[6]) * 1000.0, "axis": axis,
                                  "root_mm": [float(v) * 1000.0 for v in p[0:3]],
                                  "t_range": rng})
            elif surf.IsPlane():
                p = surf.PlaneParams  # SW2018 实测: [法向 xyz, 根点 xyz]
                n = _unit([float(v) for v in p[0:3]])
                area = 0.0
                try:
                    area = float(face.GetArea()) * 1e6
                except Exception:
                    pass
                planes.append({"normal": n,
                               "root_mm": [float(v) * 1000.0 for v in p[3:6]],
                               "area_mm2": area})
    return {"cylinders": cylinders, "planes": planes}


# ---------- spec 推导 ----------

def derive_insert_spec(carrier, insert, save_path):
    """carrier/insert = {"path", "cylinders", "planes"}。返回 (spec, 推导信息dict)。"""
    # 1) 间隙圆柱配对
    best = None
    for cc in carrier["cylinders"]:
        for ci in insert["cylinders"]:
            if abs(_dot(cc["axis"], ci["axis"])) < 0.999:
                continue
            clr = cc["r_mm"] - ci["r_mm"]
            if 0.0005 < clr < 0.5 and (best is None or clr < best[0]):
                best = (clr, cc, ci)
    if best is None:
        raise DeriveError(
            "找不到间隙配合的圆柱面对（载体孔径需比被插件外径大 0.0005~0.5mm）。"
            f"载体圆柱面半径: {[round(c['r_mm'], 3) for c in carrier['cylinders']]}；"
            f"被插件圆柱面半径: {[round(c['r_mm'], 3) for c in insert['cylinders']]}")
    clearance, hole, boss = best

    # 2) 轴定向：+axis = 座面 → 开口
    axis = hole["axis"]
    if hole["t_range"] is None:
        raise DeriveError("无法确定孔的轴向范围（GetBox 失败）")
    b_lo, b_hi = hole["t_range"]
    ts = [_dot(p["root_mm"], axis) for p in carrier["planes"]]
    if not ts:
        raise DeriveError("载体没有任何平面，无法识别座面")
    t_lo, t_hi = min(ts), max(ts)
    seats = [p for p, t in zip(carrier["planes"], ts)
             if t_lo + 0.05 < t < t_hi - 0.05
             and min(abs(t - b_lo), abs(t - b_hi)) < 0.05]
    if len(seats) != 1:
        raise DeriveError(
            f"座面识别不唯一（{len(seats)} 个候选），该零件形状超出自动推导范围，"
            "请改用显式 spec（见 output/asm_spec.json 模板）")
    seat = seats[0]
    t_seat0 = _dot(seat["root_mm"], axis)
    t_open0 = b_hi if abs(t_seat0 - b_lo) < 0.05 else b_lo
    if t_open0 < t_seat0:
        axis = [-v for v in axis]  # 翻转，使 +axis 指向开口
    t_seat = _dot(seat["root_mm"], axis)
    t_open = t_open0 if axis == hole["axis"] else -t_open0
    pocket_depth = t_open - t_seat

    # 3) 被插件配合面：⊥轴的端面（在轴向极值 0.05mm 内），多个取面积大者
    u = boss["axis"]  # 被插件轴向（局部空间，符号任意）
    i_ts = [_dot(p["root_mm"], u) for p in insert["planes"]]
    for c in insert["cylinders"]:
        if c["t_range"]:
            i_ts += list(c["t_range"])
    if not i_ts:
        raise DeriveError("被插件没有任何平面/圆柱面，无法确定入座面")
    i_lo, i_hi = min(i_ts), max(i_ts)
    end_planes = [p for p in insert["planes"]
                  if min(abs(_dot(p["root_mm"], u) - i_lo),
                         abs(_dot(p["root_mm"], u) - i_hi)) < 0.05]
    if not end_planes:
        raise DeriveError("被插件没有位于轴向端部的平面，无法自动确定入座面；请用显式 spec")
    # 配合端面优先取"紧贴配合圆柱段轴向端部"的端面——阶梯轴类零件的正确入座面
    # 是小段端面而非面积最大的大端面；无 t_range 时退化为面积最大者。
    if boss.get("t_range"):
        b_lo2, b_hi2 = boss["t_range"]
        lead = min(end_planes,
                   key=lambda p: (min(abs(_dot(p["root_mm"], u) - b_lo2),
                                      abs(_dot(p["root_mm"], u) - b_hi2)),
                                  -p["area_mm2"]))
    else:
        lead = max(end_planes, key=lambda p: p["area_mm2"])
    t_lead_u = _dot(lead["root_mm"], u)
    body_dir = 1.0 if (i_lo + i_hi) / 2.0 > t_lead_u else -1.0  # 主体在配合面的哪一侧（u 向）

    # 4) 朝向判定（确定性）：装配后被插件主体必须从座面伸向开口（+axis）
    #    恒等插入时 u→装配体的映射符号 s0 = dot(u, axis)；主体映射方向 = s0*body_dir
    #    若 ≠ +1 需翻转 180°（concentric align=anti），否则 aligned。不用 closest 猜。
    s0 = _dot(u, axis)
    flip = (s0 * body_dir) < 0
    con_align = "anti" if flip else "aligned"

    if _dot(seat["normal"], axis) < 0:
        # 座面外法向背向空腔，非常规；不影响 distance 求解，仅提示
        seat_note = "座面法向背向空腔（非常规，已按原样使用）"
    else:
        seat_note = None

    # 5) 组装 spec（被插件初始放到开口外侧 25mm，引导解算方向）
    at = [round(v * (t_open + 25.0) / 1000.0, 6) for v in axis]
    spec = {
        "components": [
            {"path": carrier["path"], "at": [0, 0, 0]},
            {"path": insert["path"], "at": at},
        ],
        "mates": [
            {"type": "concentric", "align": con_align,
             "comp1": 0, "face1": {"kind": "cylinder", "radius_mm": round(hole["r_mm"], 4)},
             "comp2": 1, "face2": {"kind": "cylinder", "radius_mm": round(boss["r_mm"], 4)}},
            {"type": "distance", "align": "closest", "distance_m": 0.0,
             "comp1": 0, "face1": {"kind": "plane", "normal": [round(v, 4) for v in seat["normal"]],
                                   "root_mm": [round(v, 3) for v in seat["root_mm"]]},
             "comp2": 1, "face2": {"kind": "plane", "normal": [round(v, 4) for v in lead["normal"]],
                                   "root_mm": [round(v, 3) for v in lead["root_mm"]]}},
        ],
        "save": save_path,
    }
    info = {"axis": [round(v, 4) for v in axis], "clearance_mm": round(clearance, 4),
            "hole_r_mm": round(hole["r_mm"], 4), "boss_r_mm": round(boss["r_mm"], 4),
            "seat_t_mm": round(t_seat, 3), "pocket_depth_mm": round(pocket_depth, 3),
            "lead_t_mm": round(t_lead_u, 3),
            "insert_t_range_mm": [round(i_lo, 3), round(i_hi, 3)],
            "flip": flip, "concentric_align": con_align,
            "seat_note": seat_note}
    return spec, info


# ---------- 构建后验证 ----------

def verify_positions(report, info):
    """用最终位置验证：两配合面贴合（<0.05mm）且被插件主体在座面→开口侧。"""
    pos = report.get("component_positions_mm") or []
    if len(pos) < 2 or pos[0] is None or pos[1] is None:
        return False, "位置信息缺失"
    axis = info["axis"]
    s = -1.0 if info.get("flip") else 1.0  # 翻转后被插件局部轴向坐标变号
    lead_t = s * info["lead_t_mm"]
    lo, hi = info["insert_t_range_mm"]
    i_lo, i_hi = (s * hi, s * lo) if s < 0 else (lo, hi)
    t_c, t_i = _dot(pos[0], axis), _dot(pos[1], axis)
    seat_asm = t_c + info["seat_t_mm"]
    lead_asm = t_i + lead_t
    gap = abs(seat_asm - lead_asm)
    if gap >= 0.05:
        return False, f"配合面未贴合（间隙 {gap:.3f}mm）"
    near_end = t_i + i_lo  # 被插件最靠 -axis 端
    if near_end < seat_asm - 0.05:
        return False, f"被插件主体越过座面进入非空腔侧（疑似装反/干涉，越过 {seat_asm - near_end:.2f}mm）"
    return True, f"贴合良好（间隙 {gap:.4f}mm），被插件位于空腔侧"


# ---------- 主流程 ----------

def _resolve(name, base_dir):
    if os.path.isabs(name) and os.path.exists(name):
        return name
    cand = os.path.join(base_dir, name)
    if os.path.exists(cand):
        return cand
    # 后缀补全
    for ext in (".SLDPRT", ".sldprt", ".SLDASM", ".sldasm"):
        if os.path.exists(cand + ext):
            return cand + ext
    raise DeriveError(f"找不到文件: {name}（目录 {base_dir}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--intent", help='意图 JSON：{"action":"insert","insert":..,"into":..,"save":..}')
    ap.add_argument("--insert", help="被插件路径/文件名")
    ap.add_argument("--into", help="载体路径/文件名")
    ap.add_argument("--save", help="装配体保存路径")
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "output"),
                    help="相对文件名解析目录（默认 output/）")
    ap.add_argument("--spec-only", action="store_true", help="只推导输出 spec JSON，不构建")
    ap.add_argument("--sketch-policy", choices=["warn", "fix", "strict"], default="warn",
                    help="装配前置草图约束检查：warn=报告但继续(默认) fix=自动补全并保存 strict=不良则中止")
    args = ap.parse_args()

    try:
        if args.intent:
            intent = json.loads(args.intent)
            if intent.get("action", "insert") != "insert":
                raise DeriveError(f"不支持的 action: {intent.get('action')}（v1 仅支持 insert）")
            ins, into, save = intent["insert"], intent["into"], intent.get("save")
        else:
            if not (args.insert and args.into):
                raise DeriveError("需要 --intent 或 --insert + --into")
            ins, into, save = args.insert, args.into, args.save
        ins = _resolve(ins, args.dir)
        into = _resolve(into, args.dir)
        if not save:
            save = os.path.join(args.dir,
                                os.path.splitext(os.path.basename(into))[0] + "_asm.SLDASM")
        elif not os.path.isabs(save):
            save = os.path.join(args.dir, save)

        sw = sw_core.connect()
        carrier_m = _open_part(sw, into)
        insert_m = _open_part(sw, ins)

        # 装配前置：草图约束检查（功能一集成）
        sketch_reports = {"carrier": sketch_gate(sw, carrier_m, args.sketch_policy),
                          "insert": sketch_gate(sw, insert_m, args.sketch_policy)}

        carrier = {"path": into, **_classify_faces(carrier_m)}
        insert = {"path": ins, **_classify_faces(insert_m)}

        spec, info = derive_insert_spec(carrier, insert, save)
        print("== 推导结果 ==")
        print(json.dumps({"spec": spec, "info": info,
                          "sketch_check": {k: v["summary"] for k, v in sketch_reports.items()}},
                         ensure_ascii=False, indent=2))
        if args.spec_only:
            return

        print("== 构建 ==")
        report = build_assembly.run(spec)
        ok, msg = verify_positions(report, info)
        print("== 验证 ==")
        print(json.dumps({"verified": ok, "message": msg,
                          "saved": report.get("saved")}, ensure_ascii=False, indent=2))
        if not ok:
            sys.exit(2)
    except DeriveError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
