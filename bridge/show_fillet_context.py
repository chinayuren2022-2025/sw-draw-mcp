import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
targets=[21256,21266,21278,31208,31214,31221,31228,35329,35335,35342,35349]
for t in targets:
    idx=t-1
    # find class line above
    cls=None
    for j in range(idx, -1, -1):
        if lines[j].startswith('class '):
            cls=lines[j]; break
    print(f'{t}: {cls} :: {lines[idx][:180]}')
