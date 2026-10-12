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
s1={'kind':'plane','normal':[0,1,0],'root_mm':[0,0,10]}
s2={'kind':'plane','normal':[0,-1,0],'root_mm':[0,20,10]}
center={'kind':'plane','normal':[0,0,-1],'root_mm':[0,0,10]}
# also alternate center bottom
center2={'kind':'plane','normal':[0,0,-1],'root_mm':[0,0,0]}
for cent, centname in [(center,'top'),(center2,'bottom')]:
  for marks in [(1,2,4),(1,2,3),(1,3,2),(2,1,4),(4,2,1),(3,2,1),(1,4,2),(2,4,1)]:
    m=block(); sw_core.clear_selection(m)
    try:
        sw_sel.select_face(m,s1,mark=marks[0])
        sw_sel.select_face(m,s2,append=True,mark=marks[1])
        sw_sel.select_face(m,cent,append=True,mark=marks[2])
    except Exception as e:
        # print('sel',centname,marks,repr(e)[:80])
        continue
    fm=m.FeatureManager
    for method,argslist in [
        ('FeatureFillet3',[(0,0.0,0.0,0.0,3,0,0,None,None,None,None,None,None,None),(1,0.0,0.0,0.0,3,0,0,None,None,None,None,None,None,None),(5,0.0,0.0,0.0,3,0,0,None,None,None,None,None,None,None)]),
        ('FeatureFillet',[(0,0.0,3,0,None,None,None),(1,0.0,3,0,None,None,None),(5,0.0,3,0,None,None,None)]),
        ('FeatureFillet5',[(0,0.0,3,0,None,None,None),(1,0.0,3,0,None,None,None),(5,0.0,3,0,None,None,None)]),
    ]:
        for args in argslist:
            try:
                r=getattr(fm,method)(*args)
                if r is not None:
                    print('FOUND',centname,marks,method,args[:2],'->',r, flush=True)
                    raise SystemExit
            except Exception:
                pass
print('no combination found', flush=True)
