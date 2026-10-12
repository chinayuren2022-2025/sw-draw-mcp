# -*- coding: utf-8 -*-
"""drawing_interpret.py — 视图理解层。

在 drawing_ingest 输出的裁剪图上做程序化分析：
  - 二值化 + 外轮廓检测
  - HoughCircles 圆检测
  - 基础视图类型提示（front/top/section/unknown）
  - 与 PDF 文本尺寸关联，输出 interpretation.json

纯 Python（Pillow + numpy + OpenCV headless）；OpenCV 从本地 .pip-deps
加载（如存在）。不连接 SolidWorks。
"""
import argparse
import json
import os
import sys

# 允许在 WSL 开发环境使用本地安装的 opencv
_PIP_DEPS = "/home/zjulin/ai+sw/.pip-deps"
if os.path.isdir(_PIP_DEPS) and _PIP_DEPS not in sys.path:
    sys.path.insert(0, _PIP_DEPS)

import cv2
import numpy as np


def load_image(path):
    im = cv2.imread(path)
    if im is None:
        raise RuntimeError(f"无法读取 {path}")
    return im


def nonwhite_mask(im, thresh=235):
    """非白色区域掩码（图纸上不再只有白底）。"""
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    mask = (gray < thresh).astype(np.uint8) * 255
    return mask


def largest_contour(im):
    mask = nonwhite_mask(im)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None
    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    return c, {"x": int(x), "y": int(y), "w": int(w), "h": int(h),
               "area": float(cv2.contourArea(c))}


def detect_circles(im, min_radius_ratio=0.03, max_radius_ratio=0.45):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    h, w = gray.shape
    min_r = max(5, int(min(h, w) * min_radius_ratio))
    max_r = max(10, int(min(h, w) * max_radius_ratio))
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2,
                               minDist=min_r * 1.5,
                               param1=80, param2=30,
                               minRadius=min_r, maxRadius=max_r)
    out = []
    if circles is not None:
        for x, y, r in circles[0]:
            out.append({"x": float(x), "y": float(y), "radius": float(r)})
    return out


def classify_view(contour, circles, im):
    h, w = im.shape[:2]
    aspect = w / h if h else 1
    n = len(circles)
    if n >= 2 and contour and contour["w"] > contour["h"] * 1.8:
        return "front"
    if n >= 1 and contour and contour["h"] > contour["w"] * 0.6 and aspect > 1.5:
        return "top"
    if n == 0 and contour and contour["h"] < contour["w"] * 0.5:
        return "section"
    return "unknown"


def interpret_image(path, name):
    im = load_image(path)
    h, w = im.shape[:2]
    contour, cbox = largest_contour(im)
    circles = detect_circles(im)
    return {
        "file": path,
        "name": name,
        "size": {"w": w, "h": h},
        "outer_contour": cbox,
        "circles": circles,
        "circle_count": len(circles),
        "view_hint": classify_view(cbox, circles, im),
        "raw": True,
    }


def interpret(drawing_json, out=None, enable_cv=False):
    """执行视图理解，返回结果 dict。

    enable_cv=False 时只聚合文本/裁剪图信息，不依赖 OpenCV（默认，便于移植）。
    enable_cv=True 且本地有 OpenCV 时，才运行轮廓/圆检测。
    """
    with open(drawing_json, "r", encoding="utf-8") as f:
        ingest = json.load(f)
    out_dir = ingest.get("out_dir", os.path.dirname(os.path.abspath(drawing_json)))
    interpretations = []
    cv_available = False
    if enable_cv:
        try:
            import cv2  # noqa: F401
            cv_available = True
        except Exception as exc:
            print("OpenCV 不可用，跳过 CV 识别:", exc, flush=True)
    for img in ingest.get("images", []):
        crop = img.get("crop") or img.get("file")
        if not crop or not os.path.exists(crop):
            continue
        print("interpret", img.get("index"), crop, flush=True)
        if cv_available:
            interpretations.append(interpret_image(crop, f"img{img.get('index', 0):02d}"))
        else:
            from PIL import Image
            try:
                size = Image.open(crop).size
            except Exception:
                size = [0, 0]
            interpretations.append({
                "file": crop,
                "name": f"img{img.get('index', 0):02d}",
                "size": {"w": size[0], "h": size[1]},
                "cv": False,
                "view_hint": "unknown",
            })
    notes = [t["text"] for t in ingest.get("texts", [])]
    result = {
        "source": ingest.get("source"),
        "cv_enabled": bool(cv_available),
        "images": interpretations,
        "texts": notes,
        "notes": [t for t in notes if any(k in t.upper() for k in
                                        ("R2 TYP", "THRU", "SECTION", "THIRD", "FIRST", "ALL DIMENSIONS"))],
    }
    out_path = out or os.path.join(out_dir, "interpretation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    result["json"] = out_path
    return result


def main():
    ap = argparse.ArgumentParser(description="视图理解：对 drawing_ingest 的裁剪图做分析")
    ap.add_argument("drawing_json", help="drawing_ingest 输出的 JSON")
    ap.add_argument("--out", help="输出 interpretation.json 路径")
    ap.add_argument("--cv", action="store_true", help="启用 OpenCV 轮廓/圆识别（默认关闭）")
    args = ap.parse_args()
    r = interpret(args.drawing_json, out=args.out, enable_cv=args.cv)
    print("interpretation ok:", r["json"], "cv_enabled=", r["cv_enabled"], flush=True)

if __name__ == "__main__":
    main()
