import win32com.client.gencache as gc
mod=gc.GetModuleForProgID('SldWorks.Application')
lines=open(mod.__file__, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'swFeatureFilletType' in l or 'swFeatureFilletOptions' in l or 'swFeatureFilletUniformRadius' in l:
        print(f'{i+1}: {l[:220]}')
