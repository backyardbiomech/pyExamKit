import numpy as np
import fnmatch
import os
import grade_functions
from pathlib import Path
from PIL import Image as PILImage
from scipy.ndimage import median_filter, binary_erosion, binary_dilation
from skimage.measure import label, regionprops
from skimage.transform import warp, AffineTransform
from skimage.color import rgb2gray


def imgReg(img, regPts, scan_settings):
    '''
    Align image with registration coordinates using affine transform.
    img: RGB uint8 ndarray
    regPts: (3,2) float64 array of (x,y) positions found in the scan
    Returns RGB uint8 ndarray aligned to the canonical template size.
    '''
    tform = AffineTransform.from_estimate(
        scan_settings.keyRegPts.astype(np.float64),
        regPts.astype(np.float64),
    )
    img_aligned = warp(img, tform,
                       output_shape=scan_settings.sz,
                       order=1,
                       preserve_range=True,
                       mode='constant',
                       cval=255.0)
    return img_aligned.astype(np.uint8)


def getRegPts(img, scan_settings):
    '''
    Find the three registration points in a (resized, not yet aligned) image.
    img: RGB uint8 ndarray
    Returns (3,2) float32 array of (x,y) centroids, sorted [br, bl, tr].
    '''
    # Grayscale → median blur → threshold
    gray = (rgb2gray(img) * 255).astype(np.uint8)
    blurred = median_filter(gray, size=7)
    # THRESH_BINARY_INV equivalent: dark dots become True
    binary = blurred < scan_settings.volthresh

    # Label connected components and sort by area descending
    labeled = label(binary, connectivity=2)
    props = sorted(regionprops(labeled), key=lambda r: r.area, reverse=True)

    pts = []
    for region in props:
        min_row, min_col, max_row, max_col = region.bbox
        h = max_row - min_row
        w = max_col - min_col
        if h == 0:
            continue
        ar = w / h
        if ar > 1.2 or ar < 0.833:
            continue
        area = region.area
        if (area > int(scan_settings.sz[1] * 1.2) or
                area < int(scan_settings.sz[1] * 0.8)):
            continue
        # centroid is (row, col); convert to float (x=col, y=row)
        cy, cx = region.centroid
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
    gray = (rgb2gray(aligned_img) * 255).astype(np.uint8)
    blurred = median_filter(gray, size=15)

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
    # THRESH_BINARY_INV: pixels darker than thresh become True (filled regions)
    binary = blurred < thresh

    kern_shape = scan_settings.kern.shape
    struct = np.ones(kern_shape, dtype=bool)
    eroded = binary_erosion(binary, structure=struct, iterations=3)
    dilated = binary_dilation(eroded, structure=struct, iterations=3)
    return dilated.astype(np.uint8) * 255


def scanDots(img, areaDict, ignores, convDict):
    '''
    Scan an aligned, thresholded image in the areas of areaDict.
    img: binary uint8 ndarray (0/255) or bool from autothresh
    Returns a dictionary of results keyed by area name.
    '''
    binary_img = img > 0

    resDict = dict.fromkeys(areaDict, '-')

    for k, v in sorted(areaDict.items()):
        if k[0] == 'Q':
            if ignores and int(k[1:]) in ignores:
                resDict[k] = 'ignore'
                continue
        pt1, pt2 = v[0], v[1]
        # Extract region; numpy indexing is [rows, cols] = [y, x]
        scanArea = binary_img[pt1[1]:pt2[1], pt1[0]:pt2[0]]

        # Label connected components; filter out tiny regions (area < 10)
        labeled = label(scanArea, connectivity=2)
        props = [r for r in regionprops(labeled) if r.area >= 10]

        if not props:
            resDict[k] = '-'
        elif k[0] == 'Q':
            resDict[k] = ''

        for region in props:
            min_row, min_col, max_row, max_col = region.bbox
            w = max_col - min_col   # horizontal extent (x direction)
            h = max_row - min_row   # vertical extent  (y direction)
            x = min_col             # left edge (x)
            y = min_row             # top edge  (y)

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

