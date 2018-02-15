from fpdf import FPDF
import sys
import os
import fnmatch
import pandas as pd
import numpy as np
import ast
from PIL import Image, ImageDraw
import PIL

from dicts import Dicts
from settings import Settings
#from image import Image
import init_functions
#import scan_functions
#import grade_functions
#from openQ import OpenQs


class KeyMaker(object):
    '''
    KeyMaker takes in a csv of anwers and an image file for the key and outputs a filled in answer key
    '''
    
    def __init__(self, keyImg, keyFile, keyVersion):
        '''
        retrieve values from the gui (or call from command line)
        keyImg is path to a jpg of the answer sheet
        keyFile is the path to a CSV of the answers
        keyVersion is 'A', 'B', 'C'... as the version of the answer sheet. Defaults to 'A'
        '''
        self.keyImg = keyImg
        self.keyFile = keyFile
        self.keyVersion = keyVersion
        # pull settings into keymaker object
        self.scan_settings=Settings()
        #self.scan_settings.sigma = thresh
        # initialize file and pathnames (and split pdfs into jpgs)
        self.path, self.image_list = init_functions.filenames(self.keyImg)
        # intialize the output pdf which the scanner object will write to
        self.outpdf=FPDF('P','pt','Letter')
        # initialize the pandas dataframe to contain results
        #self.resdf = init_functions.makeResDf(quests, len(self.image_list))
        # make the dictionaries containing scanning coordinates
        #self.qAreas, self.idAreas, self.nAreas = init_functions.makeAreaDict(150)
        # make the dictionaries to convert coordinates to letters or numbers
        self.Ndict, self.Idict, self.Qdict = init_functions.makeResDict()
        self.run()
    
   
        
    def run(self):
        # load the files
        img = Image.open(self.keyImg, 'r')
        df = pd.read_csv(self.keyFile, header = None)
        ver = self.keyVersion
        
        #make dictionary of locations for the center point of each letter in each question area
        #the coordinate should be the left boundary of the bubble
        Qdict={}
        for i in range(0,6):
            coord = i*26
            lett=chr(i + ord('A'))
            Qdict[lett]=coord
        #make a dictionary of question names and answer values from the df
        self.keyDict={}
        for row in df.index:
            qstr= 'Q' + format(row+1, '03d')
            self.keyDict[qstr] = df.loc[row][0]
        self.makeAreas()
        
        # output file name
        outname = self.path + 'Key_ver' + ver + '.jpg'
        #resize the image
        width=1224
        wpercent = width/img.size[0]
        height = int((float(img.size[1]) * float(wpercent)))
        img = img.resize((width, height), PIL.Image.ANTIALIAS)
        
        verDict={'A':(122,262), 'B':(148,262),'C':(176,262),'D':(202,262)}
        #copy the image for drawing
        img2=img.copy()
        #draw on the image
        draw = ImageDraw.Draw(img2)
        for k, v in self.areaDict.items():
            #get the key answers for question k
            ans = self.keyDict[k]
            if ans == 'IGNORE'or ans == '-':
                continue
            for a in list(ans):
                #print(v[0])
                st=(v[0][0]+Qdict[a]+4,v[0][1]+2)
                en=(v[0][0]+Qdict[a]+26, v[0][1]+24)
                draw.ellipse([st,en], fill= 'black')
        #mark the last name as KEY, first name as version
        st=[(385,395),(228,422), (748,454),verDict[ver]]
        for mark in st:
            draw.ellipse([mark, (mark[0]+24, mark[1]+24)], fill = 'black')
        #save the image
        img2.save(outname)
        
    def makeAreas(self):
        # make a dictionary containing the location of all of the questions#first column first 15
        self.areaDict={}    
        QX = 122
        QY = 595
        Qwidth = 160
        Qgap = 2
        for i in range(1,151):
            if i > len(self.keyDict):
                break
            keyName = 'Q' + format(i, '03d')
            if i < 16:
                startY=QY+((28+Qgap) * (i - 1))
            elif i < 31:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 16))
            elif i < 46:
                QX = 334
                QY = 595
                startY=QY+((28+Qgap) * (i - 31))
            elif i < 61:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 46))
            elif i < 76:
                QX = 544
                QY = 595
                startY=QY+((28+Qgap) * (i - 61))
            elif i < 91:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 76))
            elif i < 106:
                QX = 758
                QY = 595
                startY=QY+((28+Qgap) * (i - 91))
            elif i < 121:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 106))
            elif i < 136:
                QX = 972
                QY = 595
                startY=QY+((28+Qgap) * (i - 121))
            else:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 136))
            endY=startY+26
            self.areaDict[keyName] = (QX, startY), (QX + Qwidth, endY)
        



