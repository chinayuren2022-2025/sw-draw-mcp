# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
print('total', sum(1 for _ in sw_sel._faces(m)))
for f, info in ((f, sw_sel.face_info(f)) for f in sw_sel._faces(m)):
    if info.get('kind')=='plane' and info.get('normal') and abs(info['normal'][2])>0.9:
        print('z-plane', info['normal'], info['root_mm'], round(info['area_mm2'],1))
