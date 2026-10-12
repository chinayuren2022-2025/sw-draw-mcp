# -*- coding: utf-8 -*-
"""model_view_compare.py — 模型视图 vs 工程图视图差异检测。

CV 部分默认关闭，不依赖 OpenCV；默认只生成 side_by_side PNG（Pillow）。
启用 `--cv` 时才使用 OpenCV 做边缘 IoU / Hough 圆检测。
"""
import argparse
import json
import os
import sys

from PIL import Image

DEFAULT_MAPPING = {
    "front": "crop_00.png",
    "top": "crop_01.png",
    "section_a": "crop_02.png",
    "section_b": "crop_03.png",
    "isometric": "crop_04.png",
}


def read_pil(path):
    return Image.open(path).convert("RGB")


def side_by_side_pil(draw_path, model_path, out_path, height=360):
    a = read_pil(draw_path)
    b = read_pil(model_path)
    def rs(im):
        w = max(1, int(im.width * height / im.height))
        return im.resize((w, height))
    a = rs(a)
    b = rs(b)
    canvas = Image.new("RGB", (a.width + b.width + 10, height), (255, 255, 255))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 10, 0))
    canvas.save(out_path, "PNG")
    return out_path


def _cv_edge_iou(draw_path, model_path, size=(480, 360)):
    import cv2
    import numpy as np

    def _object_bbox(im, th):
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        mask = (gray < th).astype(np.uint8)
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return 0, 0, im.shape[1], im.shape[0]
        pad = 8
        x0 = max(0, int(xs.min()) - pad)
        y0 = max(0, int(ys.min()) - pad)
        x1 = min(im.shape[1], int(xs.max()) + pad)
        y1 = min(im.shape[0], int(ys.max()) + pad)
        return x0, y0, x1, y1

    def edge_map(im, th):
        x0, y0, x1, y1 = _object_bbox(im, th)
        crop = im[y0:y1, x0:x1]
        if crop.size == 0:
            crop = im
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 50, 150)
        edges = cv2.resize(edges, size)
        return (edges > 0).astype(np.uint8)

    draw = cv2.imread(draw_path)
    model = cv2.imread(model_path)
    if draw is None or model is None:
        raise RuntimeError("OpenCV 无法读取图片")
    de = edge_map(draw, 235)
    me = edge_map(model, 220)
    inter = np.logical_and(de, me).sum()
    union = np.logical_or(de, me).sum()
    iou = float(inter / union) if union else 1.0

    def circles(im, th):
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        h, w = gray.shape
        cs = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2,
                              minDist=min(h, w) * 0.15,
                              param1=80, param2=40,
                              minRadius=max(3, int(min(h, w) * 0.03)),
                              maxRadius=max(6, int(min(h, w) * 0.45)))
        out = []
        if cs is not None:
            for x, y, r in cs[0]:
                out.append({"x": float(x / w), "y": float(y / h),
                            "r": float(r / min(h, w))})
        return out

    return {
        "edge_iou": round(iou, 4),
        "drawing_circles": circles(draw, 235),
        "model_circles": circles(model, 220),
    }


def compare_pair(draw_path, model_path, tag, out_dir, enable_cv=False):
    sbs = side_by_side_pil(draw_path, model_path,
                           os.path.join(out_dir, f"compare_{tag}.png"))
    result = {
        "tag": tag,
        "drawing": draw_path,
        "model": model_path,
        "side_by_side": sbs,
        "cv_enabled": bool(enable_cv),
    }
    if enable_cv:
        try:
            metrics = _cv_edge_iou(draw_path, model_path)
            result.update(metrics)
            result["heuristic"] = "ok" if metrics["edge_iou"] >= 0.5 else "needs_review"
        except Exception as exc:
            result["cv_error"] = f"{type(exc).__name__}: {exc}"
            result["heuristic"] = "needs_review"
    else:
        result["heuristic"] = "needs_visual_review"
    return result


def compare(drawing_json, model_views_dir, mapping=None, out=None, enable_cv=False):
    """执行模型/图纸视图差异检测，返回结果 dict。"""
    with open(drawing_json, "r", encoding="utf-8") as f:
        ingest = json.load(f)
    out_dir = ingest.get("out_dir", os.path.dirname(os.path.abspath(drawing_json)))
    mapping = mapping or DEFAULT_MAPPING
    results = []
    for tag, crop_name in mapping.items():
        draw_candidates = [
            os.path.join(out_dir, crop_name),
            os.path.join(out_dir, "crop_" + crop_name.lstrip("crop_")),
        ]
        draw_path = next((p for p in draw_candidates if os.path.exists(p)), None)
        if not draw_path:
            print("skip", tag, "no drawing crop", crop_name, flush=True)
            continue
        model_path = os.path.join(model_views_dir, tag + ".png")
        if not os.path.exists(model_path):
            print("skip", tag, "no model view", model_path, flush=True)
            continue
        print("compare", tag, flush=True)
        results.append(compare_pair(draw_path, model_path, tag, out_dir,
                                    enable_cv=enable_cv))
    out_path = out or os.path.join(out_dir, "compare.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cv_enabled": bool(enable_cv), "results": results},
                  f, ensure_ascii=False, indent=2)
    return {"out": out_path, "results": results}


def main():
    ap = argparse.ArgumentParser(description="模型视图与图纸视图差异检测（默认仅 side-by-side，无 OpenCV 依赖）")
    ap.add_argument("drawing_json", help="drawing_ingest 输出的 JSON")
    ap.add_argument("model_views_dir", help="capture_model_views 输出的 PNG 目录")
    ap.add_argument("--mapping", default="",
                    help="逗号分隔 tag=crop_file，如 front=crop_00.png,top=crop_01.png")
    ap.add_argument("--out", help="compare.json 输出路径")
    ap.add_argument("--cv", action="store_true", help="启用 OpenCV 边缘/圆识别（默认关闭）")
    args = ap.parse_args()
    mapping = {}
    if args.mapping:
        for part in args.mapping.split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            mapping[k.strip()] = v.strip()
    r = compare(args.drawing_json, args.model_views_dir,
                mapping=mapping or None, out=args.out, enable_cv=args.cv)
    print("compare ok:", r["out"], flush=True)


if __name__ == "__main__":
    main()
