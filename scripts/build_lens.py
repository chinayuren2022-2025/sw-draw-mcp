"""build_lens.py — 第3层特征级工具：create_lens(params) + CLI 入口

一个 create_lens 内部编排 8-12 个 SW API 调用；每步打印检查点，
任何一步失败抛出带上下文的异常，供 harness 循环（LLM 分析→修正→重执行）使用。

用法（CLI）：
    python build_lens.py --nl "做一个Φ25、f=50的平凸透镜，BK7" --out out.SLDPRT
    python build_lens.py --params '{"type":"plano_convex","D":25,"f":50,"material":"BK7"}' --out out.SLDPRT
    python build_lens.py --params ... --dry-run   # 只推导参数，不连 SW
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import optics

# sw_core / sw_part 依赖 pywin32，仅在真正建模时导入（--dry-run 无需 COM）


def create_lens(sw, model, p, do_chamfer=True):
    """特征级抽象：平凸透镜。单位：params 里 mm，此处换算为米。

    几何：在前视基准面绘制绕 Y 轴旋转的截面——
        A(0,0) → B(r,0) → C(r, t_c-sag) →(球面弧, 圆心 O(0, t_c-R))→ D(0,t_c) → A
    """
    import sw_core
    import sw_part
    r = sw_core.mm(p["D"] / 2.0)
    t_c = sw_core.mm(p["t_c"])
    sag = sw_core.mm(p["sag"])
    R = sw_core.mm(p["R"])
    y_cyl = t_c - sag  # 圆柱段高度

    # 圆弧必须严格经过 C(r, y_cyl) 与 D(0, t_c) 两点：SW2018 CreateArc 对
    # “端点是否在圆上”的容差极严（实测 0.34µm 偏差即静默不建弧）。
    # 名义 R 由 sag 取 3 位小数而来，直接用 R 会导致 C 点偏差 ~0.34µm。
    # 因此在 Y 轴上重新求精确圆心/半径（两点共圆：cy=(t_c²-y_cyl²-r²)/(2(t_c-y_cyl))）。
    arc_cy = (t_c * t_c - y_cyl * y_cyl - r * r) / (2.0 * (t_c - y_cyl))
    R_arc = t_c - arc_cy

    steps = []

    # 1. 草图：前视基准面
    sw_part.start_sketch(model, "front")
    steps.append("sketch@front")

    # 2. 旋转轴（中心线，Y 轴，略超出轮廓避免端点重合）
    sw_part.centerline(model, 0, -t_c * 0.2, 0, t_c * 1.2)
    steps.append("centerline@Y")

    # 3. 截面轮廓（四条图元，闭合）
    sw_part.line(model, 0, 0, r, 0)                       # A→B 平面侧
    sw_part.line(model, r, 0, r, y_cyl)                   # B→C 圆柱边
    sw_part.arc(model, 0, arc_cy, r, y_cyl, 0, t_c, 1)    # C→D 球面弧（逆时针，精确过两端点）
    sw_part.line(model, 0, t_c, 0, 0)                     # D→A 沿轴闭合
    steps.append("profile closed (4 entities)")
    sw_part.end_sketch(model)

    # 4. 旋转 360° 成实体
    feat = sw_part.revolve_boss(model)
    steps.append(f"revolve: {feat.Name}")
    model.ClearSelection2(True)

    # 5. 倒角（平面侧圆柱边；坐标拾取与视角相关，沿圆周 4 个候选点重试）——失败不致命
    if do_chamfer:
        try:
            model.ViewZoomtofit2()
            picked = any(sw_core.select_edge_near(model, *pt)
                         for pt in [(r, 0, 0), (-r, 0, 0), (0, 0, r), (0, 0, -r)])
            if picked:
                feat_c = sw_part.chamfer_selected(model, sw_core.mm(p["chamfer"]))
                name = feat_c.Name if feat_c else "n/a"
                steps.append(f"chamfer C{p['chamfer']}: {name}")
            else:
                steps.append("chamfer SKIPPED（边线选择失败，可手动补倒角）")
        except Exception as exc:
            steps.append(f"chamfer SKIPPED ({exc})")

    # 6. 检查：体积 / 质量
    mp = sw_core.mass_properties(model)
    steps.append(f"inspect: V={mp['volume_m3'] * 1e9:.2f} mm3")

    return steps, mp


def run(intent, out_path, dry_run=False, do_chamfer=True):
    """完整流水线：参数推导 → 打印约束信息 → （可选）建模 → 校验 → 保存。"""
    params, msgs = optics.derive_plano_convex(
        intent["D"], intent["f"], intent["material"], intent.get("tolerance", "standard"))

    report = {"intent": intent, "params": params, "messages":
              [{"level": lv, "text": tx} for lv, tx in msgs]}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if dry_run:
        return report

    import sw_core

    sw = sw_core.connect()
    model = sw_core.new_part(sw)
    steps, mp = create_lens(sw, model, params, do_chamfer=do_chamfer)

    # 理论体积交叉校验（圆柱 + 球冠缺口的解析式）
    r = params["D"] / 2.0
    sag = params["sag"]
    R = params["R"]
    v_cyl = math.pi * r * r * params["t_c"]
    v_cap = math.pi * sag * sag * (R - sag / 3.0)  # 球冠体积
    v_theory = v_cyl - (math.pi * r * r * sag - v_cap)  # 圆柱 - (圆柱顶被球面挖去的部分)
    v_sw = mp["volume_m3"] * 1e9
    dev = abs(v_sw - v_theory) / v_theory * 100 if v_theory else float("nan")

    mass_g = v_sw * 1e-3 * params["density_g_cm3"]  # mm3 → cm3 → g
    report.update({
        "steps": steps,
        "volume_mm3_sw": round(v_sw, 3),
        "volume_mm3_theory": round(v_theory, 3),
        "volume_deviation_pct": round(dev, 3),
        "mass_g_est": round(mass_g, 2),
        "saved": sw_core.save_as(model, out_path, sw=sw),
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--nl", help="自然语言描述（兜底正则提取）")
    src.add_argument("--params", help="LLM 提取后的 JSON 意图")
    ap.add_argument("--out", default="lens.SLDPRT")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-chamfer", action="store_true")
    args = ap.parse_args()

    if args.nl:
        intent = optics.nl_extract(args.nl)
        if intent is None:
            print(json.dumps({"error": "NL 兜底提取失败，该句式需 LLM 提取意图"},
                             ensure_ascii=False))
            sys.exit(2)
    else:
        intent = json.loads(args.params)

    try:
        run(intent, args.out, dry_run=args.dry_run, do_chamfer=not args.no_chamfer)
    except optics.ConstraintError as exc:
        print(json.dumps({"error": f"约束冲突: {exc}"}, ensure_ascii=False))
        sys.exit(3)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
