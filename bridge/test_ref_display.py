# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
for name in ['ViewDispRefplanes','ViewDispOrigins','ViewDispRefpoints','ViewDispTempRefaxes','ViewDispRefaxes']:
    obj = getattr(m, name, None)
    print(name, type(obj), obj)
    try:
        r = obj()
        print('  call() ->', r)
    except Exception as e:
        print('  call err', repr(e)[:120])
    try:
        r = obj(False)
        print('  call(False) ->', r)
    except Exception as e:
        print('  call(False) err', repr(e)[:120])
