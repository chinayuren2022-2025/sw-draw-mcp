# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for n in dir(m):
    if any(k in n.lower() for k in ('disp','display','refplane','refplane','origin','refaxis','refpoint')):
        try:
            obj=getattr(m,n)
            print(n, type(obj).__name__)
        except Exception as e:
            print(n, 'ERR', e)
