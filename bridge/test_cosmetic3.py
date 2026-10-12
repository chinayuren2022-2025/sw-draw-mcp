# -*- coding: utf-8 -*-
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel, sw_sketch, sw_features
sw=sw_core.connect()
m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front')
sw_sketch.circle(m,0,0,0.010)
sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name
sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
print('built boss', flush=True)
# collect circular edges directly
edges=[]
for e in sw_sel._edges(m):
    info=sw_sel.edge_info(e)
    if info.get('type')=='circle':
        edges.append((e,info))
print('circle edges', len(edges), [x[1].get('radius_mm') for x in edges], flush=True)
if edges:
    sw_core.clear_selection(m)
    ok=sw_sel._select_entity(m, edges[0][0], False, 0)
    print('selected edge', ok, flush=True)
    fm=m.FeatureManager
    try:
        r=fm.InsertCosmeticThread3(0,'','',0.010,0,0.010,'M20 test')
        print('cosmetic3 r', r, flush=True)
    except Exception as e:
        print('cosmetic3 err',repr(e)[:300], flush=True)
    print('feats tail', [sw_core.feature_name(f) for f in list(sw_core.walk_features(m))[-5:]], flush=True)
