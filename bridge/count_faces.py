# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
part=sw_core._early(m,'IPartDoc')
print('bodies 0:', part.GetBodies2(0,False))
try:
    b=part.GetBodies2(0,False)[0]
    print('body type', type(b))
    f=b.GetFaces()
    print('faces count?', len(f) if hasattr(f,'__len__') else type(f), f)
except Exception as e:
    print('err', e)
