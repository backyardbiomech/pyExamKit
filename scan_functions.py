import itertools
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


# The registration circles as they come out of the resize to canonical width:
# 42 px across at full size. Printers with wide margins shrink the page (85%
# is common), a copier can scan a little large, and blur or heavy toner
# fattens a mark, so the size window is wide; roundness, solidity, matching
# sizes, and the three circles' arrangement are what pick them out.
REG_AREA = np.pi * 21 ** 2
REG_AREA_RANGE = (0.45, 1.6)        # fraction of REG_AREA: about 67% to 125% scale
REG_MIN_SOLIDITY = 0.65             # blob area / bounding box; a disk is 0.785


def _order_reg(pts):
    """Sort three (x, y) points as [bottom-right, bottom-left, top-right]."""
    pts = list(pts)
    br = max(pts, key=lambda t: t[0] + t[1])
    pts.remove(br)
    bl = min(pts, key=lambda p: p[0])
    pts.remove(bl)
    return [br, bl, pts[0]]


def _arrangement_error(pts, expected) -> float:
    """
    How far three ordered points are from the expected right triangle of
    circles, whatever the scale: side-length ratios and the right angle.
    """
    br, bl, tr = (np.asarray(p, float) for p in pts)
    ebr, ebl, etr = expected
    base, rise = np.linalg.norm(bl - br), np.linalg.norm(tr - br)
    if base == 0 or rise == 0:
        return np.inf
    want = np.linalg.norm(ebl - ebr) / np.linalg.norm(etr - ebr)
    cos = abs(np.dot(bl - br, tr - br)) / (base * rise)
    return abs(base / rise - want) / want + cos


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

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8)
    lo, hi = (REG_AREA * f for f in REG_AREA_RANGE)
    cands = []
    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if h == 0 or not lo <= area <= hi or not 0.833 <= w / h <= 1.2:
            continue
        if area / (w * h) < REG_MIN_SOLIDITY:
            continue
        cands.append((float(area), tuple(centroids[i])))
    cands = sorted(cands, reverse=True)[:8]

    if len(cands) < 3:
        raise ValueError(
            f'getRegPts: only {len(cands)} registration dot(s) found. '
            'Ensure the scan is well-lit and all three corner dots are visible.'
        )

    # The best triple: similar sizes, laid out like the printed circles
    expected = np.asarray(scan_settings.keyRegPts, float)
    best, best_err = None, np.inf
    for trio in itertools.combinations(cands, 3):
        areas = [a for a, _ in trio]
        spread = (max(areas) - min(areas)) / max(areas)
        pts = _order_reg([c for _, c in trio])
        err = _arrangement_error(pts, expected) + spread
        if err < best_err:
            best, best_err = pts, err
    if best_err > 0.3:
        raise ValueError(
            'getRegPts: no three dots are laid out like the registration circles. '
            'Ensure the scan is well-lit and all three corner dots are visible.'
        )
    return np.array(best, dtype=np.float32)


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
