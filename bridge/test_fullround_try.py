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
face_sets = [
    ({'kind':'plane','normal':[0,1,0]}, {'kind':'plane','normal':[1,0,0]}, {'kind':'plane','normal':[0,-1,0]}),
    ({'kind':'plane','normal':[0,0,1]}, {'kind':'plane','normal':[1,0,0]}, {'kind':'plane','normal':[0,0,-1]}),
    ({'kind':'plane','normal':[0,1,0]}, {'kind':'plane','normal':[0,0,1]}, {'kind':'plane','normal':[0,-1,0]}),
]
for opt in [0,1,2,3,5,64,65,66,67,195,129,130,131]:
    m=block()
    try:
        # select 3 face sets with marks 1,2,4
        sw_core.clear_selection(m)
        s1,c,s2 = face_sets[0]
        sw_sel.select_face(m,s1,mark=1)
        sw_sel.select_face(m,c,append=True,mark=2)
        sw_sel.select_face(m,s2,append=True,mark=4)
        fm=m.FeatureManager
        r=fm.FeatureFillet3(opt,0.0,0.0,0.0,3,0,0,None,None,None,None,None,None,None)
        print('opt',opt,'->',r, flush=True)
        if r is not None:
            print('  PASS feature', getattr(r,'Name',r), flush=True)
    except Exception as e:
        print('opt',opt,'ERR',repr(e)[:120], flush=True)
