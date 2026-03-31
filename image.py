import numpy as np
from PIL import Image as PILImage

import scan_functions


class Image(object):
    '''
    image object, most important values are:
    Image.aligned is the sized and aligned image (RGB uint8 ndarray) to copy and mark
    Image.scanimg is the binary uint8 ndarray (0/255) ready for bubble scanning
    '''
    def __init__(self, fname, scan_settings):
        # Load as RGB
        pil = PILImage.open(fname).convert('RGB')
        self.img = np.array(pil)      # (H, W, 3) uint8 RGB
        H, W = self.img.shape[:2]

        # Resize so width matches the canonical width (scan_settings.sz[1] = 1224)
        target_cols = scan_settings.sz[1]
        resizefactor = target_cols / W
        new_W = int(resizefactor * W)
        new_H = int(resizefactor * H)
        imgsized = np.array(pil.resize((new_W, new_H), PILImage.LANCZOS))

        # Find the three registration dots (returns (3,2) float32 array of (x,y) pairs)
        self.regPts = scan_functions.getRegPts(imgsized, scan_settings)
        # Affine-align to the canonical template; output shape = scan_settings.sz
        self.aligned = scan_functions.imgReg(imgsized, self.regPts, scan_settings)
        # Threshold the aligned image to produce the binary scan image
        self.scanimg = scan_functions.autothresh(self.aligned.copy(), scan_settings)
