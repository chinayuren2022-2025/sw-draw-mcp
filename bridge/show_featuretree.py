import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'InsertFeatureTreeFolder' in l or 'FeatureFolderLocation' in l or 'def EditRollback' in l and i>40000:
        print('---',i+1,l[:200])
        for j in range(i, min(len(lines), i+16)):
            print(f'{j+1:5}: {lines[j][:220]}')
