import sys
from scanner import Scanner
from keymaker import KeyMaker
from tkinter import *
from tkinter import filedialog
from tkinter import ttk

class pyScanUI(Frame): 
    """
    A class to run the  GUI
    """
    def __init__(self,parent):
        Frame.__init__(self,parent)
        self.parent = parent
        self.__initUI()
        
    def __initUI(self):
        self.parent.title("Python ExamScan")
        button_browse = Button(self.parent, text="Choose pdf of scans or jpg of key", command = self.button_browse_callback)
        button_browse.pack()

        self.fileEntry = Entry(self.parent, width = 50)
        self.fileEntry.pack()
        
        self.numQlabel = Label(self.parent, text = 'enter number of questions to grade:')
        self.numQlabel.pack()
        
        self.numQEntry = Entry(self.parent, width = 10)
        self.numQEntry.pack()
        
        self.ignorelabel = Label(self.parent, text = 'enter question numbers to ignore separated by commas:')
        self.ignorelabel.pack()
        
        self.ignoreEntry = Entry(self.parent, width = 50)
        self.ignoreEntry.pack()
        
        self.setavar=IntVar()
        self.setacheck = Checkbutton(self.parent, text = 'Any select-all-that-apply-questions?', variable= self.setavar)
        self.setacheck.pack()
        
        self.openQvar = IntVar()
        self.openQcheck = Checkbutton(self.parent, text = 'Any open ended questions to grade on the fly?', variable = self.openQvar)
        self.openQcheck.pack()
        
        self.corrvar = IntVar()
        self.corrcheck = Checkbutton(self.parent, text = 'Do you want the correct answers marked?', variable = self.corrvar)
        self.corrcheck.pack()        
        
        self.bubbleValLabel = Label(self.parent, text = 'points per bubble question')
        self.bubbleValLabel.pack()
        self.bubbleValEntry = Entry(self.parent, width = 10)
        self.bubbleValEntry.insert(0, '1')
        self.bubbleValEntry.pack()
        
        self.openValLabel = Label(self.parent, text = 'points per open-ended question')
        self.openValLabel.pack()
        self.openValEntry = Entry(self.parent, width = 10)
        self.openValEntry.insert(0, '2')
        self.openValEntry.pack()
        
        self.threshlabel = Label(self.parent, text = "Don't change the value below unless you are having problems. \n Decrease to 0.2 to pick up lighter marks, \n increase to 0.3 to avoid picking up erased marks")
        self.threshlabel.pack()
        
        self.threshEntry = Entry(self.parent, width = 15)
        self.threshEntry.insert(0, '0.25')
        self.threshEntry.pack()
              
        button_go = Button(self.parent, text = "Run Scan", command = self.button_go_callback)
        button_go.pack()
        
        separator = Frame(self.parent, height =5, bd = 1, relief = SUNKEN)
        separator.pack(fill=X, padx = 5, pady = 15)

        '''
        Add GUI for key creater
        '''
        button_keyimg = Button(self.parent, text="Choose jpg of key image", command = self.button_keyimg_callback)
        button_keyimg.pack()

        self.keyImgEntry = Entry(self.parent, width = 50)
        self.keyImgEntry.pack()
        
        button_keyFile = Button(self.parent, text="Choose CSV of key answers", command = self.button_keyFile_callback)
        button_keyFile.pack()

        self.keyFileEntry = Entry(self.parent, width = 50)
        self.keyFileEntry.pack()
        
        self.versionLabel = Label(self.parent, text = 'Enter an exam version letter (A through D)')
        self.versionLabel.pack()
        
        self.keyVersionEntry = Entry(self.parent, width = 5)
        self.keyVersionEntry.insert(0, 'A')
        self.keyVersionEntry.pack()
        
        button_makeKey = Button(self.parent, text = "Make the Key", command = self.button_makekey_callback)
        button_makeKey.pack()
        
        
        
        '''
        Add GUI for CSV regrader
        '''
        
#         separator = Frame(self.parent, height =5, bd = 1, relief = SUNKEN)
#         separator.pack(fill=X, padx = 5, pady = 15)
#         
#         button_gradebrowse = Button(self.parent, text='choose results .csv file to re-grade', command=self.button_gradebrowse_callback)
#         button_gradebrowse.pack()
#         
#         self.csvEntry = Entry(self.parent, width = 50)
#         self.csvEntry.pack()
#         
#         button_grade = Button(self.parent, text='Grade file', command=self.button_grade_callback)
#         button_grade.pack()
#         
#         separator = Frame(self.parent, height =2, bd = 1, relief = SUNKEN)
#         separator.pack(fill=X, padx = 5, pady = 15)
#         
        button_exit = Button(self.parent, text = 'Exit', command=sys.exit)
        button_exit.pack()
        
        
    def button_browse_callback(self):
        filename = filedialog.askopenfilename()
        self.fileEntry.delete(0,END)
        self.fileEntry.insert(0,filename)
        
    def button_keyimg_callback(self):
        filename = filedialog.askopenfilename()
        self.keyImgEntry.delete(0,END)
        self.keyImgEntry.insert(0,filename)
    
    def button_keyFile_callback(self):
        filename = filedialog.askopenfilename()
        self.keyFileEntry.delete(0,END)
        self.keyFileEntry.insert(0,filename)

    def button_gradebrowse_callback(self):
        filename = filedialog.askopenfilename()
        self.csvEntry.delete(0,END)
        self.csvEntry.insert(0,filename)

    def button_go_callback(self):
        input_file = self.fileEntry.get()
        quests = int(self.numQEntry.get())
        markmissing=bool(self.setavar.get())
        openQ=bool(self.openQvar.get())
        corrmark=bool(self.corrvar.get())
        ignores = self.ignoreEntry.get()
        thresh = float(self.threshEntry.get())
        bubbleVal = float(self.bubbleValEntry.get())
        openVal = float(self.openValEntry.get())
        #main call to start processing
        Scanner(input_file, quests, markmissing, openQ, corrmark, ignores, thresh, bubbleVal, openVal)
        
    def button_makekey_callback(self):
        keyImg = self.keyImgEntry.get()
        keyFile = self.keyFileEntry.get()
        keyVersion = self.keyVersionEntry.get()
        KeyMaker(keyImg, keyFile, keyVersion)
        

#     def button_grade_callback(self):
#         input_file = self.csvEntry.get()
#         pyScan.gradeData(self,input_file)
