import win32com.client.gencache as gc, glob, os
root=os.path.expanduser(r'C:\Users\ZJULIN\AppData\Local\Temp\gen_py\3.14')
f=glob.glob(root+r'\4687F359*')[0]
lines=open(f, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'swFeatureFillet' in l:
        print(f'{i+1}: {l[:200]}')
