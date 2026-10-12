# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sel, sw_features
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
sw_core.clear_selection(m)
edges=list(sw_sel._edges(m))
print('edge count', len(edges))
first=True
for e in edges:
    try:
        ok=sw_sel._select_entity(m,e,not first,0)
        if not ok:
            print('failed select edge')
        first=False
    except Exception as ex:
        print('sel err', repr(ex))
        break
print('selected', sw_sel.selected_count(m) if hasattr(sw_sel,'selected_count') else '?')
try:
    f=sw_features.fillet(m,0.002)
    print('fillet ok', f.Name)
except Exception as e:
    print('fillet err', e)
