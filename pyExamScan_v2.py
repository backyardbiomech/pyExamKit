#!/usr/bin/env python3

from gui import pyScanUI
from tkinter import *



if __name__=="__main__":
    '''
    Create the GUI when pyExamScan_v2.py is called from the terminal
    '''
    root = Tk()
    pyScanUI(root)
    root.mainloop()