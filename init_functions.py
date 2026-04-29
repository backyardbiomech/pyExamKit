import os
import fnmatch
import pandas as pd
import fitz  # pymupdf
from pathlib import Path


def filenames(input_file, scan_jpgs_dir=None):
    #Get the file path as a Path object
    filename=Path(input_file)
    #Get the extension
    ext = filename.suffix
    #Get the path to the current directory
    pathname = filename.parent
    # Get the name of the file
    basename = filename.stem

    # open a pdf file containing all of the scans and make jpegs
    if ext.lower() == '.pdf': 
        # write the jpgs, and change input_file to name of key jpg
        input_file = splitpdf(input_file, scan_jpgs_dir=scan_jpgs_dir)
        #Get the file path as a Path object
        filename=Path(input_file)
        #Get the path to the current directory
        pathname = filename.parent

    image_list=[]
    # create list of files beginning with key   
    image_list.append(input_file)
    #for all the files in the current directory
    for file in sorted(os.listdir(str(pathname))):
        # if the file is a jpg and not the key
        if ((fnmatch.fnmatch(file, '*.jpg') or fnmatch.fnmatch(file,'*.jpeg')) and not 
                fnmatch.fnmatch(str(pathname / file),input_file)):
            # add the path to the file
            image_list.append(str(pathname / file))
    #make a new directory that will contain all of the outputs  
#     if not os.path.isdir(basename + '_marked'):
#         os.mkdir(basename + '_marked')
    return image_list
    
def splitpdf(input_file, scan_jpgs_dir=None):
    '''
    Takes a PDF file and renders each page as a JPEG in a scanJPGs subfolder.
    Uses pymupdf (fitz) so it works with any PDF image format (JPEG, PNG, JBIG2, etc.)
    Returns the path to the first image (the key).
    '''
    filename = Path(input_file)
    pathname = filename.parent
    jpgdir = Path(scan_jpgs_dir) if scan_jpgs_dir else pathname / 'scanJPGs'
    jpgdir.mkdir(parents=True, exist_ok=True)

    # Clear stale JPEGs from previous runs before writing new ones
    for old_file in jpgdir.glob('*.jpg'):
        old_file.unlink()

    doc = fitz.open(str(filename))
    key = None
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render at 200 dpi (scale factor: 200/72 ≈ 2.78)
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        savename = str(jpgdir / '_scan_{:03d}.jpg'.format(page_num))
        pix.save(savename)
        if page_num == 0:
            key = savename
    doc.close()
    return key
    
def makeAreaDict(quests):
    '''
    define dictionary containing search area for all 150 questions, names, and ID numbers
    keys that start with F are first names, N are last names, 
    ID are ID numbers, and Q are questions
    3 first and 5 last name boxes
    '''
    nAreas = {}
    idAreas = {}
    qAreas = {}
    # First names
    NX=124
    NY=268
    nameWidth=676
    namegap = 2
    for i in range(1,4):
        keyName = 'F' + str(i) 
        startX=NX
        startY=NY+(i-1)*(26+ namegap)
        endX=startX+nameWidth
        endY=startY+20
        nAreas[keyName] = (startX,startY), (endX, endY)

    # Last names
    NX=124
    NY=400
    nameWidth=676
    namegap = 2
    for i in range(1,6):
        keyName = 'N' + str(i) 
        startX=NX
        startY=NY+(i-1)*(26+ namegap)
        endX=startX+nameWidth
        endY=startY+20
        nAreas[keyName] = (startX,startY), (endX, endY)

    # ID number boxes
    IDX = 874
    IDY = 273
    IDheight = 260
    IDgap = 2
    for i in range (1, 9):
        keyName = 'ID' + format(i,'02d')
        startX=IDX+(i-1)*(28+IDgap)
        startY= IDY
        endX=startX+28
        endY= startY + IDheight
        idAreas[keyName] = (startX,startY), (endX, endY)
    
    # Questions
    QX = 126
    QY = 595
    Qwidth = 160
    Qgap = 2
    for i in range(1, quests+1):
        keyName = 'Q' + format(i, '03d')
        if i < 16:
            startY=QY+((28+Qgap) * (i - 1))
        elif i < 31:
            QY = 1046
            startY=QY+((28+Qgap) * (i - 16))
        elif i < 46:
            QX = 338
            QY = 595
            startY=QY+((28+Qgap) * (i - 31))
        elif i < 61:
            QY = 1046
            startY=QY+((28+Qgap) * (i - 46))
        elif i < 76:
            QX = 550
            QY = 595
            startY=QY+((28+Qgap) * (i - 61))
        elif i < 91:
            QY = 1046
            startY=QY+((28+Qgap) * (i - 76))
        elif i < 106:
            QX = 762
            QY = 595
            startY=QY+((28+Qgap) * (i - 91))
        elif i < 121:
            QY = 1046
            startY=QY+((28+Qgap) * (i - 106))
        elif i < 136:
            QX = 976
            QY = 595
            startY=QY+((28+Qgap) * (i - 121))
        else:
            QY = 1046
            startY=QY+((28+Qgap) * (i - 136))
        endY=startY+26
        qAreas[keyName] = (QX, startY), (QX + Qwidth, endY)       
    return qAreas, idAreas, nAreas
    
def makeResDict():
    #build dictionaries to convert coordinates to letters and numbers
    #for the name
    Ndict={}
    for i in range(0,26):
        coord = ((i+1)*26)-12
        lett=chr(i + ord('A'))
        Ndict[lett]=coord
    #for the ID number
    Idict={}
    for i in range(0,10):
        coord = ((i+1)*26)-12
        numb = str(i)
        Idict[numb]=coord
    #for the questions
    Qdict={}
    for i in range(0,6):
        coord = ((i+1)*26)-12
        lett=chr(i + ord('A'))
        Qdict[lett]=coord
    #cover blank answers
    Qdict['-'] = 0
    return Ndict, Idict, Qdict
    
def makeResDf(quests, scans):
    # initialize the pandas dataframe to contain results
    cols=['LastName','FirstName','studentID']
    for i in range(1,(quests)+1):
        foo = 'Q' + format(i,'03d')
        cols.append(foo)
    resdf = pd.DataFrame('', index=range(scans), columns=cols)
    return resdf