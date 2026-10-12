import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'def FeatureFillet' in l or 'FeatureFillet3' in l and 'vtable' not in l:
        print('---', i+1, l[:180])
        for j in range(i, min(len(lines), i+22)):
            print(f'{j+1:5}: {lines[j][:230]}')
        print()
