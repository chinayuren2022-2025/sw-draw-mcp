# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
for attr_name in ['GetActiveConfiguration','IGetActiveConfiguration']:
    try:
        cfg=getattr(m,attr_name)()
        print(attr_name, type(cfg), repr(cfg)[:200])
        for n in dir(cfg):
            if 'Dim' in n or 'Xpert' in n or 'Annotation' in n:
                print(' ',n)
    except Exception as e:
        print(attr_name,'err',e)
