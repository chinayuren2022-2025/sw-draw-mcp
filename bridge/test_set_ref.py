# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
dyn=sw_core._dyn(m)
for name in ['ViewDispRefplanes','ViewDispOrigins','ViewDispRefPoints','ViewDispRefpoints','ViewDispTempRefaxes']:
    try:
        setattr(dyn, name, False)
        print('setattr dyn', name, 'ok')
    except Exception as e:
        print('setattr dyn', name, 'err', repr(e)[:160])
# try early setattr
for name in ['ViewDispRefplanes','ViewDispOrigins','ViewDispRefPoints','ViewDispRefpoints','ViewDispTempRefaxes']:
    try:
        setattr(m, name, False)
        print('setattr early', name, 'ok')
    except Exception as e:
        print('setattr early', name, 'err', repr(e)[:160])
