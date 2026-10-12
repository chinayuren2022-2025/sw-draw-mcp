# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw.ActiveDoc
if m is None:
    m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
ex=m.Extension
for args in [('默认',False),('Default',False),('',False),('默认',True)]:
    try:
        dm=ex.DimXpertManager(*args)
        print('args',args,'->',type(dm),repr(dm)[:200])
        if dm is not None:
            print('has DimXpertPart', hasattr(dm,'DimXpertPart'))
            try:
                dp=dm.DimXpertPart
                print('DimXpertPart', type(dp), repr(dp)[:200])
                ns=dir(dp)
                print('dp methods sample', [n for n in ns if not n.startswith('_')][:120])
            except Exception as e:
                print('dp err', repr(e)[:200])
    except Exception as e:
        print('args',args,'err',repr(e)[:200])
