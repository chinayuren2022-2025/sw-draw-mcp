# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
print('DimXpertManager type')
try:
    dm=m.Extension.DimXpertManager
    print(type(dm))
    for n in dir(dm):
        print(n)
except Exception as e:
    print('err', e)
