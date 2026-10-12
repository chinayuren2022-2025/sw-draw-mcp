# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_assembly, sw_assembly_full
sub=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM'
sw=sw_core.connect()
top=sw_assembly.new_assembly(sw)
c=sw_assembly_full.insert_subassembly(top, sub, x=0.01, y=0, z=0)
name=sw_assembly_full._comp_name(c)
print('inserted', name, flush=True)
# edit subassembly
sw_assembly_full.edit_subassembly(top,c)
print('active after edit', sw_core.model_title(sw.ActiveDoc), flush=True)
# try dissolve on active doc
try:
    ret=sw_assembly_full._as_asm(sw.ActiveDoc).DissolveSubAssembly()
    print('dissolve on active ->', ret, flush=True)
except Exception as e:
    print('dissolve on active err', repr(e)[:200], flush=True)
# see top components
try:
    top2=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM', doc_type=2)
    print('active again?', sw_core.model_title(top2), flush=True)
except Exception as e: print(e)
print('done')
