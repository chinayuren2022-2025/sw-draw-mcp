# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel
sw=sw_core.connect(); m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.030,0.020); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
for f in sw_sel._faces(m):
    info=sw_sel.face_info(f)
    if info.get('kind')=='plane':
        print(info['normal'], info['root_mm'])
