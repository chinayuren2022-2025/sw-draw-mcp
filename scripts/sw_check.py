"""sw_check.py — 零件级检查与校验层（补全清单 6.x）

在 sw_sketch_check 基础上补充：
  - 特征树清单 + 特征错误码 + 抑制状态
  - What's Wrong / 重建报告
  - 草图质量：开环、重复端点、极短图元、直线自交
  - 多实体包围盒干涉初筛（COM 干涉接口各版本差异大，保守回退）
纯几何函数不依赖 COM，可在 Linux 单测。
"""
import math

# 注意：COM 依赖（sw_core/sw_sel）在函数内惰性导入，纯几何部分可在 Linux 单测。
# ISketchSegment.GetType 常见值
_SEG_TYPES = {0: "line", 1: "arc", 2: "ellipse", 3: "spline", 4: "text",
              5: "parabola", 6: "point", 7: "equation"}


# ---------- 纯几何工具（可单测） ----------

def _endpoints(seg):
    """返回草图段端点 [(x,y),...]，单位米。读取失败返回 []。"""
    try:
        s = seg.GetStartPoint2()  # 0-based variant: x,y,z
        e = seg.GetEndPoint2()
        return [(float(s[0]), float(s[1])), (float(e[0]), float(e[1]))]
    except Exception:
        return []


def _len(seg):
    try:
        return float(seg.GetLength())
    except Exception:
        return None


def open_loops(segments):
    """端点链匹配法检测开环。返回 [(断点坐标, 断点数), ...]。

    圆弧/样条取端点近似参与链匹配，线弧混合草图仍有参考价值。
    """
    pts = []
    for i, seg in enumerate(segments):
        for p in _endpoints(seg):
            if p:
                pts.append((round(p[0], 9), round(p[1], 9)))
    if not pts:
        return []
    counts = {}
    for p in pts:
        counts[p] = counts.get(p, 0) + 1
    odd = [(p, c) for p, c in counts.items() if c % 2 == 1]
    return odd


def segment_self_intersections(segments, tol=1e-9):
    """直线段两两求交（仅 line 段），返回交点列表 [(x,y)]。"""
    lines = []
    for seg in segments:
        try:
            if int(seg.GetType()) != 0:
                continue
            s, e = _endpoints(seg)
            if len(s) == 2:
                lines.append((s, e))
        except Exception:
            continue
    hits = []
    n = len(lines)
    for i in range(n):
        (a, b) = lines[i]
        for j in range(i + 1, n):
            c, d = lines[j]
            p = _line_intersection(a, b, c, d, tol)
            if p is not None:
                # 只报非端点共线的内部相交
                if _is_inner(p, a, b, tol) and _is_inner(p, c, d, tol):
                    hits.append(p)
    return hits


def _line_intersection(a, b, c, d, tol):
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    denom = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
    if abs(denom) < tol:
        return None
    t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / denom
    u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / denom
    if -tol <= t <= 1 + tol and -tol <= u <= 1 + tol:
        return (ax + t * (bx - ax), ay + t * (by - ay))
    return None


def _is_inner(p, a, b, tol):
    eps = tol * max(1.0, abs(b[0] - a[0]), abs(b[1] - a[1]))
    return all((min(a[k], b[k]) + eps < p[k] < max(a[k], b[k]) - eps) for k in (0, 1))


def boxes_overlap(b1, b2):
    """两个 [x0,y0,z0,x1,y1,z1] 包围盒是否重叠（含接触）。"""
    return all(b1[i] <= b2[i + 3] + 1e-12 and b2[i] <= b1[i + 3] + 1e-12 for i in range(3))


def body_box_mm(body):
    try:
        b = body.GetBodyBox()
        return [float(v) * 1000.0 for v in b]
    except Exception:
        return None


# ---------- COM 检查 ----------

def feature_tree_report(model):
    """特征树报告：名称/类型/错误码/抑制状态/草图约束。"""
    import sw_core
    rows = []
    for feat in sw_core.walk_features(model):
        row = {"name": sw_core.feature_name(feat), "type": sw_core.feature_type(feat)}
        err, warn = sw_core.feature_error_codes(feat)
        row["error_code"], row["warning_code"] = err, warn
        try:
            row["suppressed"] = bool(feat.GetSuppression2())
        except Exception:
            row["suppressed"] = None
        if row["type"] == "ProfileFeature":
            try:
                sk = sw_core._early(feat.GetSpecificFeature2(), "ISketch")
                row["sketch_status"] = int(sk.GetConstrainedStatus())
            except Exception:
                row["sketch_status"] = None
        rows.append(row)
    return rows


