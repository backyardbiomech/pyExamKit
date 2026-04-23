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
    
    def __init__(self, input_file, quests, markmissing, openQ, corrmark, ignores, thresh, bubbleVal, openVal, parent=None, ai_ocr=False, api_key='', ai_context='', preloaded_file: str = '', review_perfect: bool = True, key_file_path: str = '', pages_per_student: int = 1, save_marked: bool = True, strictness: float = 0.5, version_question: int = 0, version_key_paths: dict | None = None):
        '''
        retrieve values from the gui (or call from command line)
        input_file is path to key jpg or pdf of all scans
        quests is an integer as the number of questions to grade
        markmissing is a boolean - True if select all that apply, False if not
        openQ is a boolean - True if there are any open ended questions to grade on screen
        ignores is a comma separated string of numbers of questions to not scan (for open ended Q's)
        parent is the Tkinter root window (needed for open-ended question grading popups)
        ai_ocr is a boolean - True to use the Claude API for handwriting recognition
        api_key is the Anthropic API key string (empty = read from config file)
        ai_context is the subject-specific context hint passed to the model
        key_file_path is the path to a JSON or CSV exam key file (optional)
        pages_per_student is the number of scanned pages per student (default 1)
        strictness is a float (0-1) controlling how strict partial credit is for bubble questions.
        '''
        self.input_file = input_file
        self.quests = quests
        self.markmissing = markmissing  # means select all that apply questions
        self.openQ = openQ
        self.corrMark = corrmark
        self.save_marked = save_marked
        self.parent = parent
        self.bubbleVal = bubbleVal
        self.openVal = openVal
        self.ai_ocr = ai_ocr
        self.api_key = api_key
        self.ai_context = ai_context
        self.preloaded_file = preloaded_file
        self.review_perfect = review_perfect
        self.key_file_path = key_file_path
        self.pages_per_student = max(1, int(pages_per_student))
        self.strictness = strictness
        # ── Multi-version support ──────────────────────────────────────────────
        self.version_question = version_question
        self.version_keys: dict[str, dict] = {}
        if version_key_paths:
            from openQ import load_key_file as _lkf_ver
            for _ver, _vpath in version_key_paths.items():
                if _vpath:
                    _vkd = _lkf_ver(_vpath)
                    if _vkd:
                        self.version_keys[_ver.upper()] = _vkd
                    else:
                        print(f'[Scanner] Warning: could not load key for version {_ver}: {_vpath}',
                              flush=True)
        self._key_data = None
        if key_file_path:
            from openQ import load_key_file
            self._key_data = load_key_file(key_file_path)
            if self._key_data is None:
                print(f'[Scanner] Warning: failed to load key file "{key_file_path}". '
                      'Falling back to scan-key mode.', flush=True)
                self.key_file_path = ''
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
        # All user-facing outputs go into a single subfolder
        self.outdir = self.path / 'ExamScanner_outputs'
        self.outdir.mkdir(exist_ok=True)
        # App-internal files (aligned, scanJPGs, openq JSON) go in app_data/
        self.app_data_dir = self.outdir / 'app_data'
        self.app_data_dir.mkdir(exist_ok=True)
        # Make all the necessary folders
        self.aligneddir = self.app_data_dir / 'aligned'
        self.aligneddir.mkdir(exist_ok = True)
        self.markeddir = self.outdir / 'marked'
        self.markeddir.mkdir(exist_ok = True)
        # initialize file and pathnames (and split pdfs into jpgs) 
        self.image_list = init_functions.filenames(
            input_file, scan_jpgs_dir=self.app_data_dir / 'scanJPGs')
        # intialize the output pdf which the scanner object will write to
        self.outpdf=FPDF('P','pt','Letter')
        # initialize the pandas dataframe to contain results
        # In key-file mode we need one extra row for the synthetic key row 0.
        # For multi-page, there are pages_per_student images per student.
        if (self.key_file_path and self._key_data) or (self.version_keys and self.version_question):
            n_actual_students = len(self.image_list) // self.pages_per_student
            n_rows = n_actual_students + 1  # +1 for placeholder row 0
        else:
            n_rows = len(self.image_list)
        self.resdf = init_functions.makeResDf(quests, n_rows)
        # make the dictionaries containing scanning coordinates
        self.qAreas, self.idAreas, self.nAreas = init_functions.makeAreaDict(quests)
        # make the dictionaries to convert coordinates to letters or numbers
        self.Ndict, self.Idict, self.Qdict = init_functions.makeResDict()
        self.run()
        
    def run(self):
        if self.version_keys and self.version_question:
            self._run_multi_version()
        elif self.key_file_path and self._key_data:
            self._run_with_key_file()
        else:
            self._run_scan_key()

    def _run_multi_version(self):
        """
        Scan all student sheets, detect each student's exam version from the
        version question bubble, then grade (and optionally mark) each version
        group against its own key file. Outputs are separated by version.
        """
        pps = self.pages_per_student
        ver_qk = 'Q' + format(self.version_question, '03d')

        # 1. Scan all pages (no key row — all rows are students)
        for i in range(len(self.image_list)):
            img = Image(self.image_list[i], self.scan_settings)
            print(f'Processing scan {i + 1}')
            scan_functions.saveimg(i + 1, img.aligned, self.aligneddir)
            if i % pps == 0:   # first page per student — scan MC bubbles
                student_row = i // pps + 1
                self.qRes = scan_functions.rundots(
                    img.scanimg,
                    self.qAreas, self.idAreas, self.nAreas,
                    self.ignores,
                    self.Qdict, self.Idict, self.Ndict)
                for k, v in self.qRes.items():
                    self.resdf.loc[student_row, k] = v

        # 2. Build sorted aligned image list (files numbered 1..N)
        n_scanned = len(self.image_list)
        self.aligned_image_list = sorted(
            str(self.aligneddir / f'aligned_{i:03d}.jpg')
            for i in range(1, n_scanned + 1)
            if (self.aligneddir / f'aligned_{i:03d}.jpg').exists())

        # 3. Determine each student's version from the version question column
        #    resdf uses integer index (from makeResDf range()), so use ints here
        n_students = len(self.image_list) // pps
        student_rows = list(range(1, n_students + 1))

        version_groups: dict[str, list[int]] = {}
        for row_idx in student_rows:
            if ver_qk in self.resdf.columns:
                raw_ver = str(self.resdf.loc[row_idx, ver_qk]).strip()
            else:
                raw_ver = '-'
            ver_letter = raw_ver[0].upper() if raw_ver and raw_ver != '-' else None
            if ver_letter and ver_letter in self.version_keys:
                version_groups.setdefault(ver_letter, []).append(row_idx)
            else:
                name = self.resdf.loc[row_idx, 'LastName']
                print(f'[MultiVersion] Student row {row_idx} ({name}) has unrecognized '
                      f'version answer "{raw_ver}" — skipped.', flush=True)

        if not version_groups:
            print('[MultiVersion] No students matched any loaded version key. '
                  'Check the version question number and key files.', flush=True)
            return

        # 4. Grade (and optionally mark) each version group separately
        for ver in sorted(version_groups):
            row_indices = version_groups[ver]
            kd = self.version_keys[ver]
            print(f'\n[MultiVersion] Version {ver}: {len(row_indices)} student(s).')

            # Build key row dict from version key data
            key_row_data: dict = {'LastName': 'KEY', 'FirstName': '', 'studentID': ''}
            for qk, ans in kd.get('bubble_answers', {}).items():
                key_row_data[qk] = ans
            if self.ignores:
                for q_num in self.ignores:
                    iqk = 'Q' + format(q_num, '03d')
                    key_row_data[iqk] = 'ignore'

            # Build sub-DataFrame: row '0' = key, rows '1'..'M' = students for this version
            sub_students = self.resdf.loc[row_indices].copy()
            sub_students.index = [str(i + 1) for i in range(len(row_indices))]

            key_series = pd.Series(key_row_data, name='0').reindex(sub_students.columns).fillna('')
            sub_df = pd.concat([key_series.to_frame().T, sub_students])
            sub_df.index.name = None

            # Save version-specific results CSV
            ver_csv = str(self.outdir / f'results_version{ver}.csv')
            sub_df.to_csv(ver_csv, index=True, index_label='index')

            # Grade (bubble-only; openQ=False)
            _point_values = kd.get('point_values')
            grade_functions.gradeResults(
                ver_csv, self.markmissing, False,
                self.bubbleVal, self.openVal, self.markeddir, self.strictness,
                point_values=_point_values)

            # Mark sheets if requested
            if self.save_marked:
                imgs_for_ver = []
                for orig_row in row_indices:
                    img_idx = (orig_row - 1) * pps  # 0-based into aligned_image_list
                    if 0 <= img_idx < len(self.aligned_image_list):
                        imgs_for_ver.append(self.aligned_image_list[img_idx])

                marked_list = [None] + imgs_for_ver  # None at [0] = synthetic key placeholder
                ver_markeddir = self.outdir / f'marked_version{ver}'
                ver_markeddir.mkdir(exist_ok=True)

                keyname = grade_functions.markSheets(
                    ver_csv, marked_list, ver_markeddir,
                    self.qAreas, self.Qdict, self.markmissing, self.corrMark)

                print(f'Saving marked files for version {ver}')
                ver_pdf = FPDF('P', 'pt', 'Letter')
                scan_functions.savePdf(ver_markeddir, ver_pdf, keyname)
                ver_pdf.output(str(self.outdir / f'marked_version{ver}.pdf'))

        print('All steps complete!')

    def _run_scan_key(self):
        # Run the scanner on each file
        # will scan dots and save out aligned image for future use)
        for i in range(len(self.image_list)):
            # create image object, which will load and align image
            # makes img.aligned, img.scanimg
            img = Image(self.image_list[i], self.scan_settings)
            print('Processing scan {0:1d}'.format(i))
            #save the aligned image aligned_00i.jpg in ./aligned
            scan_functions.saveimg(i, img.aligned, self.aligneddir)
            self.qRes=scan_functions.rundots(img.scanimg, 
                                            self.qAreas, self.idAreas, self.nAreas, 
                                            self.ignores, 
                                            self.Qdict, self.Idict, self.Ndict)
            # save results dictionary data to data frame
            for k, v in self.qRes.items():
                self.resdf.loc[i,k]=v
        #get the aligned image dir
        self.aligned_image_list = []
        for file in os.listdir(str(self.aligneddir)):
            if fnmatch.fnmatch(file, '*.jpg'):
                # add the path to the file
                self.aligned_image_list.append(str(self.aligneddir / file))
        self.aligned_image_list = sorted(self.aligned_image_list)
        # run the open questions grader
        openQs = None
        if self.openQ:
            ''' 
            open the key for open question grading, openQs will be object
            openQs.openQkeyimgs is a dictionary containing the images for grading
            openQs.openQcoords is a dictionary containing the coordinates for each image
            openQs.openQres is a dataframe containing the two-letter results (CC, CX, XX) for the open ended questions in same format as main results dictionary
            '''
            
            openQs = OpenQs(self.aligned_image_list, parent=self.parent,
                            ai_ocr=self.ai_ocr, api_key=self.api_key,
                            ai_context=self.ai_context,
                            preloaded_file=self.preloaded_file,
                            review_perfect=self.review_perfect,
                            ignores=self.ignores)
            # results data frame is accessed as openQs.openQres
            # add openQcoords to self.qAreas
            # rearrange first
            for k, v in openQs.openQcoords.items():
                self.qAreas[k] = ((v[0],v[1]),(v[2], v[3]))
            # add openQ results to regular results
            self.resdf = pd.concat([self.resdf, openQs.openQres], axis=1)
        
        # Embed OCR transcription text into open-Q cells for human readability
        if self.openQ and openQs is not None:
            for qk, trans_dict in openQs._transcriptions.items():
                if qk not in self.resdf.columns:
                    continue
                for img_idx, trans_val in trans_dict.items():
                    if img_idx == 0 or img_idx not in self.resdf.index:
                        continue
                    text = trans_val[0] if trans_val else ''
                    if not text:
                        continue
                    grade = str(self.resdf.loc[img_idx, qk])
                    if grade in ('CC', 'CX', 'XX'):
                        self.resdf.loc[img_idx, qk] = f'{grade}: {text}'

        # Save key CSV — bubble answers from key row 0 + open-ended coords/answers
        # This file can be loaded next time in the Key File field to skip re-scanning the key.
        from openQ import save_key_file as _save_key_file
        _bubble_ans = {}
        for col in self.resdf.columns:
            if col.startswith('Q') and col[1:].isdigit():
                val = str(self.resdf.loc[0, col])
                if val and val not in ('', '-'):
                    _bubble_ans[col] = val
        _open_qs = {}
        if self.openQ and openQs is not None:
            for qk, coords in openQs.openQcoords.items():
                _open_qs[qk] = {
                    'full': openQs.acceptable_answers.get(qk, []),
                    'partial': openQs.partial_credit_answers.get(qk, []),
                    'coords': list(coords),
                    'page': 1,
                }
        _key_csv_path = str(self.outdir / 'exam_key.csv')
        _skip_str = ','.join(str(n) for n in self.ignores) if self.ignores else ''
        try:
            _save_key_file(_key_csv_path, {
                'bubble_answers': _bubble_ans,
                'open_questions': _open_qs,
                'metadata': {
                    'num_questions': self.quests,
                    'questions_to_skip': _skip_str,
                },
            })
            print(f'[Scanner] Key saved → {_key_csv_path}', flush=True)
            print('[Scanner] Load this file in "Key File" next time to skip re-scanning the key sheet.', flush=True)
        except Exception as _exc:
            print(f'[Scanner] Could not save key CSV: {_exc}', flush=True)

        # write resdf to csv
        self.resCsv = str(self.outdir / 'results.csv')
        self.resdf.to_csv(self.resCsv, index=True, index_label = 'index')

        # Save acceptable answers, transcriptions, and grade config for post-session re-grading
        if self.openQ and openQs is not None:
            openQs.save_artifacts(
                self.resCsv,
                grade_config={
                    'bubbleVal': self.bubbleVal,
                    'openVal': self.openVal,
                    'selectAll': self.markmissing,
                }
            )
        
        # grade the results csv file and save out pts per question csv file
        grade_functions.gradeResults(self.resCsv, self.markmissing, self.openQ, self.bubbleVal, self.openVal, self.markeddir, self.strictness)
        
        # mark questions
        if self.save_marked:
            keyname = grade_functions.markSheets(self.resCsv, self.aligned_image_list, self.markeddir, self.qAreas, self.Qdict, self.markmissing, self.corrMark)
            # intialize the output pdf
            print('Saving marked files')
            self.outpdf=FPDF('P','pt','Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, keyname)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))
        print('All steps complete!')

    def _run_with_key_file(self):
        """Scan all images as students; populate key row 0 from the JSON key file."""
        # 1. Populate resdf row 0 from bubble_answers in the key file
        self.resdf.loc[0, 'LastName'] = 'KEY'
        self.resdf.loc[0, 'FirstName'] = ''
        self.resdf.loc[0, 'studentID'] = ''
        for qk, ans in self._key_data.get('bubble_answers', {}).items():
            if qk in self.resdf.columns:
                self.resdf.loc[0, qk] = ans
            else:
                print(f'[KeyFile] Column "{qk}" not in resdf (ignored).', flush=True)
        # Mark ignored questions
        if self.ignores:
            for q_num in self.ignores:
                qk = 'Q' + format(q_num, '03d')
                if qk in self.resdf.columns:
                    self.resdf.loc[0, qk] = 'ignore'

        # 2. Scan all images; for multi-page, only run MC bubble scan on first page per student
        pps = self.pages_per_student
        for i in range(len(self.image_list)):
            img = Image(self.image_list[i], self.scan_settings)
            print('Processing scan {:1d}'.format(i + 1))
            scan_functions.saveimg(i + 1, img.aligned, self.aligneddir)
            page_within = i % pps
            if page_within == 0:   # first page per student — scan MC bubbles
                student_row = i // pps + 1
                self.qRes = scan_functions.rundots(
                    img.scanimg,
                    self.qAreas, self.idAreas, self.nAreas,
                    self.ignores,
                    self.Qdict, self.Idict, self.Ndict)
                for k, v in self.qRes.items():
                    self.resdf.loc[student_row, k] = v

        # 3. Build sorted aligned_image_list (all student images)
        # Only include files numbered 1..N that we just wrote; ignore any
        # stale aligned_000.jpg left over from a previous scan-key-mode run.
        n_scanned = len(self.image_list)
        self.aligned_image_list = sorted(
            str(self.aligneddir / f'aligned_{i:03d}.jpg')
            for i in range(1, n_scanned + 1)
            if (self.aligneddir / f'aligned_{i:03d}.jpg').exists())

        # 4. Open-ended grading — pass [None] + students so index 0 = synthetic key row
        openQs = None
        if self.openQ:
            padded_list = [None] + self.aligned_image_list
            openQs = OpenQs(
                padded_list,
                parent=self.parent,
                ai_ocr=self.ai_ocr,
                api_key=self.api_key,
                ai_context=self.ai_context,
                preloaded_file=self.preloaded_file,
                review_perfect=self.review_perfect,
                key_file_data=self._key_data,
                key_file_path=self.key_file_path,
                pages_per_student=self.pages_per_student,
                ignores=self.ignores,
            )
            for k, v in openQs.openQcoords.items():
                self.qAreas[k] = ((v[0], v[1]), (v[2], v[3]))
            self.resdf = pd.concat([self.resdf, openQs.openQres], axis=1)
            # Re-save key file with any answers the grader typed in during review
            if self.key_file_path:
                try:
                    from openQ import load_key_file as _lkf, save_key_file as _skf
                    _kd = _lkf(self.key_file_path) or {}
                    for _qk, _oq in _kd.get('open_questions', {}).items():
                        if openQs.acceptable_answers.get(_qk):
                            _oq['full'] = list(openQs.acceptable_answers[_qk])
                        if openQs.partial_credit_answers.get(_qk):
                            _oq['partial'] = list(openQs.partial_credit_answers[_qk])
                    _skf(self.key_file_path, _kd)
                    print(f'[Scanner] Key file updated with graded answers → {self.key_file_path}', flush=True)
                except Exception as _exc:
                    print(f'[Scanner] Could not update key file: {_exc}', flush=True)

        # 5. Embed OCR transcriptions
        if self.openQ and openQs is not None:
            for qk, trans_dict in openQs._transcriptions.items():
                if qk not in self.resdf.columns:
                    continue
                for img_idx, trans_val in trans_dict.items():
                    if img_idx == 0 or img_idx not in self.resdf.index:
                        continue
                    text = trans_val[0] if trans_val else ''
                    if not text:
                        continue
                    grade = str(self.resdf.loc[img_idx, qk])
                    if grade in ('CC', 'CX', 'XX'):
                        self.resdf.loc[img_idx, qk] = f'{grade}: {text}'

        # 6. Write CSV
        self.resCsv = str(self.outdir / 'results.csv')
        self.resdf.to_csv(self.resCsv, index=True, index_label='index')

        # 7. Save artifacts
        if self.openQ and openQs is not None:
            openQs.save_artifacts(
                self.resCsv,
                grade_config={
                    'bubbleVal': self.bubbleVal,
                    'openVal': self.openVal,
                    'selectAll': self.markmissing,
                })

        # 8. Grade
        _point_values = self._key_data.get('point_values') if self._key_data else None
        grade_functions.gradeResults(
            self.resCsv, self.markmissing, self.openQ,
            self.bubbleVal, self.openVal, self.markeddir, self.strictness,
            point_values=_point_values)

        # 9. Mark sheets — [None] + first page per student so row indices align with resdf
        #    aligned_image_list[::pps] picks the first page for each student
        #    (pps=1 degenerates to all images — fully backward compatible)
        if self.save_marked:
            first_page_imgs = self.aligned_image_list[::self.pages_per_student]
            marked_list = [None] + first_page_imgs
            keyname = grade_functions.markSheets(
                self.resCsv, marked_list, self.markeddir,
                self.qAreas, self.Qdict, self.markmissing, self.corrMark)

            # 10. Save PDF
            print('Saving marked files')
            self.outpdf = FPDF('P', 'pt', 'Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, keyname)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))
        print('All steps complete!')


