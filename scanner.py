from fpdf import FPDF
import sys
import os
import fnmatch
import pandas as pd
import ast
from pathlib import Path

from dicts import Dicts
from settings import Settings
from image import Image
import init_functions
import scan_functions
import grade_functions
from openQ import OpenQs


class Scanner(object):
    '''
    Scanner is the main class that contains scanner settings from the GUI,
    lists of image files,
    aligment matrices,
    grade sheet file names,
    and panda data tables for grading
    '''
    
    def __init__(self, input_file, quests, markmissing, openQ, ignores, thresh):
        '''
        retrieve values from the gui (or call from command line)
        input_file is path to key jpg or pdf of all scans
        quests is an integer as the number of questions to grade
        markmissing is a boolean - True if select all that apply, False if not
        openQ is a boolean - True if there are any open ended questions to grade on screen
        ignnores is a comma separated string of numbers of questions to not scan (for open ended Q's)
        '''
        self.input_file = input_file
        self.quests = quests
        self.markmissing = markmissing #means select all that apply questions
        self.openQ = openQ
        if len(ignores)>0:
            ignores=ignores+','
            self.ignores=list(ast.literal_eval(ignores))
        else:
            self.ignores=None
        # pull settings into scanner object
        self.scan_settings=Settings()
        self.scan_settings.sigma = thresh
        # self.path is a Path object
        #Get the file path as a Path object
        self.path=Path(input_file).parent
        # Make all the necessary folders
        self.aligneddir = self.path / 'aligned'
        self.aligneddir.mkdir(exist_ok = True)
        self.markeddir = self.path / 'marked'
        self.markeddir.mkdir(exist_ok = True)
        # initialize file and pathnames (and split pdfs into jpgs) 
        self.image_list = init_functions.filenames(input_file)
        # intialize the output pdf which the scanner object will write to
        self.outpdf=FPDF('P','pt','Letter')
        # initialize the pandas dataframe to contain results
        self.resdf = init_functions.makeResDf(quests, len(self.image_list))
        # make the dictionaries containing scanning coordinates
        self.qAreas, self.idAreas, self.nAreas = init_functions.makeAreaDict(quests)
        # make the dictionaries to convert coordinates to letters or numbers
        self.Ndict, self.Idict, self.Qdict = init_functions.makeResDict()
        self.run()
        
    def run(self):
        # Run the scanner on each file
        # will scan dots and save out aligned image for future use)
        for i in range(len(self.image_list)):
            # create image object, which will load and align image
            # makes img.aligned, img.scanimg
            img = Image(self.image_list[i], self.scan_settings)
            print('Processing scan {0:1d}'.format(i))
            #save the aligned image aligned_00i.jpg in ./aligned
            scan_functions.saveimg(self.image_list, i, img.aligned, self.aligneddir)
            self.qRes=scan_functions.rundots(img.scanimg, 
                                            self.qAreas, self.idAreas, self.nAreas, 
                                            self.ignores, 
                                            self.Qdict, self.Idict, self.Ndict)
            # save results dictionary data to data frame
            for k, v in self.qRes.items():
                self.resdf.loc[i,k]=v
        #get the aligned image dir
        #aligneddir = self.image_list[0].rsplit('/',1)[0]+'/aligned/'
        self.aligned_image_list = []
        for file in os.listdir(str(self.aligneddir)):
            if fnmatch.fnmatch(file, '*.jpg'):
                # add the path to the file
                self.aligned_image_list.append(str(self.aligneddir / file))
        self.aligned_image_list.append = sorted(self.aligned_image_list)
        # run the open questions grader
        if self.openQ:
            ''' 
            open the key for open question grading, openQs will be object
            openQs.openQkeyimgs is a dictionary containing the images for grading
            openQs.openQcoords is a dictionary containing the coordinates for each image
            openQs.openQres is a dataframe containing the two-letter results (CC, CX, XX) for the open ended questions in same format as main results dictionary
            '''
            
            openQs = OpenQs(self.aligned_image_list)
            # results data frame is accessed as openQs.openQres
            # add openQcoords to self.qAreas
            # rearrange first
            for k, v in openQs.openQcoords.items():
                self.qAreas[k] = ((v[0],v[1]),(v[2], v[3]))
            # add openQ results to regular results
            self.resdf = pd.concat([self.resdf, openQs.openQres], axis=1)
        
        # write resdf to csv
        self.resCsv = str(self.path / 'results.csv')
        self.resdf.to_csv(self.resCsv, index=True, index_label = 'index')
        
        # grade the results csv file and save out pts per question csv file
        grade_functions.gradeResults(self.resCsv, self.markmissing, self.openQ)
        
        # mark questions
        # markeddir = self.image_list[0].rsplit('/',1)[0]+'/marked/'
        keyname = grade_functions.markSheets(self.resCsv, self.aligned_image_list, self.markeddir, self.qAreas, self.Qdict, self.markmissing)
        # intialize the output pdf
        self.outpdf=FPDF('P','pt','Letter')
        scan_functions.savePdf(self.markeddir, self.outpdf, keyname)
        self.outpdf.output(str(self.path / 'marked.pdf'), 'F')


