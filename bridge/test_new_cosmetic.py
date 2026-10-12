# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features
sw=sw_core.connect(); m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.circle(m,0,0,0.010); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
try:
    f=sw_features.cosmetic_thread(m, {'kind':'edge','type':'circle','radius_mm':10.0}, 0.010, depth_m=0.010, end_condition='blind', note='M20')
    print('cosmetic ok', f.Name, sw_core.feature_type(f))
except Exception as e:
    print('cosmetic err', e)
print('done')
