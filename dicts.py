class Dicts(object):

    def __init__(self):
        '''
        define dictionaries to contain search areas
        '''
        self.dotareas = self.makeAreaDict()
        self.openQcoords={}
            
        
    def makeAreaDict(self):
        '''
        define dictionrary containing search area for all 150 questions, names, and ID numbers
        keys that start with F are first names, N are last names, 
        ID are ID numbers, and Q are questions
        3 first and 5 last name boxes
        '''
        # First names
        NX=124
        NY=268
        nameWidth=676
        namegap = 2
        for i in range(1,4):
            keyName = 'F' + str(i) 
            startX=NX
            startY=NY+(i-1)*(26+ namegap)
            endX=startX+nameWidth
            endY=startY+20
            self.areaDict[keyName] = (startX,startY), (endX, endY)

        # Last names
        NX=124
        NY=400
        nameWidth=676
        namegap = 2
        for i in range(1,6):
            keyName = 'N' + str(i) 
            startX=NX
            startY=NY+(i-1)*(26+ namegap)
            endX=startX+nameWidth
            endY=startY+20
            self.areaDict[keyName] = (startX,startY), (endX, endY)

        # ID number boxes
        IDX = 874
        IDY = 273
        IDheight = 260
        IDgap = 2
        for i in range (1, 9):
            keyName = 'ID' + format(i,'02d')
            startX=IDX+(i-1)*(28+IDgap)
            startY= IDY
            endX=startX+28
            endY= startY + IDheight
            self.areaDict[keyName] = (startX,startY), (endX, endY)
        
        # Questions
        QX = 126
        QY = 595
        Qwidth = 160
        Qgap = 2
        for i in range(1, 151):
            if i > int(self.quests):
                break
            keyName = 'Q' + format(i, '03d')
            if i < 16:
                startY=QY+((28+Qgap) * (i - 1))
            elif i < 31:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 16))
            elif i < 46:
                QX = 338
                QY = 595
                startY=QY+((28+Qgap) * (i - 31))
            elif i < 61:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 46))
            elif i < 76:
                QX = 550
                QY = 595
                startY=QY+((28+Qgap) * (i - 61))
            elif i < 91:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 76))
            elif i < 106:
                QX = 762
                QY = 595
                startY=QY+((28+Qgap) * (i - 91))
            elif i < 121:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 106))
            elif i < 136:
                QX = 976
                QY = 595
                startY=QY+((28+Qgap) * (i - 121))
            else:
                QY = 1046
                startY=QY+((28+Qgap) * (i - 136))
            endY=startY+26
            self.areaDict[keyName] = (QX, startY), (QX + Qwidth, endY)