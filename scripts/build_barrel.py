"""build_barrel.py — 确定性镜筒生成器（带透镜座，复用 revolve 机制）

几何（mm，绕 Y 轴旋转，y ∈ [0, length]，开口在 y=0）：
  外圆 r_out；透镜座沉孔 r_bore 深 seat_depth（自 y=0 起）；通孔 r_hole。

CLI:
  python build_barrel.py --params '{"outer_d":27,"bore_d":25.1,"seat_depth":3,
      "hole_d":23,"length":8}' --out barrel.SLDPRT
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def derive(p):
    r_out = p["outer_d"] / 2.0
    r_bore = p["bore_d"] / 2.0
    r_hole = p["hole_d"] / 2.0
    seat = float(p["seat_depth"])
    L = float(p["length"])
    if not (r_hole < r_bore < r_out):
        raise ValueError(f"半径关系需满足 hole<bore<out，当前 {r_hole}/{r_bore}/{r_out}")
    if not (0 < seat < L):
        raise ValueError("seat_depth 必须在 (0, length) 内")
    if r_out - r_bore < 0.5:
        raise ValueError("壁厚过薄 (<0.5mm)")
    return r_out, r_bore, r_hole, seat, L


def run(params, out_path):
    import sw_core
    import sw_part

    r_out, r_bore, r_hole, seat, L = derive(params)
    mm = sw_core.mm

    sw = sw_core.connect()
    model = sw_core.new_part(sw)

    def rect_sketch(x_max_m, y1_m, y2_m):
        """贴轴矩形草图（x∈[0,x_max], y∈[y1,y2]）+ 中心线。"""
        sw_part.start_sketch(model, "front")
        sw_part.centerline(model, 0, -0.0016, 0, mm(L * 1.2))
        pts = [(0.0, y1_m), (x_max_m, y1_m), (x_max_m, y2_m), (0.0, y2_m)]
        for i in range(4):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % 4]
            sw_part.line(model, x1, y1, x2, y2)
        sw_part.end_sketch(model)

    # 1. 实心圆柱
    rect_sketch(mm(r_out), 0.0, mm(L))
    f1 = sw_part.revolve_boss(model)
    # 2. 透镜座沉孔切除
    rect_sketch(mm(r_bore), 0.0, mm(seat))
    f2 = sw_part.revolve_boss(model, is_cut=True)
    # 3. 通孔切除
    rect_sketch(mm(r_hole), mm(seat), mm(L))
    f3 = sw_part.revolve_boss(model, is_cut=True)

    mp = sw_core.mass_properties(model)
    v_theory = math.pi * (r_out**2 * L - r_bore**2 * seat - r_hole**2 * (L - seat))
    v_sw = mp["volume_m3"] * 1e9
    saved = sw_core.save_as(model, out_path, sw=sw)
    report = {"params": params, "features": [f1.Name, f2.Name, f3.Name],
              "volume_mm3_sw": round(v_sw, 2),
              "volume_mm3_theory": round(v_theory, 2),
              "volume_deviation_pct": round(abs(v_sw - v_theory) / v_theory * 100, 4),
              "saved": saved}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    run(json.loads(args.params), args.out)


if __name__ == "__main__":
    main()
