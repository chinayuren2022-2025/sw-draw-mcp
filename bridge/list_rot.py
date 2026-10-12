# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for i in range(0,13):
    try:
        r = m.GetStandardViewRotation(i)
        print(i, repr(r)[:180])
    except Exception as e:
        print(i, 'err', repr(e)[:120])
