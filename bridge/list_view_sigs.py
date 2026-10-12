# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for name in ['ShowNamedView','ShowNamedView2','GetStandardViewRotation','SaveBMP','ViewZoomtofit2','ActiveView','IActiveView']:
    obj=getattr(m,name,None)
    print('====', name, '====')
    try:
        print(obj.__doc__)
    except Exception as e:
        print('no doc', e)
