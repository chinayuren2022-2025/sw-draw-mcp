import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'DimXpertPart' in l or 'DimXpertFeature' in l or 'DimXpertDimension' in l:
        print(f'{i+1}: {l[:200]}')
