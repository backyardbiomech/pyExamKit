import numpy as np
import cv2
import fnmatch
import os
import df_functions
import pandas as pd

class OpenQs(object):
    '''
    a class to store all things regarding open ended questions
    '''
    def __init__(self, image_list):
        #make a dictionary to contains coordinates of boxes
        self.openQcoords = {}
        self.openQres = pd.DataFrame(np.nan)
        #load the first image (key), draw boxes, save images
        #creates self.openQkeyimgs - a dictionary containing images
        self.openQkey(image_list[0])

        #load each open ended question, load each image and grade it
        #self.back = False
        self.seckey = False
        for k,v in self.openQcoords.items():
            self.idx = 1
            while:
                #if self.back = False and not self.seckey:
                #    self.idx += 1
                if self.idx < 1:
                    self.idx = 1
                if self.idx > len(image_list):
                    break
                self.gradeOpenQs(image_list[self.idx], k, v)
        # just created self.openQres, a dataframe containing results
        # for each image, self.idx is row number for results data frame
        #return self.openQres
    
    def openQkey(self, imgpath):
    '''
    opens the key as an image an allows drawing of rectangles
    '''
        #load and resize the image
        img=cv2.imread(imgpath, 1)
        self.dispres = .7
        sz=img.shape
        self.imgopenQ=cv2.resize(img.copy(),
                                (int(.7*sz[1]), int(.7*sz[0])),
                                interpolation=cv2.INTER_AREA)
        self.drawing = False
        cv2.namedWindow('image')
        cv2.setMouseCallback('image', self.makerect)
        cv2.imshow('image',self.imgopenQ)
        self.waitKeyvar=0
        k = cv2.waitKey(self.waitKeyvar) & 0xFF
        if k == ord('g'): # if g is pressed, continue
            cv2.destroyAllWindows()            
            for k,v in self.openQcoords.items():
                self.openQkeyimgs[k]=self.img2orig.copy()[v[1]:v[3], v[0]:v[2]]

    
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
            self.openQcoords[last+1]=(int(self.sx/self.dispres), int(self.sy/self.dispres), int(ex/self.dispres), int(ey/self.dispres))
            self.drawrects()
            
    def drawrects(self):
        #copy the image again
        img=self.imgopenQ.copy()
        #then draw all rectangles on the image and display
        for k, v in self.openQcoords.items():
            cv2.rectangle(img, (int(self.dispres * v[0]),int(self.dispres * v[1])), 
                        (int(self.dispres*v[2]), int(self.dispres*v[3])), 60, 1)
            cv2.imshow('image', img)
            
    def gradeOpenQs(self,filename, k, v):
        img=cv2.imread(filename, 1)
        self.drawing=False
        self.openQk=k
        #display the image with keyboard shortcuts
        #make an image with the key at the top and the student's answer below
        studentimg=img.copy()[v[1]:v[3], v[0]:v[2]]
        studentimg=np.vstack((self.openQkeyimgs[k], studentimg))
        #display the images
        self.makeOpenQgradingWindow(studentimg)
        # self.resdf['openQ_' + str(k)].loc[i]=self.openQgrade

       # cv2.imwrite(filename, img)            
            
    def makeOpenQgradingWindow(self, img):
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
                self.openQres['openQ_' + str(k)].loc[self.idx]=self.openQgrade
                self.idx += 1
            self.back = False
        if k == ord('x'): #if x is pressed, mark as wrong
            #self.openQgrade['openQ_'+str(self.openQk)]='X'
            if not self.seckey:
                self.openQgrade='X'
                self.seckey = True
            else:
                self.openQgrade = self.openQgrade + 'X'
                self.seckey = False
                self.openQres['openQ_' + str(k)].loc[self.idx]=self.openQgrade 
                self.idx += 1 
            self.back = False
        if k == ord('b'): #if b is pressed, go back one
            self.idx -= 1
            #self.back = True
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


    
  