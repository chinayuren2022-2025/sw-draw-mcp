# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features
sw=sw_core.connect()
m=sw_core.new_part(sw)
sw_sketch.start_sketch(m,'front')
sw_sketch.corner_rectangle(m,0,0,0.03,0.02)
sw_sketch.end_sketch(m)
sk=sw_sketch.last_sketch_feature(m).Name
b=sw_features.extrude_boss(m,sketch=sk,depth_m=0.01)
print('boss',b.Name)
sw_sketch.start_sketch(m,'front')
sw_sketch.circle(m,0.015,0.010,0.004)
sw_sketch.end_sketch(m)
sk2=sw_sketch.last_sketch_feature(m).Name
c=sw_features.extrude_cut(m,sketch=sk2,depth_m=0.005)
print('cut',c.Name)
# rename
r=sw_features.rename_feature(m,c.Name,'my_cut')
print('rename',r)
# reorder: move my_cut after boss (already), before? move my_cut before boss impossible? Try after base_sk
try:
    r2=sw_features.reorder_feature(m,'my_cut',b.Name)
    print('reorder',r2)
except Exception as e:
    print('reorder err',e)
# folder with selected my_cut
try:
    f=sw_features.create_feature_folder(m,feature_names=['my_cut'],name='cut_folder')
    print('folder', f.Name, sw_core.feature_type(f))
except Exception as e:
    print('folder err',e)
# rollback to my_cut, rollforward
try:
    print('rollback', sw_features.rollback_feature(m,name='my_cut'))
    print('rollforward', sw_features.rollforward_feature(m))
except Exception as e:
    print('roll err',e)
# appearance
try:
    print('appearance', sw_features.set_appearance(m,color_rgb=(0.8,0.1,0.1)))
except Exception as e:
    print('appearance err',e)
try:
    print('scene', sw_features.set_scene(m,'Plain White'))
except Exception as e:
    print('scene err',e)
print('done')
