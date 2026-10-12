# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for fn in ['GetModelViewNames','EnumModelViews']:
    try:
        v=getattr(m,fn)()
        print(fn, type(v), repr(v)[:500])
    except Exception as e:
        print(fn, 'err', e)
