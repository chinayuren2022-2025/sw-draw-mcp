mods=['pymupdf','cv2','PIL','numpy']
for m in mods:
    try:
        mod=__import__(m)
        print(m,'OK',getattr(mod,'__version__',''))
    except Exception as e:
        print(m,'NO',type(e).__name__,e)
