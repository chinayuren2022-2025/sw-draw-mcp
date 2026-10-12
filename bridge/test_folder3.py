# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel
sw=sw_core.connect(); m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.02,0.01); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.005)
# select boss feature via object
sw_core.clear_selection(m)
feat=sw_sel.find_feature(m,name=sk)
print('feat', sw_core.feature_name(feat), flush=True)
# select with Select2 mark 1? try different marks
for mark in [0,1,4]:
    m2=sw_core.new_part(sw)
    sw_sketch.start_sketch(m2,'front'); sw_sketch.corner_rectangle(m2,0,0,0.02,0.01); sw_sketch.end_sketch(m2)
    sk2=sw_sketch.last_sketch_feature(m2).Name; sw_features.extrude_boss(m2,sketch=sk2,depth_m=0.005)
    feat2=sw_sel.find_feature(m2,name=sk2)
    sw_core.clear_selection(m2)
    try:
        ok=sw_sel._select_entity(m2, feat2, False, mark)
        print('selected mark',mark,ok, flush=True)
        r=m2.FeatureManager.InsertFeatureTreeFolder2(1)
        print(' folder type1 r',r, flush=True)
        if r is not None:
            print('  names after', [sw_core.feature_name(f) for f in sw_core.walk_features(m2) if sw_core.feature_type(f)=='FtrFolder' or 'Ftr' in (sw_core.feature_type(f) or '')][-5:], flush=True)
    except Exception as e:
        print('err mark',mark,repr(e)[:200], flush=True)
