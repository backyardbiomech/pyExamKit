import numpy as np
import fnmatch
import os
import cv2
from pathlib import Path
from PIL import Image as PILImage


def _rgb2gray_u8(img):
    '''
    Grayscale conversion matching skimage.color.rgb2gray's ITU-R 601-2 weights
    (0.2125 R + 0.7154 G + 0.0721 B), then truncated to uint8 the way the old
    code did with `(rgb2gray(img) * 255).astype(np.uint8)`. cv2.cvtColor's
    default RGB2GRAY uses different (BT.601 luma) weights, which would shift
    every threshold decision downstream, so this stays hand-rolled.
    '''
    coeffs = np.array([0.2125, 0.7154, 0.0721], dtype=np.float64)
    gray = img.astype(np.float64) @ coeffs
    return gray.astype(np.uint8)


def imgReg(img, regPts, scan_settings):
    '''
    Align image with registration coordinates using affine transform.
    img: RGB uint8 ndarray
    regPts: (3,2) float64 array of (x,y) positions found in the scan
    Returns RGB uint8 ndarray aligned to the canonical template size.
    '''
    # M maps canonical template points -> points found in the scan, i.e. it is
    # already the output-to-input map that warpAffine needs, so it must be
    # passed with WARP_INVERSE_MAP rather than inverted again.
    M = cv2.getAffineTransform(
        scan_settings.keyRegPts.astype(np.float32),
        regPts.astype(np.float32),
    )
    img_aligned = cv2.warpAffine(
        img, M, (scan_settings.sz[1], scan_settings.sz[0]),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return img_aligned.astype(np.uint8)


def getRegPts(img, scan_settings):
    '''
    Find the three registration points in a (resized, not yet aligned) image.
    img: RGB uint8 ndarray
    Returns (3,2) float32 array of (x,y) centroids, sorted [br, bl, tr].
    '''
    # Grayscale → median blur → threshold
    gray = _rgb2gray_u8(img)
    blurred = cv2.medianBlur(gray, 7)
    # THRESH_BINARY_INV equivalent: dark dots become foreground
    mask = (blurred < scan_settings.volthresh).astype(np.uint8) * 255

    # Label connected components and sort by area descending
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8)
    regions = sorted(range(1, num_labels),
                      key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)

    pts = []
    for i in regions:
        x, y, w, h, area = stats[i]
        if h == 0:
            continue
        ar = w / h
        if ar > 1.2 or ar < 0.833:
            continue
        if (area > int(scan_settings.sz[1] * 1.2) or
                area < int(scan_settings.sz[1] * 0.8)):
            continue
        cx, cy = centroids[i]
        pts.append((cx, cy))
        if len(pts) == 3:
            break

    if len(pts) < 3:
        raise ValueError(
            f'getRegPts: only {len(pts)} registration dot(s) found. '
            'Ensure the scan is well-lit and all three corner dots are visible.'
        )

    # Sort: bottom-right (max x+y), bottom-left (min x), top-right (remaining)
    bridx = np.argmax([t[0] + t[1] for t in pts])
    br = pts[bridx]
    del pts[bridx]
    bl = min(pts, key=lambda p: p[0])
    pts.remove(bl)
    tr = pts[0]
    pts = [br, bl, tr]
    return np.array(pts, dtype=np.float32)


def saveimg(i, scanimg, aligneddir):
    if not aligneddir.is_dir():
        aligneddir.mkdir()
    savename = str(aligneddir / 'aligned_{:03d}.jpg'.format(i))
    # scanimg is a RGB uint8 ndarray
    PILImage.fromarray(scanimg).save(savename, quality=95)


def savePdf(markeddir, outpdf, keyname):
    '''Assemble all marked JPEGs into the given FPDF object.
    keyname may be None when using a key file (no key scan image).
    '''
    filelist = []
    if keyname is not None:
        filelist.append(str(keyname))
    key_name_str = keyname.name if keyname is not None else None
    student_pages = []
    for file in os.listdir(str(markeddir)):
        if fnmatch.fnmatch(file, '*.jpg'):
            if key_name_str is None or not fnmatch.fnmatch(file, key_name_str):
                student_pages.append(str(markeddir / file))
    filelist.extend(sorted(student_pages))
    for page in filelist:
        outpdf.add_page()
        outpdf.image(page, 0, 0, 612)
