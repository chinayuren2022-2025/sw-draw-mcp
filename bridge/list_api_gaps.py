# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core

def names(obj):
    return [n for n in dir(obj) if any(k in n.lower() for k in
        ('thread','cosmetic','dimxpert','annotation','roll','reorder','featurefolder','folder',
         'appearance','color','render','material','photoview','scene','background',
         'subassembly','dissolve','form','editassembly','editpart'))]

sw=sw_core.connect()
print('=== IModelDoc2 (part active?) ===')
try:
    m=sw.ActiveDoc
    if m is None:
        m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
    print('active title', sw_core.model_title(m))
    for n in names(m):
        print(n)
except Exception as e:
    print('err', e)

print('=== IPartDoc ===')
try:
    p=sw_core._early(m,'IPartDoc')
    for n in names(p):
        print(n)
except Exception as e:
    print('err', e)

print('=== IAssemblyDoc ===')
try:
    asm_path=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM'
    asm=sw_core.open_doc(sw, asm_path, doc_type=2) if os.path.exists(asm_path.replace('\\wsl.localhost\\Ubuntu-24.04','/home/zjulin/ai+sw')) else None
except Exception:
    asm=None
if asm is None:
    print('no assembly file or open fail')
else:
    for n in names(asm):
        print(n)
