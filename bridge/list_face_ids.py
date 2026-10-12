# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
part=sw_core._early(m,'IPartDoc')
b=part.GetBodies2(0,False)[0]
for i,f in enumerate(b.GetFaces()):
    face=sw_core._early(f,'IFace2')
    print(i, id(face))
    if i>15: break
