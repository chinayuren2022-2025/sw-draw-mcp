# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
dm=m.Extension.DimXpertManager('默认', True)
dp=dm.DimXpertPart
print('dp', type(dp), repr(dp))
try:
    ns=dir(dp)
    print('dir count', len(ns))
    print(ns[:200])
except Exception as e:
    print('dir err', repr(e)[:300])
# try common names
for name in ['InsertBasicDimension','InsertLocationDimension','InsertSizeDimension','AddDimension','GetFeatures','FeatureCount','GetFeatureCount','InsertPatternDimension','InsertCompoundAngleDimension']:
    try:
        obj=getattr(dp,name)
        print(name,'EXISTS',type(obj),repr(obj)[:120])
    except Exception as e:
        print(name,'no',repr(e)[:120])
