import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'def InsertCosmeticThread3' in l:
        print('start', i+1)
        for j in range(i, min(len(lines), i+60)):
            print(f'{j+1:5}: {lines[j][:250]}')
