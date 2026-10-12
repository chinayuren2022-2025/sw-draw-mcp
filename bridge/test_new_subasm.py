# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_assembly, sw_assembly_full
sub=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM'
sw=sw_core.connect()
top=sw_assembly.new_assembly(sw)
print('top', sw_core.model_title(top))
try:
    c=sw_assembly_full.insert_subassembly(top, sub, x=0.01, y=0, z=0)
    print('inserted', sw_assembly_full._comp_name(c))
    found=sw_assembly_full.find_component(top, sw_assembly_full._comp_name(c))
    print('find', found.Name2)
    print('edit', sw_assembly_full.edit_subassembly(top, found))
    sw_core._dyn(sw).ActivateDoc2(sw_core.model_title(top), False, sw_core.err_variants()[0])
    c2=sw_assembly_full.find_component(top, sw_assembly_full._comp_name(c))
    print('dissolve', sw_assembly_full.dissolve_subassembly(top, c2))
    print('components after', [x.Name2 for x in sw_assembly_full.component_list(top, top_level=False)])
except Exception as e:
    print('ERR', e)
