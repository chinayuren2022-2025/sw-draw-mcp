import win32com.client.gencache as gc, glob, os
root=os.path.expanduser(r'C:\Users\ZJULIN\AppData\Local\Temp\gen_py\3.14')
f=[p for p in glob.glob(root+r'\582D0D5B*')][0]
lines=open(f, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if l.startswith('class ') and 'Option' in l:
        print(f'{i+1}: {l[:160]}')
