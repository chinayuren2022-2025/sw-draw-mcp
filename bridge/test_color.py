# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
p=sw_core._early(m,'IPartDoc')
# read current
for attr in ['MaterialPropertyValues','IMaterialPropertyValues']:
    try:
        v=getattr(p,attr)
        print(attr, type(v), repr(v)[:200])
    except Exception as e:
        print(attr,'read err',repr(e)[:160])
# set whole part via property
try:
    p.MaterialPropertyValues = (1.0,0.0,0.0, 0.1,1.0,0.5,0.5,0.0,0.0)
    print('set property ok')
except Exception as e:
    print('set property err',repr(e)[:200])
# Extension.SetMaterialPropertyValues on current selection/part
try:
    r=m.Extension.SetMaterialPropertyValues((0.0,0.0,1.0, 0.1,1.0,0.5,0.5,0.0,0.0), 1, None)
    print('extension set',r)
except Exception as e:
    print('extension err',repr(e)[:200])
