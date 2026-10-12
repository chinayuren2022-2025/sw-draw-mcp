"""WSL → PowerShell 7 → Windows Python → SolidWorks 2018 COM 链路探针。

在 Windows 执行节点（或从 WSL 经 pwsh）运行：
    python sw_bridge_probe.py

检查项：
  1. Python / pywin32 / mcp 环境
  2. SW2018 COM 连接（附着或启动）
  3. makepy 早绑定缓存（TLB v26）
  4. 当前文档状态（只读探活，不建模）
"""
import sys

try:
    import pythoncom  # noqa: F401
    import win32com.client
    from win32com.client import gencache
except Exception as exc:
    print("IMPORT_FAIL:", exc)
    sys.exit(1)

SW_TLB = ("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 26, 0)
print("pywin32 ok")

try:
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    mode = "ATTACHED"
except Exception:
    sw = win32com.client.Dispatch("SldWorks.Application")
    mode = "LAUNCHED"
    try:
        sw.Visible = True
    except Exception:
        pass

rev = sw.RevisionNumber
if callable(rev):
    rev = rev()
print("MODE:", mode)
print("REVISION:", rev)

try:
    mod = gencache.EnsureModule(SW_TLB[0], SW_TLB[1], SW_TLB[2], SW_TLB[3])
    print("EARLY_BIND_MODULE:", mod.__name__)
except Exception as exc:
    print("EARLY_BIND_FAIL:", exc)

try:
    doc = sw.ActiveDoc
    title = doc.GetTitle if doc is not None else None
    print("ACTIVE_DOC:", title)
except Exception as exc:
    print("ACTIVE_DOC_ERR:", exc)

try:
    print("OPEN_DOC_COUNT:", sw.GetDocumentCount())
except Exception as exc:
    print("DOC_COUNT_ERR:", exc)

print("SW_COM_PROBE_OK")
