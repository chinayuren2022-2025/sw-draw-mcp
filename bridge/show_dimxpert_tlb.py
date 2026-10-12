import win32com.client.gencache as gc, glob, os
# find generated file
root=os.path.expanduser(r'C:\Users\ZJULIN\AppData\Local\Temp\gen_py\3.14')
f=[p for p in glob.glob(root+r'\582D0D5B*')]
print(f)
if f:
    lines=open(f[0], encoding='utf-8', errors='ignore').read().splitlines()
    for i,l in enumerate(lines):
        if l.startswith('class IDimXpertPart') or 'InsertBasicDimension' in l or 'InsertLocationDimension' in l or 'InsertSizeDimension' in l:
            print('---',i+1,l[:200])
            for j in range(i, min(len(lines), i+30)):
                print(f'{j+1:5}: {lines[j][:220]}')
            print()
