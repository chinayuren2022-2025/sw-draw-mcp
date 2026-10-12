# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
print('type', type(m))
try:
    names = dir(m)
except Exception as e:
    print('dir failed', e)
    names=[]
for n in names:
    if any(k in n.lower() for k in ('view','orient','savebmp','bmp','zoom','rotate','standard')):
        print(n)
