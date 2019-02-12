import numpy as np
import cv2
import pandas as pd
import fnmatch
import scan_functions
import difflib
from pathlib import Path

    
def getid(idRes, nRes):
    #compile student name
    lastName=nRes['N1']+nRes['N2']+nRes['N3']+nRes['N4']+nRes['N5']
    firstName=nRes['F1']+nRes['F2']+nRes['F3']
    #get list of ID keys
    studentID = ''
    for k, v in sorted(idRes.items()):
        studentID = studentID + str(v)    
    return lastName, firstName, studentID

    
def gradeResults(resCsv, selectAll, openQ, bubbleVal, openVal, markeddir):
    #open the csv into a Pandas data frame
    df=pd.read_csv(resCsv)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]
    #create score and partial score columns at the end (overwrite if existing)
    df['score']=0
    df['partialscore']=0
    #create a bottom row to track number correct per question (overwrite if existing)
    df.loc['numb_correct']=0
    #create a new dataframe that matches the results frame, but that contains points gained per question per student (replace answers with points gained
    ptsdf=df.copy(deep=True)
    ptsdf.loc[:,3:] = 0.0
    #loop through students
    for row in range(1,df.shape[0]-1):
        row=str(row)
        #create grade of total correct
        score = 0
        #create grade of partial correct
        partscore = 0
        #loop through questions
        for col in df.columns[3:-2]:
            #compare student's answer to key
            key = df[col][0]
            if key == 'ignore':
                continue
            #if it's an open ended question
            if key == 'CC':
                ans = df[col][row]
                if ans == 'CC':
                    score += openVal
                    partscore += openVal
                    ptsdf.loc[row,col] = openVal
                    df.loc['numb_correct',col] = df.loc['numb_correct',col] + 1
                if ans == 'CX':
                    score =+ openVal / 2
                    partscore += openVal / 2
                    ptsdf.loc[row,col] = openVal / 2
                # go on to the next question
                continue
            ans = df[col][row]
            # catch when ans is '-' meaning no answer was scanned
            if ans == '-':
                    # get scan number (index), name, and L number
                    alertStr = 'Name: {},{}, Lnumber: {} had no answer scanned for question {}'.format(
                                df.loc[row, 'LastName'],
                                df.loc[row, 'FirstName'],
                                df.loc[row, 'studentID'],
                                str(col))
                    # check if ALERT file exists, if it does, append, if it doesn't, create it and append
                    alertPath = Path (markeddir.parent / 'ALERT.txt')
                    if not alertPath.exists():
                        alertPath.write_text(alertStr)
                    else:
                        with open(alertPath, 'a') as f:
                            f.write('\n')
                            f.write(alertStr)
                            
            #if no partial credit calculations necessary
            if not selectAll and not openQ:
                if ans == key:
                    score += bubbleVal
                    partscore += bubbleVal
                    ptsdf.loc[row,col] = bubbleVal
                    df.loc['numb_correct',col] = df.loc['numb_correct',col] + 1
            # if necessary to calculate for partial credit:
            else:
                #match sequences
                s = difflib.SequenceMatcher(None, key, ans)
                #if it's completely right, add one
                if s.ratio() == 1:
                    score += bubbleVal
                    partscore += bubbleVal
                    ptsdf.loc[row,col] = bubbleVal
                else:
                    ptsdf.loc[row,col]=0
                #if anything matches...
                if 0 < s.ratio() < 1:
                    ptscore=0
                    #each bubble is worth 1/(# of filled bubbles on key) up to 1
                    partial = bubbleVal/len(key)
                    #for each bubble in the student's answer
                    for i in ans:
                        #if it's in the key, add the fractional point
                        if i in key:
                            ptscore = ptscore + partial
                        #if it's not in the key, penalize by the fractional point
                        if i not in key:
                            ptscore = ptscore - partial
                    #make sure the partial score is positive and add
                    if ptscore>0:
                        partscore = partscore + ptscore
                        ptsdf.loc[row,col]=ptscore
                #calculate the per-question calculation of the number of students selecting the correct answer
                df.loc['numb_correct',col] = df[col]['numb_correct'] + int(s.ratio())
        #save score and partscore to new columns
        df.loc[row,'score']=score
        df.loc[row,'partialscore']=partscore
    #write the dataframe back to the csv
    df.to_csv(resCsv, index=True, index_label = 'index')
    ptsdf.to_csv(resCsv.split('.')[0] +'perquestions.csv')
    # make a grades csv for upload to canvas, sorted by last name, just names, Lnum, and scores without the key
    cols = ['LastName','FirstName','studentID','partialscore']
    gradesdf = df[cols].copy()
    gradesdf = gradesdf.drop(index='0')
    gradesdf = gradesdf.drop(index='numb_correct')
    gradesdf = gradesdf.sort_values(by=['LastName', 'FirstName','studentID'])
    gradesdf.to_csv(resCsv.split('.')[0]+'forCanvas.csv')
    print('Done grading')

