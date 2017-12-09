from fpdf import FPDF
import sys

from dicts import Dicts
from settings import Settings
from image import Image
import init_functions
import scan_functions
import df_functions
from openQ import OpenQs


class Scanner(object):
    '''
    Scanner is the main class that contains scanner settings from the GUI,
    lists of image files,
    aligment matrices,
    grade sheet file names,
    and panda data tables for grading
    '''
    
    def __init__(self, input_file, quests, markmissing, openQ, ignores):
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
        self.markmissing = markmissing
        self.openQ = openQ
        if len(ignores)>0:
            ignores=ignores+','
            self.ignores=list(ast.literal_eval(ignores))
        else:
            self.ignores=None
        # pull settings into scanner object
        self.scan_settings=Settings()
        # initialize file and pathnames (and split pdfs into jpgs)
        self.path, self.image_list = init_functions.filenames(input_file)
        # intialize the output pdf which the scanner object will write to
        self.outpdf=FPDF('P','pt','Letter')
        # initialize the pandas dataframe to contain results
        self.resdf = init_functions.makeResDf(quests, len(self.image_list))
        # make the dictionaries containing scanning coordinates
        self.qAreas, self.idAreas, self.nAreas = init_functions.makeAreaDict(quests)
        # make the dictionaries to convert coordinates to letters or numbers
        self.Ndict, self.Idict, self.Qdict = init_functions.makeResDict()
        # Run the scanner on each file
        # will scan dots and save out aligned image for future use)
        for i in range(len(self.image_list)):
            # create image object, which will load and align image
            # makes img.aligned, img.scanimg
            img = Image(self.image_list[i], self.scan_settings)
            print('Processing scan {0:1d}'.format(i))
            #save the aligned image aligned_00i.jpg in ./aligned
            scan_functions.saveimg(self.image_list, i, img.aligned)
            self.qRes=scan_functions.rundots(img.scanimg, 
                                            self.qAreas, self.idAreas, self.nAreas, 
                                            self.ignores, 
                                            self.Qdict, self.Idict, self.Ndict)
            # save results dictionary data to data frame
            for k, v in self.qRes.items():
                self.resdf.loc[i,k]=v
        #get the aligned image dir
        aligneddir = image_list[0].rsplit('/',1)[0]+'/aligned/'
        self.aligned_image_list = []
        for file in os.listdir(aligneddir):
            if ((fnmatch.fnmatch(file, '*.jpg'):
                # add the path to the file
                self.aligned_image_list.append(pathname+file)
        
        self.aligned_image_list = aligned_image_list.sorted()
        # run the open questions grader
        if self.openQ:
            ''' 
            open the key for open question grading, openQs will be object
            openQs.openQkeyimgs is a dictionary containing the images for grading
            openQs.openQcoords is a dictionary containing the coordinates for each image
            openQs.openQres is a dataframe containing the two-letter results (CC, CX, XX) for the open ended questions in same format as main results dictionary
            '''
            openQs = openQ_functions.gradeOpenQ(self.aligned_image_list)
            # results data frame is accessed as openQs.openQres
            
            #### HERE#######
            # need to grade scanned and open ended questions
            # need to mark scanned questions
            # need to mark open ended questions
            # need to save out marked pdf and marked jpgs
                
        

        # test write resdf to csv
        fname = self.path + 'results.csv'
        print(fname)
        self.resdf.to_csv(fname, index=True, index_label = 'index')
        sys.exit()

