import re
import numpy as np
import pandas as pd
import fnmatch
import scan_functions
import difflib
import os
from pathlib import Path
from PIL import Image as PILImage, ImageDraw, ImageFont


def _get_font(size=28):
    """Return a PIL font of the given size, falling back to the default bitmap font."""
    import sys
    candidates = []
    if sys.platform == 'darwin':
        candidates = [
            '/Library/Fonts/Arial.ttf',
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
        ]
    elif sys.platform == 'win32':
        candidates = ['C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/consola.ttf']
    else:
        candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default(size=size)

    
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
    df=pd.read_csv(resCsv, dtype=object)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]
    #create score and partial score columns at the end (overwrite if existing)
    df['score'] = np.float64(0)
    df['partialscore'] = np.float64(0)
    #create a bottom row to track number correct per question (overwrite if existing)
    df.loc['numb_correct'] = 0
    # Ensure score/partialscore stay float64 after row addition
    df['score'] = df['score'].astype(np.float64)
    df['partialscore'] = df['partialscore'].astype(np.float64)
    #create a new dataframe that matches the results frame, but that contains points gained per question per student (replace answers with points gained
    ptsdf=df.copy(deep=True)
    ptsdf.iloc[:, 3:] = 0.0
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
            key = df.loc['0', col]
            if key == 'ignore':
                continue
            #if it's an open ended question
            if key == 'CC':
                ans = df.loc[row, col]
                # support 'CC: transcription text' format as well as plain 'CC'
                ans_grade = str(ans)[:2]
                if ans_grade == 'CC':
                    score += openVal
                    partscore += openVal
                    ptsdf.loc[row,col] = openVal
                    df.loc['numb_correct',col] = df.loc['numb_correct',col] + 1
                if ans_grade == 'CX':
                    score += openVal / 2
                    partscore += openVal / 2
                    ptsdf.loc[row,col] = openVal / 2
                # go on to the next question
                continue
            ans = df.loc[row, col]
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
                df.loc['numb_correct',col] = df.loc['numb_correct',col] + int(s.ratio())
        #save score and partscore to new columns
        df.loc[row,'score']=score
        df.loc[row,'partialscore']=partscore
    #write the dataframe back to the csv
    df.to_csv(resCsv, index=True, index_label = 'index')
    _stem = str(Path(resCsv).parent / Path(resCsv).stem)
    ptsdf.to_csv(_stem + 'perquestions.csv')
    # make a grades csv for upload to canvas, sorted by last name, just names, Lnum, and scores without the key
    cols = ['LastName','FirstName','studentID','partialscore']
    gradesdf = df[cols].copy()
    gradesdf = gradesdf.drop(index='0')
    gradesdf = gradesdf.drop(index='numb_correct')
    gradesdf = gradesdf.sort_values(by=['LastName', 'FirstName','studentID'])
    gradesdf.to_csv(_stem + 'forCanvas.csv')
    print('Done grading')

def regrade_open_questions(resCsv: str, acceptable_answers: dict, transcriptions: dict,
                            partial_answers: dict | None = None) -> int:
    """
    Re-evaluate open-ended question grades in an existing results.csv using
    updated acceptable_answers and stored transcriptions.

    Only upgrades grades (XX→CC, XX→CX, CX→CC), never downgrades.
    Returns the total number of grade slots upgraded.

    acceptable_answers: {qk: [str, ...]}
    transcriptions:     {qk: {str(idx): [text, conf]}}
    partial_answers:    {qk: [str, ...]}  (optional; earn partial credit CX)
    """
    from ocr import suggest_grade
    df = pd.read_csv(resCsv, dtype=object)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]

    grade_rank = {'CC': 3, 'CX': 2, 'XX': 1, '': 0}
    total_upgraded = 0
    open_cols = [c for c in df.columns if c.startswith('openQ_')]

    for qk in open_cols:
        if qk not in transcriptions:
            continue
        acc_list = acceptable_answers.get(qk, [])
        partial_list = (partial_answers or {}).get(qk, [])
        if not acc_list and not partial_list:
            continue
        q_trans = transcriptions[qk]   # {str(idx): [text, conf]}
        for row_str, trans_val in q_trans.items():
            if row_str not in df.index:
                continue
            if row_str in ('0', 'numb_correct'):
                continue
            text, conf = trans_val[0], float(trans_val[1])
            if not text:
                continue
            old_grade_cell = str(df.loc[row_str, qk])
            # support 'CC: transcription text' format as well as plain 'CC'/'CX'/'XX'
            old_grade = old_grade_cell[:2] if old_grade_cell[:2] in ('CC', 'CX', 'XX') else old_grade_cell
            new_sug = suggest_grade(text, acc_list, conf,
                                    partial_texts=partial_list if partial_list else None)
            if new_sug and grade_rank.get(new_sug, 0) > grade_rank.get(str(old_grade), 0):
                df.loc[row_str, qk] = f'{new_sug}: {text}'
                total_upgraded += 1

    df.to_csv(resCsv, index=True, index_label='index')
    return total_upgraded


