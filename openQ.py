import numpy as np
import cv2
import fnmatch
import os
import grade_functions
import pandas as pd

class OpenQs(object):
    '''
    a class to store all things regarding open ended questions
    '''
    def __init__(self, image_list):
        #make a dictionary to contains coordinates of boxes
        self.openQcoords = {}

        # create self.openQkeyimgs - a dictionary containing images
        self.openQkey(image_list[0])
        # create list of openQ column names
        cols = ['openQ_' + str(id) for id in range(1, len(self.openQcoords)+1)]
        # initialize a dataFrame to contain results
        #self.openQres = pd.DataFrame('', index = range(len(image_list)), columns = list(range(1,len(self.openQcoords)+1)))
        self.openQres = pd.DataFrame('', index = range(len(image_list)), columns = cols)
        # set the first row (key) all to 'CC'
        self.openQres.loc[0]='CC'
        #load each open ended question, load each image and grade it
        self.seckey = False
        # get keys of openQcoords as list
        openqs = sorted(list(self.openQcoords))
        self.openQidx = 0
        while self.openQidx < len(openqs):
            if self.openQidx < 0:
                self.openQidx = 0
            self.idx = 1
            while self.idx < len(image_list):
                if self.idx < 1:
                    self.idx = 1
                k = openqs[self.openQidx]
                v = self.openQcoords[k]
                self.gradeOpenQs(image_list[self.idx], k, v)
            self.openQidx += 1
        
        
#         for k,v in sorted(self.openQcoords.items()):
#             self.idx = 1
#             while self.idx < len(image_list):
#                 if self.idx < 1:
#                     self.idx = 1
#                 self.gradeOpenQs(image_list[self.idx], k, v)
    
    def openQkey(self, imgpath):
        '''
        opens the key as an image an allows drawing of rectangles
        '''
        #load and resize the image
        img=cv2.imread(imgpath, 1)
        self.dispres = .7
        sz=img.shape
        self.imgopenQ=cv2.resize(img.copy(),
                                (int(self.dispres*sz[1]), int(self.dispres*sz[0])),
                                interpolation=cv2.INTER_AREA)
        self.drawing = False
        cv2.namedWindow('image')
        cv2.setMouseCallback('image', self.makerect)
        cv2.imshow('image',self.imgopenQ)
        self.waitKeyvar=0
        k = cv2.waitKey(self.waitKeyvar) & 0xFF
        if k == ord('g'): # if g is pressed, continue
            #create key images dict
            self.openQkeyimgs = {}
            cv2.destroyAllWindows()            
            for key,v in self.openQcoords.items():     
                self.openQkeyimgs[key]=img.copy()[v[1]:v[3], v[0]:v[2]]

    
    def makerect(self, event, x, y, flags, param):
        '''
        mouse control functions for drawing on key
        '''
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.sx, self.sy = x, y
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing == True:
                img=self.imgopenQ.copy()
                cv2.rectangle(img, (self.sx, self.sy), (x, y), 60, 1)
                cv2.imshow('image', img)
        elif event == cv2.EVENT_LBUTTONUP:
            ex, ey = x, y
            self.drawing = False
            #add coordinates to dictionary
            last=len(self.openQcoords)
            self.openQcoords['openQ_'+ str(last + 1)]=(int(self.sx/self.dispres), int(self.sy/self.dispres), int(ex/self.dispres), int(ey/self.dispres))
            self.drawrects()
            
    def drawrects(self):
        #copy the image again
        img=self.imgopenQ.copy()
        #then draw all rectangles on the image and display
        for k, v in self.openQcoords.items():
            cv2.rectangle(img, (int(self.dispres * v[0]),int(self.dispres * v[1])), 
                        (int(self.dispres*v[2]), int(self.dispres*v[3])), 60, 1)
            cv2.imshow('image', img)
            
    def gradeOpenQs(self, filename, k, v):
        img=cv2.imread(filename, 1)
        self.drawing=False
        self.openQk=k
        #display the image with keyboard shortcuts
        #make an image with the key at the top and the student's answer below
        studentimg=img.copy()[v[1]:v[3], v[0]:v[2]]
        studentimg=np.vstack((self.openQkeyimgs[k], studentimg))
        #display the images
        self.makeOpenQgradingWindow(studentimg, k)            
            
    def makeOpenQgradingWindow(self, img, q):
        cv2.namedWindow('image')
        cv2.imshow('image', img)
        self.waitKeyvar=0
        k = cv2.waitKey(self.waitKeyvar) & 0xFF
        if k == ord('c'): # if c is pressed, mark as correct
            #self.openQgrade['openQ_'+str(self.openQk)]='C'
            if not self.seckey:
                self.openQgrade='C'
                self.seckey = True
            else:
                self.openQgrade = self.openQgrade + 'C'
                self.seckey = False
                self.openQres.loc[self.idx, q] = ''.join(sorted(self.openQgrade))
#                 print(self.openQres)
                self.idx += 1
        if k == ord('x'): #if x is pressed, mark as wrong
            #self.openQgrade['openQ_'+str(self.openQk)]='X'
            if not self.seckey:
                self.openQgrade='X'
                self.seckey = True
            else:
                self.openQgrade = self.openQgrade + 'X'
                self.seckey = False
                self.openQres.loc[self.idx, q] = ''.join(sorted(self.openQgrade)) 
                self.idx += 1 
        if k == ord('b'): #if b is pressed, go back one
            self.idx -= 1
            #if we've gone back to the first image, need to back up to previous question
            if self.idx == 0 and self.openQidx > 0:
                self.openQidx -= 1
                #and set self.idx to the last option to get last picture
                self.idx = len(self.openQres)-1
            self.seckey = False
        
def deleterect(self,x):
    #find last rect coords in self.openQcoords by max key value, and delete it
    if len(self.openQcoords)>0:
        last = len(self.openQcoords)
        del self.openQcoords[last]
        self.drawrects()

def continueButton(self, x):
    self.waitKeyvar = 1
    cv2.destroyAllWindows()


    
  