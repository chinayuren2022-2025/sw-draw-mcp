# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel
sw=sw_core.connect()
def block():
    m=sw_core.new_part(sw)
    sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.030,0.020); sw_sketch.end_sketch(m)
    sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
    return m
# faces on block: side1 front [0,1,0], side2 back [0,-1,0], center top [0,0,1]
for marks in [(1,2,4),(1,4,2),(4,2,1),(2,4,1),(2,1,4)]:
    m=block()
    sw_core.clear_selection(m)
    try:
        sw_sel.select_face(m,{'kind':'plane','normal':[0,1,0]},mark=marks[0])
        sw_sel.select_face(m,{'kind':'plane','normal':[0,-1,0]},append=True,mark=marks[1])
        sw_sel.select_face(m,{'kind':'plane','normal':[0,0,1]},append=True,mark=marks[2])
    except Exception as e:
        print('select err',marks,repr(e)[:120]); continue
    fm=m.FeatureManager
    for opt in [0,1,2,3,5,65,66,67,195]:
        try:
            r=fm.FeatureFillet(opt,0.0,3,0,None,None,None)
            print('marks',marks,'opt',opt,'->',r, flush=True)
            if r is not None:
                print('PASS', flush=True); raise SystemExit
        except Exception as e:
            print('marks',marks,'opt',opt,'ERR',repr(e)[:80], flush=True)
