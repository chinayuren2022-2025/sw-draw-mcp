import win32com.client.gencache as gc, glob, os
root=os.path.expanduser(r'C:\Users\ZJULIN\AppData\Local\Temp\gen_py\3.14')
f=[p for p in glob.glob(root+r'\582D0D5B*')][0]
lines=open(f, encoding='utf-8', errors='ignore').read().splitlines()
for i,l in enumerate(lines):
    if 'A69FE92A' in l and 'class' in l:
        print('--- class around', i+1)
        for j in range(i, min(len(lines), i+120)):
            print(f'{j+1:5}: {lines[j][:230]}')
        break
