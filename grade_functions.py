import re
import json
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

    
def gradeResults(resCsv, selectAll, openQ, bubbleVal, openVal, markeddir, strictness=0.5, point_values=None):
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
            # Per-question point value: use key-file override if available, else default
            if key == 'CC':
                q_pts = point_values.get(col, openVal) if point_values else openVal
            else:
                q_pts = point_values.get(col, bubbleVal) if point_values else bubbleVal
            #if it's an open ended question
            if key == 'CC':
                ans = df.loc[row, col]
                # support 'CC: transcription text' format as well as plain 'CC'
                ans_grade = str(ans)[:2]
                if ans_grade == 'CC':
                    score += q_pts
                    partscore += q_pts
                    ptsdf.loc[row,col] = q_pts
                    df.loc['numb_correct',col] = df.loc['numb_correct',col] + 1
                if ans_grade == 'CX':
                    score += q_pts / 2
                    partscore += q_pts / 2
                    ptsdf.loc[row,col] = q_pts / 2
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
                    score += q_pts
                    partscore += q_pts
                    ptsdf.loc[row,col] = q_pts
                    df.loc['numb_correct',col] = df.loc['numb_correct',col] + 1
            # if necessary to calculate for partial credit:
            else:
                #match sequences
                s = difflib.SequenceMatcher(None, key, ans)
                #if it's completely right, add one
                if s.ratio() == 1:
                    score += q_pts
                    partscore += q_pts
                    ptsdf.loc[row,col] = q_pts
                else:
                    ptsdf.loc[row,col]=0
                #if anything matches above the strictness threshold, award partial credit
                if 0 < s.ratio() < 1 and s.ratio() >= strictness:
                    ptscore=0
                    #each bubble is worth 1/(# of filled bubbles on key) up to 1
                    partial = q_pts/len(key)
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
        ptsdf.loc[row,'score'] = score
        ptsdf.loc[row,'partialscore'] = partscore
    #write the dataframe back to the csv
    df.to_csv(resCsv, index=True, index_label = 'index')
    _stem = str(Path(resCsv).parent / Path(resCsv).stem)
    ptsdf.to_csv(_stem + 'perquestions.csv')
    try:
        _xlsx_path = _stem + '_gradebook.xlsx'
        # Load open-ended question answers for gradebook display
        # (save_artifacts writes this file before gradeResults is called)
        _open_q_answers = None
        try:
            _app_data = Path(resCsv).parent / 'app_data'
            _ans_file = _app_data / (Path(resCsv).stem + '_openq_answers.json')
            if _ans_file.exists():
                _raw = json.loads(_ans_file.read_text(encoding='utf-8'))
                _open_q_answers = {}
                for _qk, _v in _raw.items():
                    if isinstance(_v, dict):
                        _open_q_answers[_qk] = _v.get('full', [])
                    elif isinstance(_v, list):
                        _open_q_answers[_qk] = _v
        except Exception:
            pass
        save_gradebook_xlsx(_xlsx_path, df, ptsdf, open_q_answers=_open_q_answers)
        print(f'Gradebook saved \u2192 {_xlsx_path}')
    except Exception as _exc:
        print(f'[gradeResults] Could not save gradebook xlsx: {_exc}')
    # make a grades csv for upload to canvas, sorted by last name, just names, Lnum, and scores without the key
    cols = ['LastName','FirstName','studentID','partialscore']
    gradesdf = df[cols].copy()
    gradesdf = gradesdf.drop(index='0')
    gradesdf = gradesdf.drop(index='numb_correct')
    gradesdf = gradesdf.sort_values(by=['LastName', 'FirstName','studentID'])
    gradesdf.to_csv(_stem + 'forCanvas.csv')
    print('Done grading')

