# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
dm=m.Extension.DimXpertManager('默认', True)
dp=dm.DimXpertPart
print('manager ok', dm is not None, 'features', dp.GetFeatureCount)
try:
    sw_core.clear_selection(m)
    face, info = sw_sel.select_face(m, {'kind':'cylinder','radius_mm':17.5,'axis':[0,1,0]})
    print('selected face', info.get('radius_mm'))
except Exception as e:
    print('select face err', e)
try:
    opt=dp.GetDimOption()
    print('dim option', type(opt), repr(opt)[:200])
    r=dp.InsertSizeDimension(opt)
    print('InsertSizeDimension ->', r)
    print('features after', dp.GetFeatureCount, 'annotations', dp.GetAnnotationCount)
except Exception as e:
    print('insert err', repr(e)[:300])
