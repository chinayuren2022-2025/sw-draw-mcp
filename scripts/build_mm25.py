"""mm25-p1-1 零件最佳近似建模（依据图纸文字与视图，忽略颜色）。

近似几何：
  - 外轮廓：150 × 60 × 100 的长圆块（俯视图为 R30 两端圆弧）
  - 两个 Ø40 贯穿孔（Z 向）位于两端圆弧圆心 X=25/125、Y=0
  - 中央腰形盲腔：前、后各 20mm 深（宽50×高50，两侧内凹），中间保留实体
  - Ø35 贯穿孔（Y 向）位于中心 (X=75, Z=50)
  - R2 全圆角（全部边）

坐标：X=长度 150，Y=宽度 60，Z=高度 100；SW 内单位米。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_core
import sw_sel
import sw_sketch
import sw_features
import sw_advanced

OUT = r"\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT"

sw = sw_core.connect()
model = sw_core.new_part(sw)

# 1. 俯视图（Front Plane 即 XY）画长圆轮廓
sw_sketch.start_sketch(model, "front")
# 左侧半圆 圆心(25,0) r30，从下到上过 (-5,0)
sw_sketch.arc3pt(model, 0.025, -0.030, 0.025, 0.030, -0.005, 0.000)
# 上边
sw_sketch.line(model, 0.025, 0.030, 0.125, 0.030)
# 右侧半圆 圆心(125,0) r30，从上到下过 (155,0)
sw_sketch.arc3pt(model, 0.125, 0.030, 0.125, -0.030, 0.155, 0.000)
# 下边
sw_sketch.line(model, 0.125, -0.030, 0.025, -0.030)
sw_sketch.end_sketch(model)
base_sk = sw_sketch.last_sketch_feature(model).Name
base = sw_features.extrude_boss(model, sketch=base_sk, depth_m=0.100)
print("base:", base.Name)

# 2. Ø40 竖直贯穿孔
sw_sketch.start_sketch(model, "front")
sw_sketch.circle(model, 0.025, 0.000, 0.020)
sw_sketch.circle(model, 0.125, 0.000, 0.020)
sw_sketch.end_sketch(model)
h40_sk = sw_sketch.last_sketch_feature(model).Name
cut1 = sw_features.extrude_cut(model, sketch=h40_sk, depth_m=0.100, end_condition="blind")
print("40 holes:", cut1.Name)

# 3. 中央腰形凹槽：前、后各一个 20mm 深的盲腔（截面为向内凹的腰形，宽50x高50）
def _pocket_sketch(model, plane="front"):
    sw_sketch.start_sketch(model, plane)
    # 上边
    sw_sketch.line(model, 0.050, 0.025, 0.100, 0.025)
    # 右边：从上到下，中间向腔内凹（中点在 X=0.090）
    sw_sketch.arc3pt(model, 0.100, 0.025, 0.100, -0.025, 0.090, 0.0)
    # 下边
    sw_sketch.line(model, 0.100, -0.025, 0.050, -0.025)
    # 左边：从下到上，中间向腔内凹（中点在 X=0.060）
    sw_sketch.arc3pt(model, 0.050, -0.025, 0.050, 0.025, 0.060, 0.0)
    sw_sketch.end_sketch(model)
    return sw_sketch.last_sketch_feature(model).Name

front_pocket_sk = _pocket_sketch(model, "front")
cut2 = sw_features.extrude_cut(model, sketch=front_pocket_sk,
                               depth_m=0.020, end_condition="blind")
print("front pocket:", cut2.Name)

# 后腔：用镜像把前腔复制到后端（中间平面 Z=50）
try:
    mid_plane = sw_advanced.insert_ref_plane(model, plane_type="offset",
                                             base_spec="front", distance_mm=50)
    mid_plane_name = mid_plane[1] if isinstance(mid_plane, tuple) else mid_plane
    print("mid plane:", mid_plane_name)
    mirror_feat = sw_features.mirror_feature(model, seed_features=[cut2.Name],
                                             plane_name=mid_plane_name)
    print("mirror pocket:", mirror_feat.Name)
    cut2b = mirror_feat
except Exception as exc:
    print("mirror pocket failed:", exc)
    cut2b = None

# 4. Ø35 贯穿孔（Y 向）：用侧平面上的简单孔
cut3 = sw_features.simple_hole(model, {"kind": "plane", "normal": [0, 1, 0]},
                               diameter_m=0.035, depth_m=0.060,
                               position_mm=(75, 50))
print("35 hole:", cut3.Name)

# 5. R2 圆角（全部边；失败不致命）
try:
    sw_core.clear_selection(model)
    first = True
    for e in sw_sel._edges(model):
        sw_sel._select_entity(model, e, not first, 0)
        first = False
    f = sw_features.fillet(model, 0.002, edge_specs=None)
    print("fillet:", f.Name)
except Exception as exc:
    print("fillet skipped:", exc)

saved = sw_core.save_as(model, OUT, sw=sw)
print("saved:", saved)
print(json_dumps := __import__("json").dumps({"saved": saved, "features": [
    base.Name, cut1.Name, cut2.Name, cut2b.Name, cut3.Name]}, ensure_ascii=False, indent=2))
