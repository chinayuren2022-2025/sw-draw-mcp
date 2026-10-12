# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_assembly, sw_assembly_full
BLOCK=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\asm_block.SLDPRT'
sw=sw_core.connect()
# open existing test_sub if exists else build
subpath=r'D:\ai+sw\sw-draw-skill\output\test_sub.SLDASM'
if os.path.exists(subpath):
    sub=sw_core.open_doc(sw, subpath, doc_type=2)
else:
    sub=sw_assembly.new_assembly(sw)
    c1=sw_assembly_full.insert_component_full(sub, BLOCK)
    c2=sw_assembly_full.insert_component_full(sub, BLOCK, x=0.02)
    sw_core.save_as(sub, subpath, sw=sw)
top=sw_assembly.new_assembly(sw)
try:
    comp=sw_assembly_full.insert_subassembly(top, subpath, x=0.01, y=0, z=0)
    name=sw_assembly_full._comp_name(comp)
    print('inserted',name, flush=True)
    # direct dissolve wrapper
    try:
        r=sw_assembly_full.dissolve_subassembly(top, comp)
        print('dissolve result',r, flush=True)
    except Exception as e:
        print('dissolve wrapper err',repr(e)[:300], flush=True)
    print('comps after', [x.Name2 for x in sw_assembly_full.component_list(top,top_level=False)], flush=True)
except Exception as e:
    print('main err',repr(e)[:300], flush=True)
