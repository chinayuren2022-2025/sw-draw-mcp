# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
p=sw_core._early(m,'IPartDoc')
print('feats', [sw_core.feature_name(f) for f in sw_core.walk_features(m)])
# rename fillet? feature 圆角1 -> test?
f=sw_sel.find_feature(m,name='圆角1')
print('f type', sw_core.feature_type(f))
try:
    f.Name='圆角_R2'
    print('rename ok')
except Exception as e:
    print('rename err', repr(e)[:200])
# reorder: move 孔1 after 切除-拉伸2? 
try:
    r=p.ReorderFeature('孔1','切除-拉伸2')
    print('reorder ->',r)
except Exception as e:
    print('reorder err', repr(e)[:200])
print('feats after', [sw_core.feature_name(f) for f in sw_core.walk_features(m)])
# rollback: select 镜向1 then part.EditRollback
try:
    sw_sel.select_feature(m,name='镜向1')
    r=p.EditRollback()
    print('rollback ->',r)
    print('feats after rollback', [sw_core.feature_name(f) for f in sw_core.walk_features(m)])
except Exception as e:
    print('rollback err',repr(e)[:200])
# rollforward
try:
    r=p.EditRollforward()
    print('rollforward ->',r)
except Exception as e:
    print('rollforward err',repr(e)[:200])
# folder creation with selected features
try:
    sw_core.clear_selection(m)
    sw_sel.select_feature(m,name='孔1')
    fm=m.FeatureManager
    fr=fm.InsertFeatureTreeFolder2(0)
    print('folder ->',type(fr),repr(fr)[:200])
    print('feats', [sw_core.feature_name(f) for f in sw_core.walk_features(m)])
except Exception as e:
    print('folder err',repr(e)[:200])