def markSheets(resCsv, aligned_image_list, markeddir, qAreas, qDict, markmissing, markCorr):
    # load results csv
    df = pd.read_csv(resCsv)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]

    font = _get_font(size=28)
    # cv2 putText uses bottom-left anchor; Pillow uses top-left, so we subtract this offset
    TEXT_Y_OFFSET = 26

    # PIL RGB colors (note: cv2 used BGR, so (0,0,255) red in BGR = (255,0,0) in RGB)
    GREEN = (0, 255, 0)
    RED   = (255, 0, 0)
    BLUE  = (0, 0, 255)

    keyname = None
    # load aligned images in loop with index matching the results row number
    for row in range(len(aligned_image_list)):
        if aligned_image_list[row] is None:
            continue   # synthetic key row — no image to mark
        pil_img = PILImage.open(aligned_image_list[row]).convert('RGB')
        draw = ImageDraw.Draw(pil_img)

        for col in df.columns[3:-2]:
            key = df.loc['0', col]
            if key == 'ignore':
                continue

            key = list(key)
            ans = list(df.loc[str(row), col])

            # open-ended questions
            if col[0:4] == 'open':
                # extract just the 2-char grade code (supports 'CC: text' format)
                grade_code = str(df.loc[str(row), col])[:2]
                coord = 0
                for lett in list(grade_code):
                    markX = qAreas[col][0][0] + coord
                    markY = qAreas[col][1][1]
                    color = GREEN if lett == 'C' else RED
                    draw.text((markX, markY - TEXT_Y_OFFSET), lett, fill=color, font=font)
                    coord += 30

            else:  # bubble questions
                markY = qAreas[col][1][1]
                for lett in ans:
                    coord = qDict[lett]
                    markX = qAreas[col][0][0] + coord - 8
                    if lett in key:
                        draw.text((markX, markY - TEXT_Y_OFFSET), 'C', fill=GREEN, font=font)
                        key.remove(lett)
                    elif lett != '-':
                        draw.text((markX, markY - TEXT_Y_OFFSET), 'X', fill=RED, font=font)

                if markmissing and len(key) > 0:
                    markX = qAreas[col][0][0] - 26
                    draw.text((markX, markY - TEXT_Y_OFFSET), 'M', fill=RED, font=font)
                if ans == ['-'] and len(key) > 0:
                    markX = qAreas[col][0][0] - 26
                    draw.text((markX, markY - TEXT_Y_OFFSET), 'M', fill=RED, font=font)
                if markCorr and len(key) > 0:
                    for lett in key:
                        coord = qDict[lett]
                        markX = qAreas[col][0][0] + coord - 8
                        draw.text((markX, markY - TEXT_Y_OFFSET), '#', fill=BLUE, font=font)

        # get name of student and save — sanitize to prevent path traversal
        def _safe(s):
            return re.sub(r'[^\w\-]', '_', str(s))
        studentName = (_safe(df.loc[str(row), 'LastName']) + '_' +
                       _safe(df.loc[str(row), 'FirstName']) + '_' +
                       _safe(df.loc[str(row), 'studentID']) + '.jpg')
        pil_img.save(str(markeddir / studentName), quality=95)
        if row == 0:
            keyname = markeddir / studentName

    return keyname
