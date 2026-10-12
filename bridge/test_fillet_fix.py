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
# constant
m=block()
try:
    f=sw_features.fillet(m,0.001, edge_specs={'kind':'edge','type':'line'})
    print('constant PASS', f.Name, sw_core.feature_type(f), flush=True)
except Exception as e:
    print('constant FAIL', repr(e)[:200], flush=True)
# variable
m=block()
try:
    f=sw_features.fillet(m,0.001, fillet_type='variable',
                         edge_specs={'kind':'edge','type':'line'},
                         radii_mm=[0.5,1.5])
    print('variable PASS', f.Name, sw_core.feature_type(f), flush=True)
except Exception as e:
    print('variable FAIL', repr(e)[:300], flush=True)
# face
m=block()
try:
    f=sw_features.fillet(m,0.001, fillet_type='face',
                         edge_specs={'kind':'plane','normal':[0,0,1]},
                         face_specs2={'kind':'plane','normal':[1,0,0]})
    print('face PASS', f.Name, sw_core.feature_type(f), flush=True)
except Exception as e:
    print('face FAIL', repr(e)[:300], flush=True)
# full_round
m=block()
try:
    f=sw_features.full_round_fillet(m,
        side_face_specs1={'kind':'plane','normal':[0,1,0]},
        center_face_spec={'kind':'plane','normal':[1,0,0]},
        side_face_specs2={'kind':'plane','normal':[0,-1,0]})
    print('full_round PASS', f.Name, sw_core.feature_type(f), flush=True)
except Exception as e:
    print('full_round FAIL', repr(e)[:300], flush=True)
