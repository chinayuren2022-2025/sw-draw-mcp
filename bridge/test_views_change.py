# -*- coding: utf-8 -*-
import os, sys, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
out=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\views\test'
os.makedirs(out, exist_ok=True)
def snap(name):
    p=os.path.join(out, name+'.bmp')
    ok=m.SaveBMP(p,0,0)
    print('snap',name,'ok',ok)
    return p
def trycall(desc, fn):
    try:
        r=fn()
        print('call',desc,'ok',r)
    except Exception as e:
        print('call',desc,'ERR',repr(e)[:200])
trycall('ShowNamedView2 *前视', lambda: m.ShowNamedView2('*前视',0))
time.sleep(0.5); m.ViewZoomtofit2(); time.sleep(0.5); p1=snap('after_show2_0')
trycall('ShowNamedView2 *前视 1', lambda: m.ShowNamedView2('*前视',1))
time.sleep(0.5); m.ViewZoomtofit2(); time.sleep(0.5); p2=snap('after_show2_1')
trycall('ShowNamedView *前视', lambda: m.ShowNamedView('*前视'))
time.sleep(0.5); m.ViewZoomtofit2(); time.sleep(0.5); p3=snap('after_show1')
trycall('ViewRotateplusx', lambda: m.ViewRotateplusx())
time.sleep(0.5); m.ViewZoomtofit2(); time.sleep(0.5); p4=snap('after_rot_plusx')
trycall('ViewRotateplusy', lambda: m.ViewRotateplusy())
time.sleep(0.5); m.ViewZoomtofit2(); time.sleep(0.5); p5=snap('after_rot_plusy')
for pth in [p1,p2,p3,p4,p5]:
    h=hashlib.md5(open(pth,'rb').read()).hexdigest()
    print(os.path.basename(pth), h, os.path.getsize(pth))
