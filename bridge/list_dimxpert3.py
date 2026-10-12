# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
ex=m.Extension
for name in ['DimXpertManager','GetAnnotations','AddRenderMaterial','SetMaterialPropertyValues']:
    obj=getattr(ex,name)
    print('====',name,'====')
    print(getattr(obj,'__doc__',None))
    try:
        print('args?', getattr(obj,'argtypes',None))
    except Exception as e: pass
