# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features
sw=sw_core.connect(); m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.030,0.020); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
part=sw_core._early(m,'IPartDoc')
bodies=part.GetBodies2(0,False) or []
print('bodies', len(bodies))
try:
    f=sw_features.flex(m,'bending',30, body_specs=[bodies[0]])
    print('flex ok', f.Name, sw_core.feature_type(f))
except Exception as e:
    print('flex err', repr(e)[:300])
