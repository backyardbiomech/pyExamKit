import numpy as np
import fnmatch
import os
import cv2
import grade_functions
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


def autothresh(aligned_img, scan_settings):
    '''
    Auto-threshold the aligned image based on calibration box medians.
    aligned_img: RGB uint8 ndarray
    Returns binary uint8 ndarray (0/255) where 255 = filled region.
    '''
    gray = _rgb2gray_u8(aligned_img)
    blurred = cv2.medianBlur(gray, 15)

    threshdict = scan_settings.threshdict
    threshvals = np.full(4, np.nan)
    for j in range(1, 5):
        keyName = 'thresh' + format(j, '02d')
        startX, startY = threshdict[keyName][0]
        endX, endY = threshdict[keyName][1]
        patch = blurred[startY:endY, startX:endX]
        threshvals[j - 1] = np.median(patch)

    v = np.median(threshvals)
    thresh = int(v * (1 - scan_settings.sigma))
    # THRESH_BINARY_INV: pixels darker than thresh become foreground (filled
    # regions). Kept as a plain numpy compare rather than cv2.threshold,
    # since THRESH_BINARY_INV treats pixels equal to thresh as foreground
    # (<=) where the original code used a strict <.
    mask = (blurred < thresh).astype(np.uint8) * 255

    kern_shape = scan_settings.kern.shape
    struct = cv2.getStructuringElement(cv2.MORPH_RECT, kern_shape)
    eroded = cv2.erode(mask, struct, iterations=3)
    dilated = cv2.dilate(eroded, struct, iterations=3)
    return dilated


def scanDots(img, areaDict, ignores, convDict):
    '''
    Scan an aligned, thresholded image in the areas of areaDict.
    img: binary uint8 ndarray (0/255) or bool from autothresh
    Returns a dictionary of results keyed by area name.
    '''
    binary_img = (img > 0).astype(np.uint8) * 255

    resDict = dict.fromkeys(areaDict, '-')

    for k, v in sorted(areaDict.items()):
        if k[0] == 'Q':
            if ignores and int(k[1:]) in ignores:
                resDict[k] = 'ignore'
                continue
        pt1, pt2 = v[0], v[1]
        # Extract region; numpy indexing is [rows, cols] = [y, x]
        scanArea = np.ascontiguousarray(binary_img[pt1[1]:pt2[1], pt1[0]:pt2[0]])

        # Label connected components; filter out tiny regions (area < 10)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            scanArea, connectivity=8)
        regions = [i for i in range(1, num_labels)
                   if stats[i, cv2.CC_STAT_AREA] >= 10]

        if not regions:
            resDict[k] = '-'
        elif k[0] == 'Q':
            resDict[k] = ''

        for i in regions:
            x, y, w, h, area = stats[i]

            if k[0] == 'F':
                for lett, coord in convDict.items():
                    if x < coord < x + w and h > 10:
                        resDict[k] = lett
            if k[0] == 'N':
                for lett, coord in convDict.items():
                    if x < coord < x + w and h > 10:
                        resDict[k] = lett
            if k[0] == 'I':
                for lett, coord in convDict.items():
                    if y < coord < y + h and w > 10:
                        resDict[k] = lett
            if k[0] == 'Q':
                for lett, coord in convDict.items():
                    if x < coord < x + w and h > 10:
                        if lett not in resDict[k]:
                            resDict[k] = ''.join(sorted(resDict[k] + lett))
            if len(resDict[k]) == 0:
                resDict[k] = '-'
            # Fix odd behavior: remove '-' if uppercase letters are also present
            if '-' in resDict[k] and resDict[k].isupper():
                resDict[k] = resDict[k].replace('-', '')

    return resDict


def saveimg(i, scanimg, aligneddir):
    if not aligneddir.is_dir():
        aligneddir.mkdir()
    savename = str(aligneddir / 'aligned_{:03d}.jpg'.format(i))
    # scanimg is a RGB uint8 ndarray
    PILImage.fromarray(scanimg).save(savename, quality=95)


def rundots(img, qAreas, idAreas, nAreas, ignores, Qdict, Idict, Ndict):
    '''
    Scans the thresholded image for all bubble areas.
    Returns a dictionary ready to be added to the main results dataframe.
    '''
    qRes = scanDots(img, qAreas, ignores, Qdict)
    idRes = scanDots(img, idAreas, ignores, Idict)
    nRes = scanDots(img, nAreas, ignores, Ndict)
    lastName, firstName, studentID = grade_functions.getid(idRes, nRes)
    qRes['LastName'] = lastName
    qRes['FirstName'] = firstName
    qRes['studentID'] = studentID
    return qRes


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
