# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core
sw = sw_core.connect()
print('SW dir:')
for x in dir(sw):
    if any(k in x.lower() for k in ('process','window','frame','main','handle','hwnd','active','doc')):
        print(' ', x)
print('model dir:')
for x in dir(sw_core._dyn(sw.ActiveDoc)):
    if any(k in x.lower() for k in ('process','window','frame','main','handle','hwnd','active','view','orientation')):
        print(' ', x)
