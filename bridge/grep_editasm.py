import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'EditAssembly' in l or 'EscapeEdit' in l or 'LeaveEdit' in l:
        print(f'{i+1}: {l[:220]}')
