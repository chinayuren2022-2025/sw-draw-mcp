# -*- coding: utf-8 -*-
import os, sys, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
out=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\views\test2'
os.makedirs(out, exist_ok=True)
def snap(name):
    p=os.path.join(out,name+'.bmp')
    m.SaveBMP(p,0,0)
    return hashlib.md5(open(p,'rb').read()).hexdigest()[:10]
names=['*前视','*后视','*左视','*右视','*上视','*下视','*等轴测','*上下二等角轴测','*左右二等角轴测']
for n in names:
    # ShowNamedView2(name,1)
    try:
        m.ShowNamedView2(n,1)
    except Exception as e:
        print('show2_1',n,'err',e); continue
    time.sleep(0.3); m.ViewZoomtofit2(); time.sleep(0.3)
    print('show2_1',n,snap('v2_1_'+n.strip('*')))
for n in names:
    # ShowNamedView (one arg)
    try:
        m.ShowNamedView(n)
    except Exception as e:
        print('show1',n,'err',e); continue
    time.sleep(0.3); m.ViewZoomtofit2(); time.sleep(0.3)
    print('show1 ',n,snap('v1_'+n.strip('*')))
