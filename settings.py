import numpy as np

class Settings():
    '''
    A class to store all the settings for pyExamKit
    '''
    def __init__(self):
        '''Initialize the settings'''
        # set a threshold for finding registration marks
        self.volthresh = 180

        # set the document size (#rows, #columns) to work with.  All images scaled to this.
        self.sz = (1584, 1224)
        # set the coordinates for the registration points in (x, y) = (col, row) format
        self.keyRegPts = np.array([[1153, 1532], [73, 1532], [1153, 64]], dtype=np.float32)

