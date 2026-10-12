# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
for attr in ['SceneName','SceneUserName','SceneBkgImageFileName']:
    try:
        print(attr, '=', getattr(m, attr))
    except Exception as e:
        print(attr,'err',repr(e)[:160])
try:
    m.SceneName='Plain White'
    print('set SceneName ok ->',m.SceneName)
except Exception as e:
    print('set scene err',repr(e)[:200])
