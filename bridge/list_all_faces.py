# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for i,(f, info) in enumerate(( (f, sw_sel.face_info(f)) for f in sw_sel._faces(m) )):
    if info.get('kind')=='plane':
        n=info.get('normal'); r=info.get('root_mm')
        print(i, 'plane', [round(x,3) for x in n], [round(x,1) for x in r], round(info.get('area_mm2',0),1))
