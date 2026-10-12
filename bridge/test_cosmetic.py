# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
fm=m.FeatureManager
# select a circular edge (r=0.0175 or 0.020, axis Y?)
try:
    sw_core.clear_selection(m)
    e, info = sw_sel.select_edge(m, {'kind':'edge','type':'circle','radius_mm':17.5,'near_mm':[75,30,50]})
    print('edge', info)
except Exception as e:
    print('select err', e)
    raise SystemExit
for std in [0,1,2]:
    for std_type,size in [('', ''),('Metric Tap','M35'),('','M35')]:
        try:
            r=fm.InsertCosmeticThread3(std, std_type, size, 0.035, 2, 0.060, 'M35 THRU')
            print('std',std,'type',std_type,'size',size,'->',type(r),repr(r)[:100])
            if r is not None:
                # walk newest features
                feats=list(sw_core.walk_features(m))
                print('last features', [sw_core.feature_name(f) for f in feats[-3:]])
        except Exception as e:
            print('std',std,'type',std_type,'size',size,'ERR',repr(e)[:160])
