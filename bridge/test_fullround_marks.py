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
# use top face as center between front/back? side1 front, side2 back, center top
combos = [
    # (side1, side2, center)
    ({'kind':'plane','normal':[0,1,0]}, {'kind':'plane','normal':[0,-1,0]}, {'kind':'plane','normal':[0,0,1]}),
    ({'kind':'plane','normal':[0,1,0]}, {'kind':'plane','normal':[0,-1,0]}, {'kind':'plane','normal':[1,0,0]}),
]
for marks in [(1,2,4),(1,4,2),(2,4,1)]:
    m=block()
    s1,s2,center=combos[0]
    sw_core.clear_selection(m)
    sw_sel.select_face(m,s1,mark=marks[0])
    sw_sel.select_face(m,s2,append=True,mark=marks[1])
    sw_sel.select_face(m,center,append=True,mark=marks[2])
    fm=m.FeatureManager
    for opt in [0,1,2,3,5]:
        try:
            r=fm.FeatureFillet3(opt,0.0,0.0,0.0,3,0,0,None,None,None,None,None,None,None)
            print('marks',marks,'opt',opt,'->',r, flush=True)
            if r is not None:
                print('  PASS', flush=True); raise SystemExit
        except Exception as e:
            print('marks',marks,'opt',opt,'ERR',repr(e)[:100], flush=True)
