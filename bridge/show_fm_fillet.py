import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for j in range(21255,21301):
    print(f'{j+1:5}: {lines[j][:250]}')
