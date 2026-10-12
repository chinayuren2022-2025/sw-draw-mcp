# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
for args in [(0,), (1,), (2,), (3,)]:
    try:
        r=m.Extension.DisplayMode(*args)
        print('DisplayMode',args,'->',r)
    except Exception as e:
        print('DisplayMode',args,'err',repr(e)[:160])
try:
    print('ViewDisplayRealView attr', getattr(m.Extension,'ViewDisplayRealView'))
    r=m.Extension.ViewDisplayRealView()
    print('realview call ->',r)
except Exception as e:
    print('realview err',repr(e)[:200])
