# -*- coding: utf-8 -*-
"""从 SolidWorks 实机中按标准视角导出模型位图，用于与工程图三视图比对。

用法：
    python scripts/capture_model_views.py [模型路径] [输出目录]

依赖：Windows 端 pywin32 + sw_core；输出 BMP，可再用 PIL 转 PNG。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_core

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_MODEL = os.path.join(ROOT, "output", "mm25_p1_1.SLDPRT")
DEFAULT_OUT = os.path.join(ROOT, "output", "views")

VIEWS = [
    ("isometric", "*等轴测"),
    ("front", "*前视"),
    ("back", "*后视"),
    ("right", "*右视"),
    ("left", "*左视"),
    ("top", "*上视"),
    ("bottom", "*下视"),
    ("trimetric", "*上下二等角轴测"),
    ("dimetric", "*左右二等角轴测"),
]


def set_view(model, name):
    dyn = sw_core._dyn(model)
    try:
        dyn.ShowNamedView(name)
    except Exception as exc:
        print(f"  view {name}: ShowNamedView2 失败: {exc}", flush=True)
        return False
    try:
        dyn.ViewZoomtofit2()
    except Exception:
        try:
            dyn.ViewZoomtofit()
        except Exception:
            pass
    time.sleep(0.6)
    return True


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    out_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    print("connecting...", flush=True)
    sw = sw_core.connect()
    model = sw_core.open_doc(sw, model_path)
    title = sw_core.model_title(model)
    print("model:", title, flush=True)
    # 激活文档，确保 SaveBMP 保存的是当前可视模型视图
    errors, warnings = sw_core.err_variants()
    try:
        sw_core._dyn(sw).ActivateDoc2(title, False, errors)
    except Exception as exc:
        print("activate failed:", exc, flush=True)
    # 隐藏参考基准面/原点等辅助显示，便于对比（SW2018 这些是无参 toggle 方法）
    for meth_name in ("ViewDispRefplanes", "ViewDispOrigins",
                      "ViewDispRefPoints", "ViewDispTempRefaxes"):
        try:
            getattr(model, meth_name)()
        except Exception as exc:
            print(f"toggle {meth_name} failed:", exc, flush=True)
    time.sleep(0.8)
    for tag, vname in VIEWS:
        print("capture", vname, flush=True)
        if not set_view(model, vname):
            continue
        bmp = os.path.join(out_dir, tag + ".bmp")
        png = os.path.join(out_dir, tag + ".png")
        try:
            ok = sw_core._dyn(model).SaveBMP(bmp, 0, 0)
            if ok:
                from PIL import Image
                im = Image.open(bmp).convert("RGB")
                im.thumbnail((1200, 750))
                im.save(png, "PNG")
                print("  saved", tag, "png", os.path.getsize(png), flush=True)
                try:
                    os.remove(bmp)
                except OSError:
                    pass
            else:
                print("  savebmp returned false", tag, flush=True)
        except Exception as exc:
            print("  savebmp failed:", exc, flush=True)


if __name__ == "__main__":
    main()
