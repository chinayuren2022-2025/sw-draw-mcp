# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw = sw_core.connect()
print('pid', sw.GetProcessID())
try:
    act = sw.ActiveDoc
    print('active:', sw_core.model_title(act) if act else None, sw_core.model_path(act) if act else None)
except Exception as e:
    print('active err', e)
docs = sw.GetDocuments() or []
print('docs', len(docs))
for i,d in enumerate(docs):
    try:
        t = sw_core.com_get(d, 'GetTitle')
        p = sw_core.com_get(d, 'GetPathName')
        typ = sw_core.com_get(d, 'GetType')
        print(i, repr(t), repr(p), typ)
    except Exception as e:
        print(i, 'err', e)
