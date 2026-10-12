# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
print('clear', flush=True)
sw_core.clear_selection(m)
print('select edge', flush=True)
e, info = sw_sel.select_edge(m, {'kind':'edge','type':'circle','radius_mm':17.5,'near_mm':[75,30,50]})
print('edge ok', info.get('radius_mm'), flush=True)
fm=m.FeatureManager
print('call InsertCosmeticThread3', flush=True)
try:
    r=fm.InsertCosmeticThread3(0, '', '', 0.035, 2, 0.060, 'M35 THRU')
    print('r', r, flush=True)
except Exception as e:
    print('err', repr(e), flush=True)
print('done', flush=True)
