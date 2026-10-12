# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core

KW=('thread','cosmetic','dimxpert','annotation','roll','reorder','featurefolder','folder',
    'appearance','color','render','material','photoview','scene','background',
    'subassembly','dissolve','form','editassembly','editpart','insertnew')
def names(obj):
    try:
        ns=dir(obj)
    except Exception as e:
        print('dir error', e)
        return []
    return [n for n in ns if any(k in n.lower() for k in KW)]

sw=sw_core.connect()
print('=== IModelDoc2 ===')
try:
    m=sw.ActiveDoc
    if m is None:
        m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
    m=sw_core._early(m,'IModelDoc2')
    print('active title', sw_core.model_title(m))
    for n in names(m): print(n)
except Exception as e:
    print('err', e)

print('=== IPartDoc ===')
try:
    p=sw_core._early(m,'IPartDoc')
    for n in names(p): print(n)
except Exception as e:
    print('err', e)

print('=== IAssemblyDoc ===')
try:
    asm_path=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM'
    asm=sw_core.open_doc(sw, asm_path, doc_type=2)
    asm=sw_core._early(asm,'IAssemblyDoc')
    print('asm title', sw_core.model_title(asm))
    for n in names(asm): print(n)
except Exception as e:
    print('asm err', e)
