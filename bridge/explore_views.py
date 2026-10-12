# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
try:
    av = m.ActiveView
    print('ActiveView type', type(av), 'repr', repr(av)[:200])
    for attr in ['SaveBMP','GetStandardViewRotation','SetViewOrientation','GetViewport','GetFirstModelView','GetNextModelView','GetName','SetViewOrientation2','GetType','Name']:
        try:
            obj = getattr(av, attr)
            print(' ', attr, 'exists', obj)
        except Exception as e:
            print(' ', attr, 'err', repr(e)[:200])
except Exception as e:
    print('ActiveView err', e)
print('--- first model view ---')
try:
    mv = m.GetFirstModelView()
    print('mv type', type(mv), 'repr', repr(mv)[:200])
    print('dir', [n for n in dir(mv) if any(k in n.lower() for k in ('view','bmp','orient','rotate','save','name','type'))][:100])
except Exception as e:
    print('GetFirstModelView err', e)
print('--- GetStandardViewRotation calls ---')
for args in [("*前视",), ("前视",), ("*前视", 0)]:
    try:
        r = m.GetStandardViewRotation(*args)
        print(args, 'ok', repr(r)[:500])
    except Exception as e:
        print(args, 'err', repr(e)[:300])
