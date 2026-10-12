import win32com.client, win32com.client.gencache as gc, glob, os
try:
    mod=gc.GetModuleForProgID('SldWorks.Application')
    p=getattr(mod,'__file__',None)
    print('module file', p)
except Exception as e:
    print('gencache err', e)
    p=None
if p:
    root=os.path.dirname(os.path.dirname(os.path.dirname(p)))
    for f in glob.glob(os.path.join(root,'**','*.py'), recursive=True):
        try:
            s=open(f, encoding='utf-8', errors='ignore').read()
            if 'DimXpertManager' in s or 'InsertCosmeticThread' in s or 'EditRollback' in s:
                print('====',f,'====')
                for line in s.splitlines():
                    if any(k in line for k in ('DimXpertManager','InsertCosmeticThread','EditRollback','ReorderFeature')):
                        print(line[:300])
        except Exception:
            pass
