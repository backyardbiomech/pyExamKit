import re
import numpy as np
import cv2
import fnmatch
import os
import grade_functions
import pandas as pd
try:
    import tkinter as tk
    from tkinter import simpledialog
    _tk_available = True
except ImportError:
    _tk_available = False

# Display constants for the open-ended question box labels
_LABEL_COLOR = (0, 0, 200)   # BGR: red-ish for visibility
_LABEL_FONT_SCALE = 0.4

class OpenQs(object):
    '''
    a class to store all things regarding open ended questions
    '''
    def __init__(self, image_list, ignores=None):
        '''
        image_list: list of aligned image paths
        ignores: list of integer question numbers that are open-ended (from the "questions to skip" field).
                 These are used as default labels for the open-ended question boxes.
        '''
        #make a dictionary to contains coordinates of boxes
        self.openQcoords = {}
        # store the ignores list for auto-labeling open-ended questions
        self.ignores = sorted(ignores) if ignores else []

        # create self.openQkeyimgs - a dictionary containing images
        self.openQkey(image_list[0])
        # create list of openQ column names (in insertion order)
        cols = list(self.openQcoords.keys())
        # initialize a dataFrame to contain results
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
        cv2.destroyAllWindows()
    
    def _get_question_label(self, box_index):
        '''
        Return a question label for the given box index (0-based).
        If the ignores list has an entry at this index, use that number.
        Otherwise prompt the user.
        '''
        if box_index < len(self.ignores):
            default_num = self.ignores[box_index]
        else:
            default_num = box_index + 1
        # Try to prompt the user via tkinter dialog for a custom number
        if _tk_available:
            root = tk.Tk()
            root.withdraw()
            result = simpledialog.askinteger(
                "Open-Ended Question Number",
                "Enter the question number for this open-ended answer box\n(default: {}):".format(default_num),
                initialvalue=default_num,
                parent=root
            )
            root.destroy()
            if result is not None:
                return 'openQ_' + str(result)
        return 'openQ_' + str(default_num)

    def openQkey(self, imgpath):
        '''
        opens the key as an image an allows drawing of rectangles
        '''
        #load and resize the image
        img=cv2.imread(imgpath, 1)
        self.dispres = .5
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
            #add coordinates to dictionary using the question-number-based label
            box_index = len(self.openQcoords)
            label = self._get_question_label(box_index)
            # ensure no duplicate labels
            while label in self.openQcoords:
                # append an incrementing suffix if duplicate
                m = re.match(r'^(openQ_\d+)(?:_(\d+))?$', label)
                if m:
                    base = m.group(1)
                    count = int(m.group(2)) + 1 if m.group(2) else 2
                    label = '{}_{}'.format(base, count)
                else:
                    label = label + '_2'
            self.openQcoords[label]=(int(self.sx/self.dispres), int(self.sy/self.dispres), int(ex/self.dispres), int(ey/self.dispres))
            self.drawrects()
            
    def drawrects(self):
        #copy the image again
        img=self.imgopenQ.copy()
        #then draw all rectangles on the image and display
        for k, v in self.openQcoords.items():
            cv2.rectangle(img, (int(self.dispres * v[0]),int(self.dispres * v[1])), 
                        (int(self.dispres*v[2]), int(self.dispres*v[3])), 60, 1)
            # label the box with the question name
            cv2.putText(img, k, (int(self.dispres * v[0]), int(self.dispres * v[1]) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, _LABEL_FONT_SCALE, _LABEL_COLOR, 1)
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


    
  