# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel
sw=sw_core.connect(); m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front'); sw_sketch.corner_rectangle(m,0,0,0.02,0.01); sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name; sw_features.extrude_boss(m,sketch=sk,depth_m=0.005)
fm=m.FeatureManager
for method,args in [('InsertFeatureTreeFolder',()),('InsertFeatureTreeFolder2',(0,)),('InsertFeatureTreeFolder2',(1,)),('InsertFeatureTreeFolder2',(2,))]:
    before=[sw_core.feature_name(f) for f in sw_core.walk_features(m)]
    sw_core.clear_selection(m)
    try:
        r=getattr(fm,method)(*args)
        print(method,args,'->',r,flush=True)
        after=[f for f in sw_core.walk_features(m) if f not in [x for x in sw_core.walk_features(m)]]
        print('features tail', [sw_core.feature_name(f) for f in list(sw_core.walk_features(m))[-6:]], flush=True)
    except Exception as e:
        print(method,args,'ERR',repr(e)[:200], flush=True)
