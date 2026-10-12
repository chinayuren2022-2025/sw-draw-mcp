import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
p=mod.__file__
lines=open(p, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if any(k in l for k in ('def DimXpertManager','def InsertCosmeticThread','def EditRollback','def ReorderFeature','class IDimXpertManager','def AddRenderMaterial','def SetMaterialPropertyValues')):
        print('---',i+1,l[:220])
        for j in range(i, min(len(lines), i+28)):
            print(f'{j+1:5}: {lines[j][:220]}')
        print()
