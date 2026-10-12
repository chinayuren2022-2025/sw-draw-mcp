# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
cfg=m.GetActiveConfiguration()
print('cfg type',type(cfg))
for attr in ['DimXpertManager','GetDimXpertManager']:
    try:
        obj=getattr(cfg,attr)
        print(attr,'obj',type(obj),repr(obj)[:200])
        if callable(obj):
            try:
                r=obj()
                print(' call ->',type(r),repr(r)[:200])
                if r is not None:
                    ns=dir(r)
                    print(' methods sample', [n for n in ns if not n.startswith('_')][:60])
            except Exception as e:
                print(' call err',repr(e)[:200])
    except Exception as e:
        print(attr,'attr err',repr(e)[:200])
