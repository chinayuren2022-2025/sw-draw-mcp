# -*- coding: utf-8 -*-
"""环境自检脚本（目标机 Windows 使用）。
检查 Python、依赖包、可选 OpenCV、SolidWorks COM 是否可用。
"""
import importlib
import platform
import sys

REQUIRED = {
    "pywin32": "pythoncom",
    "mcp": "mcp",
    "pymupdf": "pymupdf",
    "Pillow": "PIL",
}
OPTIONAL = {
    "opencv-python-headless": "cv2",
}


def check(name, module_name):
    try:
        importlib.import_module(module_name)
        print(f"  [OK] {name}")
        return True
    except Exception as exc:
        print(f"  [MISS] {name}: {type(exc).__name__}: {exc}")
        return False


def main():
    print("Python:", sys.version.split()[0], "on", platform.system())
    ok = True
    print("\n核心依赖：")
    for name, mod in REQUIRED.items():
        ok &= check(name, mod)
    print("\n可选依赖：")
    for name, mod in OPTIONAL.items():
        check(name, mod)

    print("\nSolidWorks COM：")
    try:
        import win32com.client
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        print("  [OK] SolidWorks 正在运行, Revision:", sw.RevisionNumber())
    except Exception as exc:
        print("  [INFO] SolidWorks 未运行或 COM 未注册:", type(exc).__name__)
        print("  （如果本机已安装 SW2018，请先启动 SolidWorks 再测试）")
    print("\n结论:", "OK" if ok else "存在缺失，请先安装依赖")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
