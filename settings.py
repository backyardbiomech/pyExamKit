import numpy as np

class Settings():
    '''
    A class to store all the settings for pyExamScan
    '''
    def __init__(self):
        '''Initialize the settings'''
        # set a threshold for finding registration marks
        self.volthresh = 180

        # set the kernel size for erosion/dilation (used as structuring element shape)
        self.kern = np.ones((4, 4), np.int8)
        # set the document size (#rows, #columns) to work with.  All images scaled to this.
        self.sz = (1584, 1224)
        # set the coordinates for the registration points in (x, y) = (col, row) format
        self.keyRegPts = np.array([[1153, 1532], [73, 1532], [1153, 64]], dtype=np.float32)
        # set locations for threshold calibration cues
        threshdict = {}
        threshdict['thresh01'] = (607, 55),  (635, 83)
        threshdict['thresh02'] = (600, 1520), (626, 1548)
        threshdict['thresh03'] = (36, 828),  (68, 856)
        threshdict['thresh04'] = (1165, 842), (1193, 870)
        self.threshdict = threshdict
        # relative threshold value used in autothresh
        self.sigma = 0.25