def save_gradebook_xlsx(xlsx_path: str, df, ptsdf, open_q_answers: dict | None = None) -> None:
    """
    Write an xlsx gradebook with live SUM formulas.

    Layout (one sheet "Gradebook"):
      Row 1 — frozen header: LastName | FirstName | studentID |
               Q Answer (Key: X) | Q Pts | ... | Total
      Row 2 — KEY row (yellow): raw key answers; for open-ended questions,
               pipe-separated acceptable answers from open_q_answers (if provided)
      Rows 3+ — students: answer + points per question;
                 Total cell is =SUM(...) formula so editing a Pts cell updates Total

    df    — full results DataFrame (index '0' = key row)
    ptsdf — points DataFrame (same shape; question cells contain float points)
    open_q_answers — {qk: [answer_str, ...]} of full-credit answers for open-ended
                     questions; used to populate the KEY row (optional)
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    # Question columns: everything after name cols (LastName/FirstName/studentID),
    # before the score/partialscore summary columns at the end.
    q_cols = list(df.columns[3:-2])
    n_q = len(q_cols)

    # Student row indices — string '1'...'N'; exclude key row '0' and 'numb_correct'
    student_indices = [str(i) for i in range(1, df.shape[0] - 1)]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Gradebook'

    # Column layout:
    #   cols 1-3  : LastName, FirstName, studentID
    #   col 4+2*i : student answer for question i (0-based)
    #   col 5+2*i : points for question i
    #   col 4+2*n_q : Total
    total_col_num = 4 + 2 * n_q  # 1-based

    def pts_col_num(qi: int) -> int:
        return 5 + 2 * qi

    # ── Row 1: header ──────────────────────────────────────────────────────
    header = ['LastName', 'FirstName', 'studentID']
    for qi, qc in enumerate(q_cols):
        key_val = str(df.loc['0', qc])
        if key_val == 'CC':
            key_label = f'{qc}\n(open-ended)'
        elif key_val in ('ignore', 'nan', ''):
            key_label = f'{qc}\n(ignored)'
        else:
            key_label = f'{qc}\n(Key: {key_val})'
        header.append(key_label)
        header.append(f'{qc} Pts')
    header.append('Total')
    ws.append(header)

    hdr_fill = PatternFill('solid', fgColor='BDD7EE')
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
        cell.fill = hdr_fill
    ws.row_dimensions[1].height = 36

    # ── Row 2: KEY row ──────────────────────────────────────────────────────
    key_row = ['KEY', '', '']
    for qi, qc in enumerate(q_cols):
        key_val = str(df.loc['0', qc])
        if key_val == 'CC' and open_q_answers and qc in open_q_answers:
            answers = open_q_answers[qc]
            key_display = ' | '.join(answers) if answers else 'CC'
        else:
            key_display = key_val
        key_row.append(key_display)
        key_row.append('')
    key_row.append('')
    ws.append(key_row)

    key_fill = PatternFill('solid', fgColor='FFFF99')
    for cell in ws[2]:
        cell.font = Font(bold=True)
        cell.fill = key_fill

    # ── Rows 3+: student rows ───────────────────────────────────────────────
    for row_str in student_indices:
        row_data = [
            str(df.loc[row_str, 'LastName']),
            str(df.loc[row_str, 'FirstName']),
            str(df.loc[row_str, 'studentID']),
        ]
        for qi, qc in enumerate(q_cols):
            ans = str(df.loc[row_str, qc])
            try:
                pts = float(ptsdf.loc[row_str, qc])
            except (ValueError, TypeError, KeyError):
                pts = 0.0
            row_data.append(ans)
            row_data.append(pts)
        row_data.append('')  # placeholder for formula
        ws.append(row_data)

        excel_row = ws.max_row
        sum_refs = ','.join(
            f'{get_column_letter(pts_col_num(qi))}{excel_row}'
            for qi in range(n_q)
        )
        ws.cell(row=excel_row, column=total_col_num).value = (
            f'=SUM({sum_refs})' if sum_refs else 0
        )

    # ── Freeze header + key rows, set column widths ─────────────────────────
    ws.freeze_panes = 'A3'

    ws.column_dimensions['A'].width = 16
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 14
    for qi in range(n_q):
        ws.column_dimensions[get_column_letter(4 + 2 * qi)].width = 18
        ws.column_dimensions[get_column_letter(5 + 2 * qi)].width = 8
    ws.column_dimensions[get_column_letter(total_col_num)].width = 10

    wb.save(xlsx_path)


def regrade_open_questions(resCsv: str, acceptable_answers: dict, transcriptions: dict,
                            partial_answers: dict | None = None,
                            strictness: float = 0.0) -> int:
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
                                    partial_texts=partial_list if partial_list else None,
                                    partial_threshold=strictness if strictness > 0 else None)
            if new_sug and grade_rank.get(new_sug, 0) > grade_rank.get(str(old_grade), 0):
                df.loc[row_str, qk] = f'{new_sug}: {text}'
                total_upgraded += 1

    df.to_csv(resCsv, index=True, index_label='index')
    return total_upgraded


def markSheets(resCsv, aligned_image_list, markeddir, qAreas, qDict, markmissing, markCorr,
               pages_per_student=1, q_pages=None):
    """Mark student answer sheets with correct/incorrect indicators.

    aligned_image_list layout (both single- and multi-page):
      index 0          — key image (scan-key mode) or None (key-file mode)
      index (r-1)*pps+1 .. r*pps — all pages for student row r (1-based)

    pages_per_student — number of scanned pages per student (default 1)
    q_pages           — {question_key: page_number (1-based)} for open-ended
                        questions that live on a page other than page 1.
                        Bubble questions always default to page 1.
    """
    # load results csv
    df = pd.read_csv(resCsv)
    df.set_index(['index'], inplace=True)
    df.index = df.index.map(str)
    df.index.names = [None]

    if q_pages is None:
        q_pages = {}

    font = _get_font(size=28)
    # cv2 putText uses bottom-left anchor; Pillow uses top-left, so we subtract this offset
    TEXT_Y_OFFSET = 26

    # PIL RGB colors (note: cv2 used BGR, so (0,0,255) red in BGR = (255,0,0) in RGB)
    GREEN = (0, 255, 0)
    RED   = (255, 0, 0)
    BLUE  = (0, 0, 255)

    keyname = None

    # Iterate over CSV rows (skip 'numb_correct' which has no image)
    row_strs = [r for r in df.index if r != 'numb_correct']
    for row_str in row_strs:
        # Resolve which page images belong to this row
        if row_str == '0':
            # Key row — uses the single entry at index 0 (may be None in key-file mode)
            page_imgs = [aligned_image_list[0] if aligned_image_list else None]
        elif pages_per_student == 1:
            r = int(row_str)
            img = aligned_image_list[r] if r < len(aligned_image_list) else None
            page_imgs = [img]
        else:
            r = int(row_str)
            start = (r - 1) * pages_per_student + 1
            page_imgs = list(aligned_image_list[start:start + pages_per_student])
            # Pad with None if fewer images were found than expected
            while len(page_imgs) < pages_per_student:
                page_imgs.append(None)

        # Skip rows that have no images at all (e.g. synthetic key row in key-file mode)
        if all(p is None for p in page_imgs):
            continue

        # Open each page image and create a draw handle
        pil_pages = []
        draws = []
        for p in page_imgs:
            if p is None or not os.path.exists(p):
                pil_pages.append(None)
                draws.append(None)
            else:
                pil_img = PILImage.open(p).convert('RGB')
                pil_pages.append(pil_img)
                draws.append(ImageDraw.Draw(pil_img))

        for col in df.columns[3:-2]:
            key = df.loc['0', col]
            if key == 'ignore':
                continue

            key = list(key)
            ans = list(df.loc[row_str, col])

            # Determine which page image to draw on (1-based page → 0-based index)
            page_idx = max(0, q_pages.get(col, 1) - 1)
            if page_idx >= len(draws) or draws[page_idx] is None:
                continue
            draw = draws[page_idx]

            # open-ended questions
            if col[0:4] == 'open':
                # extract just the 2-char grade code (supports 'CC: text' format)
                grade_code = str(df.loc[row_str, col])[:2]
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

        # Save each page — sanitize name to prevent path traversal
        def _safe(s):
            return re.sub(r'[^\w\-]', '_', str(s))
        name_base = (_safe(df.loc[row_str, 'LastName']) + '_' +
                     _safe(df.loc[row_str, 'FirstName']) + '_' +
                     _safe(df.loc[row_str, 'studentID']))
        for page_num, pil_img in enumerate(pil_pages, 1):
            if pil_img is None:
                continue
            if pages_per_student == 1:
                filename = name_base + '.jpg'
            else:
                filename = name_base + f'_p{page_num}.jpg'
            pil_img.save(str(markeddir / filename), quality=95)
            if row_str == '0' and page_num == 1:
                keyname = markeddir / filename

    return keyname
