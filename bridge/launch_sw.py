"""启动一个干净的 SolidWorks 2018 实例并等待就绪。"""
import sys, time
import win32com.client

try:
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    print("ATTACHED existing")
except Exception:
    sw = win32com.client.Dispatch("SldWorks.Application")
    print("LAUNCHED new")

try:
    sw.Visible = True
except Exception:
    pass

rev = None
for i in range(120):
    try:
        v = sw.RevisionNumber
        if callable(v):
            v = v()
        if v:
            rev = v
            break
    except Exception as exc:
        print(f"waiting {i}: {exc}", flush=True)
    time.sleep(2)

if not rev:
    print("NOT_READY")
    sys.exit(1)
print("READY revision=", rev, flush=True)
