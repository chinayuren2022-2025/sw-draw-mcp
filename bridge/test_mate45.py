# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_assembly, sw_assembly_full
BLOCK=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\asm_block.SLDPRT'
sw=sw_core.connect()
asm=sw_assembly.new_assembly(sw)
c1=sw_assembly_full.insert_component_full(asm, BLOCK)
c2=sw_assembly_full.insert_component_full(asm, BLOCK, x=0.021)
f1=sw_assembly.find_face(c1, kind='plane', normal=[1,0,0])[0]
f2=sw_assembly.find_face(c2, kind='plane', normal=[-1,0,0])[0]
try:
    mate,err=sw_assembly_full.add_mate_full(asm, f1, f2, 'coincident', lock_rotation=True, width_option=0)
    print('mate', mate.Name if hasattr(mate,'Name') else mate, 'err', err)
    print('mates', sw_assembly_full.list_mates(asm))
except Exception as e:
    print('ERR', repr(e)[:300])
