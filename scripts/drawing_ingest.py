# -*- coding: utf-8 -*-
"""drawing_ingest.py — 工程图解析层。

把 PDF/图片工程图解析为可审计的结构化 JSON：
  - 整页高分辨率渲染
  - PDF 原生文本与尺寸/注释定位
  - 内嵌视图图片提取 + 按页面 bbox 裁剪
  - 输出 metadata、视图图像列表、文本标注

纯 Python + PyMuPDF + PIL，不需要 SolidWorks。
"""
import argparse
import json
import os
import sys

try:
    import pymupdf
except Exception:
    import fitz as pymupdf
from PIL import Image

# 特殊注记关键字
NOTE_KEYWORDS = [
    "THIRD ANGLE", "FIRST ANGLE", "R2 TYP", "ALL RED", "FILLETS",
    "SECTION A-A", "SECTION B-B", "SECTION A", "SECTION B",
    "ALL DIMENSIONS", "MM", "THRU", "TYP", "NOTES",
]


def norm_text(t):
    return " ".join(str(t).split())


def render_page(page, matrix=2.2, out_path=None):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(matrix, matrix), alpha=False)
    if out_path:
        pix.save(out_path)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def extract_text(page):
    """返回文本块列表，含 bounding box（PDF 坐标，pt）。"""
    out = []
    try:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                texts = []
                for span in line.get("spans", []):
                    texts.append(span.get("text", ""))
                text = norm_text("".join(texts))
                if not text:
                    continue
                bbox = list(line.get("bbox", [0, 0, 0, 0]))
                out.append({"text": text, "bbox": bbox,
                            "kind": "note" if any(k in text.upper() for k in NOTE_KEYWORDS) else "text"})
    except Exception as exc:
        print("extract_text error:", exc, flush=True)
    return out


def extract_images(page, out_dir, prefix="view"):
    """提取页面内嵌光栅图，返回描述列表。"""
    items = []
    seen = set()
    for i, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        if xref in seen:
            continue
        seen.add(xref)
        doc = getattr(page, "parent", None) or page
        try:
            data = doc.extract_image(xref)
        except Exception:
            continue
        ext = data.get("ext", "png")
        raw_path = os.path.join(out_dir, f"img_{i:02d}.{ext}")
        with open(raw_path, "wb") as f:
            f.write(data["image"])
        rects = page.get_image_rects(xref)
        rect = list(rects[0]) if rects else None
        items.append({
            "index": i,
            "xref": xref,
            "file": raw_path,
            "rect": rect,
            "width": data.get("width"),
            "height": data.get("height"),
            "ext": ext,
        })
    return items


def crop_rect(page, rect, out_path, padding=10, scale=2.0):
    """按 PDF 坐标 bbox 从渲染页裁剪，并放大。"""
    x0, y0, x1, y1 = rect
    # PyMuPDF 坐标 y 向下；PIL 与 pixmap y 一致
    box = (max(0, int(x0 * scale) - padding * scale),
           max(0, int(y0 * scale) - padding * scale),
           int(x1 * scale) + padding * scale,
           int(y1 * scale) + padding * scale)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    im.crop(box).save(out_path)
    return out_path


def ingest(inp, out_dir=None, scale=2.2, json_path=None):
    """执行图纸解析，返回结果 dict。out_dir 缺省 output/drawing/<stem>。"""
    inp = os.path.abspath(inp)
    stem = os.path.splitext(os.path.basename(inp))[0]
    out_dir = out_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "drawing", stem)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    texts = []
    images = []
    pages_meta = []

    full_path = os.path.join(out_dir, "full.png")
    if inp.lower().endswith((".pdf",)):
        doc = pymupdf.open(inp)
        for pi, page in enumerate(doc):
            texts += [dict(t, page=pi) for t in extract_text(page)]
            images += [dict(img, page=pi) for img in extract_images(page, out_dir)]
            pages_meta.append({"page": pi, "rect": list(page.rect)})
        render_page(doc[0], matrix=scale, out_path=full_path)
        for img in images:
            if img.get("rect"):
                crop_path = os.path.join(out_dir, f"crop_{img['index']:02d}.png")
                crop_rect(doc[img["page"]], img["rect"], crop_path, scale=scale)
                img["crop"] = crop_path
    else:
        im = Image.open(inp).convert("RGB")
        im.save(full_path, "PNG")

    result = {
        "source": inp,
        "out_dir": out_dir,
        "full": full_path,
        "pages": pages_meta,
        "texts": texts,
        "images": images,
    }
    jp = json_path or os.path.join(out_dir, "drawing.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    result["json"] = jp
    return result


def main():
    ap = argparse.ArgumentParser(description="解析工程图 PDF/图片")
    ap.add_argument("input", help="PDF 或图片路径")
    ap.add_argument("--out-dir", help="输出目录，默认 output/drawing/<stem>")
    ap.add_argument("--scale", type=float, default=2.2)
    ap.add_argument("--json", help="输出 JSON 路径，默认 <out>/drawing.json")
    args = ap.parse_args()
    r = ingest(args.input, out_dir=args.out_dir, scale=args.scale, json_path=args.json)
    print("drawing ingest ok:", r["json"], flush=True)
    print("images:", len(r["images"]), "texts:", len(r["texts"]), flush=True)

if __name__ == "__main__":
    main()
