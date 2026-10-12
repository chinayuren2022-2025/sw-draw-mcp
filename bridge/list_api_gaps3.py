# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
KW=('dim','dimxpert','annotation','note','render','color','material','view','display','thread','cosmetic','scene','appearance','featurefolder','roll','reorder')
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
for obj_name in ['Extension','FeatureManager','SelectionManager']:
    print('====',obj_name,'====')
    try:
        obj=getattr(m,obj_name)
        for n in dir(obj):
            if any(k in n.lower() for k in KW):
                print(n)
    except Exception as e:
        print('err',e)
