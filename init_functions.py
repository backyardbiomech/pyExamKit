import numpy as np
import cv2
import os
import fnmatch
import pandas as pd


def filenames(input_file):
    #get the name of the file
    basename = input_file.split('.')[0] #includes full path, not extension
    ext = input_file.split('.')[1] #extension
    pathname = basename.rsplit('/',1)[0]+'/' #just the path to the directory

    # open a pdf file containing all of the scans and make jpegs
    if ext == 'pdf':
        # write the jpgs, and change input_file to name of key jpg
        input_file = splitpdf(input_file)
       
    # create list of files beginning with key   
    image_list = [input_file] 
    #for all the files in the current directory
    for file in os.listdir(pathname):
        # if the file is a jpg and not the key
        if ((fnmatch.fnmatch(file, '*.jpg') or fnmatch.fnmatch(file,'*.jpeg')) and not 
                fnmatch.fnmatch(pathname+file,input_file)):
            # add the path to the file
            image_list.append(pathname+file)
    #make a new directory that will contain all of the outputs  
#     if not os.path.isdir(basename + '_marked'):
#         os.mkdir(basename + '_marked')
    return pathname, image_list
    
def splitpdf(input_file):
    '''
    takes in a pdf file, splits it out to jpgs in same directory, with same base name
    '''
    basename = input_file.split('.')[0] #includes full path, not extension
    pathname = basename.rsplit('/',1)[0]+'/' #just the path to the directory
    pdf = open(input_file, 'rb').read()
    # find the image in the pdf
    #stuff about bytes
    startmark = b"\xff\xd8"
    startfix = 0
    endmark = b"\xff\xd9"
    endfix = 2
    i = 0
    njpg = 0
    while True:
        #find the next image in the pdf
        istream = pdf.find(b"stream", i)
        if istream < 0:
            break
        istart = pdf.find(startmark, istream, istream+20)
        if istart < 0:
            i = istream+20
            continue
        iend = pdf.find(b"endstream", istart)
        if iend < 0:
            raise Exception("Didn't find end of stream!")
        iend = pdf.find(endmark, iend-20)
        if iend < 0:
            raise Exception("Didn't find end of JPG!")
        istart += startfix
        iend += endfix
        #extract the image bytes
        jpg = pdf[istart:iend]
        #convert image bytes to image array
        nparr = np.fromstring(jpg, np.uint8)
        jpg_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        #save jpg
        savename=basename + '_scan_'+'{0:03d}'.format(njpg)+'.jpg'
        cv2.imwrite(savename, jpg_np)
        if njpg == 0:
            key = savename
        njpg += 1
        i = iend
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
    resdf = pd.DataFrame(0, index=range(scans),columns=cols)
    return resdf