def rebuild_report(model):
    """重建 + What's Wrong。返回 dict。"""
    import sw_core
    try:
        rebuilt = sw_core.rebuild(model)
    except Exception as exc:
        rebuilt = False
        rebuild_error = str(exc)
    else:
        rebuild_error = None
    return {"rebuild_ok": rebuilt, "rebuild_error": rebuild_error,
            "whats_wrong": sw_core.get_whats_wrong(model)}


def sketch_quality_report(sketch_feat):
    """单草图几何质量：开环、重复端点、极短图元、直线自交。"""
    import sw_core
    rec = {"sketch": sw_core.feature_name(sketch_feat)}
    try:
        sk = sw_core._early(sketch_feat.GetSpecificFeature2(), "ISketch")
        segs = [sw_core._early(s, "ISketchSegment") for s in (sk.GetSketchSegments() or [])]
    except Exception as exc:
        rec["error"] = str(exc)
        return rec
    odd = open_loops(segs)
    rec["segment_count"] = len(segs)
    rec["open_loop_points"] = len(odd)
    rec["open_loops"] = [{"x": p[0], "y": p[1], "count": c} for p, c in odd]
    rec["short_segments_mm"] = []
    for i, seg in enumerate(segs):
        ln = _len(seg)
        if ln is not None and 0 < ln * 1000.0 < 0.01:
            rec["short_segments_mm"].append({"index": i, "length_mm": round(ln * 1000.0, 6)})
    rec["self_intersections"] = segment_self_intersections(segs)
    rec["ok"] = not odd and not rec["short_segments_mm"] and not rec["self_intersections"]
    return rec


def body_interference_report(model):
    """多实体包围盒干涉初筛。返回 [(box1_mm, box2_mm), ...]。"""
    import sw_core
    try:
        part = sw_core._early(model, "IPartDoc")
        bodies = [sw_core._early(b, "IBody2") for b in (part.GetBodies2(0, False) or [])]
    except Exception as exc:
        return {"error": str(exc)}
    boxes = [(i, body_box_mm(b)) for i, b in enumerate(bodies)]
    hits = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1] and boxes[j][1] and boxes_overlap(boxes[i][1], boxes[j][1]):
                hits.append({"body_a": boxes[i][0], "body_b": boxes[j][0],
                             "box_a_mm": boxes[i][1], "box_b_mm": boxes[j][1]})
    return {"body_count": len(bodies), "bbox_overlaps": hits}


def min_wall_report(model, threshold_mm=0.5):
    """按特征错误+短边给壁厚风险提示（不保证精确；精确需 SW 检查工具）。"""
    import sw_core
    rows = []
    for feat in sw_core.walk_features(model):
        err, warn = sw_core.feature_error_codes(feat)
        if err not in (0, -1) or warn not in (0, -1):
            rows.append({"feature": sw_core.feature_name(feat),
                         "type": sw_core.feature_type(feat),
                         "error_code": err, "warning_code": warn})
    return {"threshold_mm": threshold_mm, "feature_errors": rows}


def deep_check(model):
    """零件深度检查汇总：草图约束 + 草图质量 + 特征树 + 重建 + 多实体。"""
    import sw_sketch_check
    report = {
        "sketch_constraints": sw_sketch_check.check_part(model),
        "feature_tree": feature_tree_report(model),
        "rebuild": rebuild_report(model),
        "interference": body_interference_report(model),
    }
    bad = 0
    for r in report["sketch_constraints"].get("sketches", []):
        if r.get("status_code") in (2, 4, 5, 6, 7):
            bad += 1
    for r in report["feature_tree"]:
        if r.get("error_code") not in (0, -1) or r.get("warning_code") not in (0, -1):
            bad += 1
    if not report["rebuild"]["rebuild_ok"]:
        bad += 1
    report["summary"] = f"共发现 {bad} 类问题" if bad else "检查通过 ✅"
    report["ok"] = bad == 0
    return report
