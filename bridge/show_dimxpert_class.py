import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if l.startswith('class IDimXpertManager'):
        print('start', i+1)
        for j in range(i, min(len(lines), i+220)):
            print(f'{j+1:5}: {lines[j][:230]}')
        break
