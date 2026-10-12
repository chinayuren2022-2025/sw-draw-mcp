# -*- coding: utf-8 -*-
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw = sw_core.connect()
model = sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
dyn = sw_core._dyn(model)
print('has SaveBMP', hasattr(dyn, 'SaveBMP'))
p = r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\views\savebmp_test.bmp'
import os
os.makedirs(os.path.dirname(p), exist_ok=True)
for args in [(p,), (p, 0), (p, 0, 0), (p, 0, 0, 0)]:
    try:
        r = dyn.SaveBMP(*args)
        print('args', args, 'ok', r, 'exists', os.path.exists(p), 'size', os.path.getsize(p) if os.path.exists(p) else None)
        os.remove(p) if os.path.exists(p) else None
    except Exception as e:
        print('args', args, 'err', repr(e))