def markSheets(resCsv, aligned_image_list, markeddir, qAreas, qDict, markmissing, markCorr):
    # load results csv
    df=pd.read_csv(resCsv)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]
    # load aligned images (not key) in loop with index that will equal row number
    for row in range(len(aligned_image_list)):
        img = cv2.imread(aligned_image_list[row], 1)
        # loop through each question
        for col in df.columns[3:-2]: 
            key = df[col][0]
            if key == 'ignore':
                continue
            
            key = list(key)
#           print(key)
            ans = list(df[col][row])
            #for open questions
            if col[0:4] == 'open':
                coord = 0
                for lett in ans:
                    markX = qAreas[col][0][0] + coord
                    markY = qAreas[col][1][1]
                    if lett == 'C':
                        cv2.putText(img, 'C', 
                                    (markX, markY),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                                    (0,255,0), 3)
                    if lett == 'X':
                        cv2.putText(img, 'X', 
                                    (markX, markY),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                                    (0,0,255), 3)
                    coord += 30
            
            else: # bubble questions
                #loop through each given answer
                for lett in ans:
                    coord = qDict[lett]
                    markX=qAreas[col][0][0]+coord-8
                    markY=qAreas[col][1][1]
                    if lett in key:
                        # if that letter is in the key, mark with green C
                        cv2.putText(img, 'C',
                                        (markX, markY),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                                        (0,255,0), 2)
                        key.remove(lett)
                    # if that letter is not in the key, mark with red X
                    elif lett != '-':
                        cv2.putText(img, 'X',
                                        (markX, markY),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                                        (0,0,255), 2)
                # if markmissing, and if there are letters in the key not in the answer, add a red M
                if markmissing and len(key)>0:
                    markX=qAreas[col][0][0] - 26
                    cv2.putText(img, 'M',
                                    (markX, markY),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                                    (0, 0, 255), 2)
                # if student left answer blank and it shouldn't have been
                if ans == '-' and len(key)>0:
                    markX=qAreas[col][0][0] - 26
                    cv2.putText(img, 'M',
                                    (markX, markY),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                                    (0, 0, 255), 2)
                # if mark correct is selected and the student did not mark the correct answer
                if markCorr and len(key)>0:
                    for lett in key:
                        coord = qDict[lett]
                        markX=qAreas[col][0][0]+coord-8
                        cv2.putText(img, '#',
                                        (markX, markY),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                                        (255,0,0), 2)
                
            
        # get name of student
        studentName=df['LastName'][row] + '_' + df['FirstName'][row] + '_' + df['studentID'][row] + '.jpg'
        # save image in marked dir
        cv2.imwrite(str(markeddir / studentName), img)
        if row == 0: #this is the key, get the filename
            keyname = markeddir / studentName
            #keyname = keyname.name
    #return the path to the marked key to include as the first page in the archive pdf
    return keyname
        