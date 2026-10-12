# -*- coding: utf-8 -*-
import os, sys, hashlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
dyn=sw_core._dyn(sw); dyn.ActivateDoc2('mm25_p1_1.SLDPRT', False, sw_core.err_variants()[0])
out=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\views\toggle_test'
os.makedirs(out, exist_ok=True)
def snap(name):
    p=os.path.join(out,name+'.bmp')
    m.SaveBMP(p,0,0)
    return hashlib.md5(open(p,'rb').read()).hexdigest()
print('before', snap('before'))
for meth in ['ViewDispRefplanes','ViewDispOrigins','ViewDispRefPoints','ViewDispTempRefaxes']:
    try:
        getattr(m,meth)()
        time.sleep(0.3)
        print(meth, snap(meth))
    except Exception as e:
        print(meth,'ERR',repr(e)[:120])
