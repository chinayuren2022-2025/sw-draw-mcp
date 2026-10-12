# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_assembly, sw_assembly_full
BLOCK=r'D:\FastProgram\SW2018\SOLIDWORKS\..\..\..\ai+sw\sw-draw-skill\output\asm_block.SLDPRT'
# use Windows local path if exists
for cand in [r'D:\ai+sw\sw-draw-skill\output\asm_block.SLDPRT', r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\asm_block.SLDPRT']:
    if os.path.exists(cand):
        BLOCK=cand; break
print('block', BLOCK, os.path.exists(BLOCK), flush=True)
sw=sw_core.connect()
sub=sw_assembly.new_assembly(sw)
c1=sw_assembly_full.insert_component_full(sub, BLOCK)
c2=sw_assembly_full.insert_component_full(sub, BLOCK, x=0.02)
subpath=r'D:\ai+sw\sw-draw-skill\output\test_sub.SLDASM'
os.makedirs(os.path.dirname(subpath), exist_ok=True)
try:
    sw_core.save_as(sub, subpath, sw=sw)
    print('sub saved', subpath, flush=True)
except Exception as e:
    print('sub save err', e, flush=True)
    subpath=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\test_sub.SLDASM'
    sw_core.save_as(sub, subpath, sw=sw)
    print('sub saved2', subpath, flush=True)
top=sw_assembly.new_assembly(sw)
try:
    comp=sw_assembly_full.insert_subassembly(top, subpath, x=0.01, y=0, z=0)
    name=sw_assembly_full._comp_name(comp)
    print('inserted',name, flush=True)
    found=sw_assembly_full.find_component(top,name)
    # try dissolve with different selection
    for type_name in ['COMPONENT','BODYFEATURE']:
        sw_core.clear_selection(top)
        try:
            ok=sw_core.select_by_id(top, name, type_name, 0,0,0, False, 0)
            print('select',type_name,ok, flush=True)
            if ok:
                ret=sw_assembly_full._as_asm(top).DissolveSubAssembly()
                print('dissolve after',type_name,'->',ret, flush=True)
                if ret:
                    print('components after', [x.Name2 for x in sw_assembly_full.component_list(top,top_level=False)], flush=True)
                    break
        except Exception as e:
            print('dissolve err',type_name,repr(e)[:200], flush=True)
except Exception as e:
    print('main err',repr(e)[:300], flush=True)
