# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_annotate
sw=sw_core.connect()
m=sw_core.open_doc(sw, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\mm25_p1_1.SLDPRT')
m=sw_core._early(m,'IModelDoc2')
try:
    print('counts', sw_annotate.dimxpert_counts(m))
    print('add size', sw_annotate.dimxpert_add_dimension(m, dim_type='size', face_spec={'kind':'cylinder','radius_mm':17.5,'axis':[0,1,0]}))
except Exception as e:
    print('ERR', e)
