# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel
sw=sw_core.connect()
m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.030,0.020); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
s1={'kind':'plane','normal':[0,1,0],'root_mm':[0,0,10]}
s2={'kind':'plane','normal':[0,-1,0],'root_mm':[0,20,10]}
center={'kind':'plane','normal':[0,0,-1],'root_mm':[0,0,10]}
for radius in [0.001,0.005,0.01]:
  m2=sw_core.new_part(sw)
  sw_sketch.start_sketch(m2,'front'); sw_sketch.corner_rectangle(m2,0,0,0.030,0.020); sw_sketch.end_sketch(m2)
  sk=sw_sketch.last_sketch_feature(m2).Name; sw_features.extrude_boss(m2,sketch=sk,depth_m=0.010)
  sw_core.clear_selection(m2)
  sw_sel.select_face(m2,s1,mark=1); sw_sel.select_face(m2,s2,append=True,mark=2); sw_sel.select_face(m2,center,append=True,mark=4)
  r=m2.FeatureFillet3(radius, True, 3, 0, 0, 0, None, False, False)
  print('radius',radius,'return',r, 'feat count', len(list(sw_core.walk_features(m2))), flush=True)
  print([sw_core.feature_name(f) for f in sw_core.walk_features(m2) if sw_core.feature_type(f) not in ('RefPlane','OriginProfileFeature','ProfileFeature','Extrusion')], flush=True)
