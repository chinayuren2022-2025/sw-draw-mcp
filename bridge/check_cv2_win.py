import cv2
print('cv2 file', cv2.__file__)
print('version', getattr(cv2,'__version__','?'))
print('has imread', hasattr(cv2,'imread'))
print('attrs sample', [x for x in dir(cv2) if x.startswith('im')][:10])
