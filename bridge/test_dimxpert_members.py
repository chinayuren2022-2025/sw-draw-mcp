# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
dm=m.Extension.DimXpertManager('默认', True)
dp=dm.DimXpertPart
for name in ['GetDimOption','GetFeatureCount','GetAnnotationCount','InsertSizeDimension','InsertLocationDimension','InsertBasicDimension','AutoDimensionScheme','GetAutoDimSchemeOption']:
    try:
        obj=getattr(dp,name)
        print(name, type(obj).__name__, repr(obj)[:160])
        if callable(obj) and name=='GetDimOption':
            try:
                r=obj()
                print(' call ->', type(r), repr(r)[:200])
            except Exception as e:
                print(' call err', repr(e)[:200])
    except Exception as e:
        print(name,'GETATTR ERR',repr(e)[:200])
