# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw = sw_core.connect()
closed = []
try:
    for doc in (sw_core.com_get(sw_core._dyn(sw), "GetDocuments") or []):
        try:
            path = sw_core.com_get(doc, "GetPathName") or ""
            title = sw_core.com_get(doc, "GetTitle") or ""
        except Exception:
            continue
        if not path:
            try:
                sw_core._dyn(sw).CloseDoc(title)
                closed.append(title)
            except Exception as e:
                print("close fail", title, e)
except Exception as e:
    print("iter fail", e)
print("closed unsaved docs:", closed, flush=True)
print("remaining:", sum(1 for d in (sw_core.com_get(sw_core._dyn(sw), "GetDocuments") or [])), flush=True)
