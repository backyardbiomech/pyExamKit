from fpdf import FPDF
import sys
import os
import fnmatch
import pandas as pd
import ast
from pathlib import Path
import numpy as np
from PIL import Image as PILImage

from settings import Settings
from image import Image
import init_functions
import scan_functions
import bubbles
import sheet_layout
import roster as roster_mod
import practical
import practical_scan
import grade_functions
from openQ import OpenQs
from keyformat import load_key_file, save_key_file
import outputs


class Scanner(object):
    '''
    Scanner is the main class that contains scanner settings from the GUI,
    lists of image files,
    aligment matrices,
    grade sheet file names,
    and panda data tables for grading
    '''
    
    def __init__(self, input_file, quests, markmissing, openQ, corrmark, ignores, thresh, bubbleVal, openVal, parent=None, ai_ocr=False, api_key='', ai_context='', preloaded_file: str = '', review_perfect: bool = True, key_file_path: str = '', pages_per_student: int = 1, save_marked: bool = True, strictness: float = 0.5, version_question: int = 0, version_key_paths: dict | None = None, reuse_aligned: bool = False, roster_path: str = ''):
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
        thresh is the fill cutoff: the fraction of each student's own typical
        mark a bubble must reach to count as filled (see bubbles.py)
        version_question is the question row holding the version letter; 0
        reads the version bubbles printed in the header of a v2 sheet
        roster_path is an optional class roster CSV used to fill in names by ID
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
        self.reuse_aligned = reuse_aligned
        # ── Multi-version support ──────────────────────────────────────────────
        self.version_question = version_question
        self.version_keys: dict[str, dict] = {}
        self.version_key_paths: dict[str, str] = {}
        if version_key_paths:
            for _ver, _vpath in version_key_paths.items():
                if _vpath:
                    _vkd = load_key_file(_vpath)
                    if _vkd:
                        self.version_keys[_ver.upper()] = _vkd
                        self.version_key_paths[_ver.upper()] = _vpath
                    else:
                        print(f'[Scanner] Warning: could not load key for version {_ver}: {_vpath}',
                              flush=True)
        self._key_data = None
        if key_file_path:
            self._key_data = load_key_file(key_file_path)
            if self._key_data is None:
                print(f'[Scanner] Warning: failed to load key file "{key_file_path}". '
                      'Falling back to scan-key mode.', flush=True)
                self.key_file_path = ''
        # Question grids for sheets printed with rows grouped by question,
        # by version letter ('' for a single key); see bubbles.read_sheet
        self._keyed = {}
        for _ver, _kd in ([('', self._key_data)] if self._key_data else []) + \
                list(self.version_keys.items()):
            _runs = (_kd or {}).get('metadata', {}).get('sheet_rows')
            if _runs:
                self._keyed[_ver] = sheet_layout.keyed_layout(
                    sheet_layout.parse_columns(_runs))
        if len(ignores)>0:
            ignores=ignores+','
            self.ignores=list(ast.literal_eval(ignores))
        else:
            self.ignores=None
        # pull settings into scanner object
        self.scan_settings=Settings()
        self.cutoff = thresh
        # What the reader found on each scanned row: layout, flags, version
        self.reads: dict[int, bubbles.SheetRead] = {}
        self.roster = None
        if roster_path:
            try:
                self.roster, _desc = roster_mod.load_roster(roster_path)
                print(f'[Roster] {_desc}', flush=True)
            except roster_mod.RosterError as exc:
                print(f'[Roster] Not used: {exc}', flush=True)
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
        if self.reuse_aligned:
            _existing = sorted(self.aligneddir.glob('aligned_*.jpg'))
            if not _existing:
                print('[Scanner] reuse_aligned: no aligned images found in '
                      f'{self.aligneddir} — falling back to full scan.', flush=True)
                self.reuse_aligned = False
            else:
                self.image_list = [str(p) for p in _existing]
                print(f'[Scanner] Re-using {len(self.image_list)} existing aligned images. '
                      'Skipping PDF split and alignment.', flush=True)
        if not self.reuse_aligned:
            self.image_list = init_functions.filenames(
                input_file, scan_jpgs_dir=self.app_data_dir / 'scanJPGs')
        # intialize the output pdf which the scanner object will write to
        self.outpdf=FPDF('P','pt','Letter')
        # initialize the pandas dataframe to contain results
        # In key-file mode we need one extra row for the synthetic key row 0.
        # For multi-page, there are pages_per_student images per student.
        if (self.key_file_path and self._key_data) or self.version_keys:
            n_actual_students = len(self.image_list) // self.pages_per_student
            n_rows = n_actual_students + 1  # +1 for placeholder row 0
        elif self.pages_per_student > 1:
            # scan-key mode, multi-page: index 0 is the key (1 page), rest are student pages
            n_rows = (len(self.image_list) - 1) // self.pages_per_student + 1
        else:
            n_rows = len(self.image_list)
        self.resdf = init_functions.makeResDf(quests, n_rows)
        # Question rectangles for marking; rows on another layout override
        # these per row (see _row_areas)
        self.qAreas = sheet_layout.CLASSIC.q_areas(quests)
        # make the dictionaries to convert coordinates to letters or numbers
        self.Ndict, self.Idict, self.Qdict = init_functions.makeResDict()
        self.run()
        
    def _load_aligned(self, path):
        """Load a saved aligned JPEG. Used in reuse_aligned mode, which skips
        registration and warping."""
        with PILImage.open(path) as pil:
            return np.array(pil.convert('RGB'))

    def _read(self, row, aligned, layout=None, answers_only=False):
        """Read one sheet's bubbles into resdf row `row`. answers_only keeps
        the name and ID already there, which the roster may have replaced."""
        r = bubbles.read_sheet(aligned, self.quests, self.ignores, self.cutoff,
                               layout=layout, keyed=self._keyed)
        self.reads[row] = r
        for k, v in r.answers.items():
            if answers_only and not k.startswith('Q'):
                continue
            self.resdf.loc[row, k] = v

    def _alert(self, line):
        alert_path = self.outdir / 'ALERT.txt'
        with open(alert_path, 'a') as f:
            if alert_path.stat().st_size:
                f.write('\n')
            f.write(line)

    def _apply_roster(self, skip_rows=()):
        """Replace bubbled names with roster names, matched by ID."""
        if not self.roster:
            return
        seen: dict[str, int] = {}
        for row in sorted(self.reads):
            if row in skip_rows:
                continue
            scanned = str(self.resdf.loc[row, 'studentID'])
            student, note = roster_mod.match_id(scanned, self.roster)
            if student is None:
                self._alert(f'ROSTER: scan {row} (ID read as {scanned}, name bubbles '
                            f'"{self.resdf.loc[row, "LastName"]}"): {note}. Check the '
                            'handwritten name on the marked sheet.')
                continue
            self.resdf.loc[row, 'LastName'] = student.last
            self.resdf.loc[row, 'FirstName'] = student.first
            self.resdf.loc[row, 'studentID'] = student.id
            if note:
                self._alert(f'ROSTER: scan {row} ({student.last}, {student.first}): '
                            f'ID read as {scanned}, {note}.')
            if student.id in seen:
                self._alert(f'ROSTER: scans {seen[student.id]} and {row} both read as '
                            f'ID {student.id} ({student.last}, {student.first}).')
            seen.setdefault(student.id, row)

    def _write_read_alerts(self):
        """Report marks the reader could not call confidently."""
        for row in sorted(self.reads):
            r = self.reads[row]
            who = (f'scan {row} ({self.resdf.loc[row, "LastName"]}, '
                   f'{self.resdf.loc[row, "FirstName"]}, ID {self.resdf.loc[row, "studentID"]})')
            if r.fill_level < bubbles.LIGHT_SHEET:
                self._alert(f'LIGHT MARKS: {who}: marks are very light; check this sheet by eye.')
            for f in r.flags:
                self._alert(f'CHECK MARK: {who}: {f.field} bubble {f.label} {f.reason}.')

    def _row_areas(self, row_map):
        """Per-row question areas and flags for markSheets, keyed by csv row.
        row_map maps csv row string -> resdf row."""
        areas, flags = {}, {}
        for row_str, row in row_map.items():
            r = self.reads.get(row)
            if r is None:
                continue
            if r.layout is not sheet_layout.CLASSIC:
                areas[row_str] = r.layout.q_areas(self.quests)
            flags[row_str] = [f for f in r.flags if f.field.startswith('Q')]
        return areas, flags

    def run(self):
        if self._key_data and self._key_data.get('metadata', {}).get('practical'):
            self._run_practical()
        elif self.version_keys:
            self._run_multi_version()
        elif self.key_file_path and self._key_data:
            self._run_with_key_file()
        else:
            self._run_scan_key()

    def _ask_version_for_student(self, row_idx: int, name: str,
                                   raw_ver: str, img_path: str | None) -> str | None:
        """Show a dialog with the student's aligned scan and ask the user to
        manually select an exam version.  Returns a version letter (e.g. 'A')
        from self.version_keys, or None to skip the student."""
        import tkinter as tk
        from PIL import ImageTk, Image as _PILImage

        result = [None]
        win = tk.Toplevel(self.parent)
        win.title(f'Unknown version — row {row_idx}: {name}')
        win.transient(self.parent)
        win.grab_set()
        win.lift()
        win.focus_force()

        tk.Label(win,
                 text=f'Student row {row_idx}:  {name}',
                 font=('Arial', 13, 'bold')).pack(pady=(10, 2))
        tk.Label(win,
                 text=f'Version bubble not detected  (scanned: "{raw_ver}")\n'
                      'Select the correct version or click Skip to exclude this student:',
                 font=('Arial', 11), justify='center').pack(pady=(0, 8))

        if img_path:
            try:
                with _PILImage.open(img_path) as pil_img:
                    max_w, max_h = 620, 780
                    ratio = min(max_w / pil_img.width, max_h / pil_img.height, 1.0)
                    disp = pil_img.resize(
                        (int(pil_img.width * ratio), int(pil_img.height * ratio)),
                        _PILImage.LANCZOS)
                photo = ImageTk.PhotoImage(disp)
                img_lbl = tk.Label(win, image=photo)
                img_lbl.image = photo  # prevent GC
                img_lbl.pack(padx=8, pady=(0, 8))
            except Exception as _e:
                tk.Label(win, text=f'(Could not load image: {_e})',
                         fg='gray').pack()

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=(4, 12))

        def _choose(v):
            result[0] = v
            win.destroy()

        for ver in sorted(self.version_keys):
            tk.Button(btn_frame, text=f'Version {ver}', width=12,
                      font=('Arial', 12),
                      command=lambda v=ver: _choose(v)).pack(side='left', padx=6)
        tk.Button(btn_frame, text='Skip', width=8, font=('Arial', 12),
                  fg='gray', command=lambda: _choose(None)).pack(side='left', padx=10)

        win.wait_window()
        return result[0]

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
            if self.reuse_aligned:
                print(f'Re-reading {i + 1}')
                aligned = self._load_aligned(self.image_list[i])
            else:
                img = Image(self.image_list[i], self.scan_settings)
                print(f'Processing scan {i + 1}')
                scan_functions.saveimg(i + 1, img.aligned, self.aligneddir)
                aligned = img.aligned
            if i % pps == 0:   # first page per student — scan MC bubbles
                self._read(i // pps + 1, aligned)
        self._apply_roster()
        self._write_read_alerts()

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
            if not self.version_question:
                # v2 sheets print their own version bubbles in the header
                _r = self.reads.get(row_idx)
                raw_ver = _r.version if _r is not None else '-'
            elif ver_qk in self.resdf.columns:
                raw_ver = str(self.resdf.loc[row_idx, ver_qk]).strip()
            else:
                raw_ver = '-'
            ver_letter = raw_ver[0].upper() if raw_ver and raw_ver != '-' else None
            if ver_letter and ver_letter in self.version_keys:
                version_groups.setdefault(ver_letter, []).append(row_idx)
            else:
                name = self.resdf.loc[row_idx, 'LastName']
                print(f'[MultiVersion] WARNING — Student row {row_idx} ({name}) version '
                      f'bubble not detected (scanned: "{raw_ver}").', flush=True)
                # Try to get the aligned image for this student
                img_idx = (row_idx - 1) * pps
                img_path = (self.aligned_image_list[img_idx]
                            if 0 <= img_idx < len(self.aligned_image_list) else None)
                chosen = None
                if self.parent is not None:
                    chosen = self._ask_version_for_student(row_idx, name, raw_ver, img_path)
                if chosen:
                    print(f'[MultiVersion] Student row {row_idx} ({name}) manually '
                          f'assigned to version {chosen}.', flush=True)
                    version_groups.setdefault(chosen, []).append(row_idx)
                    # A grouped-row sheet was read with a guessed grid; read
                    # it again with the grid of the version now known.
                    _r = self.reads.get(row_idx)
                    _grid = self._keyed.get(chosen)
                    if (_r is not None and _grid is not None and img_path
                            and _r.layout.code == _grid.code
                            and _r.layout.columns != _grid.columns):
                        self._read(row_idx, self._load_aligned(img_path), layout=_grid,
                                   answers_only=True)
                else:
                    print(f'[MultiVersion] Student row {row_idx} ({name}) skipped — '
                          'will NOT appear in any output.', flush=True)
                    alert_path = self.outdir / 'ALERT.txt'
                    alert_line = (f'MISSING VERSION: Student row {row_idx} ({name}) '
                                  f'— version bubble not detected (raw: "{raw_ver}") '
                                  f'— excluded from all results.')
                    if not alert_path.exists():
                        alert_path.write_text(alert_line)
                    else:
                        with open(alert_path, 'a') as _af:
                            _af.write('\n')
                            _af.write(alert_line)

        if not version_groups:
            print('[MultiVersion] No students matched any loaded version key. '
                  'Check the version question number and key files.', flush=True)
            return

        # 4. Grade (and optionally mark) each version group separately, into
        #    one set of outputs
        ver_csvs = []
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

            # Every page of this version's students, after a None for the key
            # row, which is the layout the grader and the marker expect
            imgs_for_ver = []
            for orig_row in row_indices:
                first = (orig_row - 1) * pps  # 0-based into aligned_image_list
                imgs_for_ver += self.aligned_image_list[first:first + pps]
            ver_csv = outputs.results_csv(self.outdir, ver)
            ver_csvs.append(ver_csv)

            # Written answers, graded against this version's key: its boxes
            # and accepted answers can differ from another version's.
            openQs = None
            if self.openQ:
                print(f'[MultiVersion] Version {ver}: written answers.', flush=True)
                openQs = self._grade_written([None] + imgs_for_ver, kd,
                                             self.version_key_paths.get(ver, ''), ver_csv)
            ver_areas = dict(self.qAreas)
            q_pages = {}
            if openQs is not None:
                for k, v in openQs.openQcoords.items():
                    ver_areas[k] = ((v[0], v[1]), (v[2], v[3]))
                q_pages.update(openQs._q_pages)
                sub_df = self._with_written(sub_df, openQs)

            # Save version-specific results CSV
            sub_df.to_csv(ver_csv, index=True, index_label='index')
            if openQs is not None:
                openQs.save_artifacts(ver_csv, grade_config={
                    'bubbleVal': self.bubbleVal, 'openVal': self.openVal,
                    'selectAll': self.markmissing,
                    'point_values': kd.get('point_values') or None})

            _point_values = kd.get('point_values')
            grade_functions.gradeResults(
                ver_csv, self.markmissing, openQs is not None,
                self.bubbleVal, self.openVal, self.markeddir, self.strictness,
                point_values=_point_values, key_data=kd)

            # Mark sheets if requested; every version's go in marked/
            if self.save_marked:
                marked_list = [None] + imgs_for_ver  # None at [0] = synthetic key placeholder
                _areas, _flags = self._row_areas(
                    {str(j + 1): orig for j, orig in enumerate(row_indices)})
                grade_functions.markSheets(
                    ver_csv, marked_list, self.markeddir,
                    ver_areas, self.Qdict, self.markmissing, self.corrMark,
                    pages_per_student=pps, q_pages=q_pages,
                    row_areas=_areas, flags=_flags)

        if self.save_marked:
            print('Saving marked files')
            self.outpdf = FPDF('P', 'pt', 'Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, None)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))

        outputs.record(self.outdir, ver_csvs)
        outputs.write(self.outdir)

        print('All steps complete!')

    def _run_scan_key(self):
        # Run the scanner on each file
        # will scan dots and save out aligned image for future use)
        pps = self.pages_per_student
        for i in range(len(self.image_list)):
            is_first_page = (i == 0 or (i - 1) % pps == 0)
            if self.reuse_aligned:
                if not is_first_page:
                    continue  # aligned images already exist; only scan first page per student
                print('Re-reading {0:1d}'.format(i))
                aligned = self._load_aligned(self.image_list[i])
            else:
                # create image object, which will load and align image
                img = Image(self.image_list[i], self.scan_settings)
                print('Processing scan {0:1d}'.format(i))
                #save the aligned image aligned_00i.jpg in ./aligned
                scan_functions.saveimg(i, img.aligned, self.aligneddir)
                if not is_first_page:
                    continue  # aligned image saved; only scan first page per student
                aligned = img.aligned
            # For multi-page: only run bubble scan on key (i=0) and first page per student
            if i == 0 or (i - 1) % pps == 0:
                self._read(0 if i == 0 else (i - 1) // pps + 1, aligned)
        if 0 in self.reads and self.reads[0].layout is not sheet_layout.CLASSIC:
            self.resdf.loc[0, 'LastName'] = 'KEY'   # no name bubbles to write it in
        self._apply_roster(skip_rows=(0,))
        self._write_read_alerts()
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
                            pages_per_student=pps,
                            ignores=self.ignores,
                            strictness=self.strictness,
                            output_csv_path=outputs.results_csv(self.outdir))
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
        # Carry per-question points through from the loaded key. This file is
        # advertised below as reusable in the Key File field, so dropping them
        # here would silently regrade every question at the flat bubble value
        # the next time it is used.
        _point_values = self._key_data.get('point_values') if self._key_data else None
        try:
            save_key_file(_key_csv_path, {
                'bubble_answers': _bubble_ans,
                'open_questions': _open_qs,
                'point_values': _point_values or {},
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
        self.resCsv = outputs.results_csv(self.outdir)
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
        outputs.record(self.outdir, [self.resCsv])
        outputs.write(self.outdir)
        
        # mark questions
        if self.save_marked:
            # Build q_pages: open-ended questions may be on page > 1
            q_pages = {}
            if self.openQ and openQs is not None:
                q_pages.update(openQs._q_pages)
            _areas, _flags = self._row_areas({str(r): r for r in self.reads})
            # Pass the full aligned_image_list so markSheets can access all pages per student.
            # Layout: [0]=key page, [(r-1)*pps+1 .. r*pps]=student r's pages (r 1-based)
            keyname = grade_functions.markSheets(
                self.resCsv, self.aligned_image_list, self.markeddir,
                self.qAreas, self.Qdict, self.markmissing, self.corrMark,
                pages_per_student=pps, q_pages=q_pages,
                row_areas=_areas, flags=_flags)
            # intialize the output pdf
            print('Saving marked files')
            self.outpdf=FPDF('P','pt','Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, keyname)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))
        print('All steps complete!')

    def _grade_written(self, image_list, key_data, key_path, csv_path, **where):
        """Grade the written answers of the students in image_list ([None]
        then each student's pages) against one key. Returns the grader, or
        None when the key has no written questions. `where` passes OpenQs its
        locate and student_info hooks, for sheets whose boxes vary by student."""
        if not key_data.get('open_questions'):
            return None
        openQs = OpenQs(
            image_list,
            parent=self.parent,
            ai_ocr=self.ai_ocr,
            api_key=self.api_key,
            ai_context=self.ai_context,
            preloaded_file=self.preloaded_file,
            review_perfect=self.review_perfect,
            key_file_data=key_data,
            key_file_path=key_path,
            pages_per_student=self.pages_per_student,
            ignores=self.ignores,
            strictness=self.strictness,
            output_csv_path=csv_path,
            **where,
        )
        # Re-save the key with any answers the grader accepted during review
        if key_path:
            try:
                _kd = load_key_file(key_path) or {}
                if not _kd:
                    print('[Scanner] Key file re-read returned empty — skipping '
                          'answer update to avoid overwriting existing data.',
                          flush=True)
                    raise ValueError('empty key file re-read')
                for _qk, _oq in _kd.get('open_questions', {}).items():
                    if openQs.acceptable_answers.get(_qk):
                        _oq['full'] = list(openQs.acceptable_answers[_qk])
                    if openQs.partial_credit_answers.get(_qk):
                        _oq['partial'] = list(openQs.partial_credit_answers[_qk])
                save_key_file(key_path, _kd)
                print(f'[Scanner] Key file updated with graded answers → {key_path}', flush=True)
            except Exception as _exc:
                print(f'[Scanner] Could not update key file: {_exc}', flush=True)
        return openQs

    @staticmethod
    def _with_written(df, openQs):
        """df with the written grades joined on, each followed by its
        transcription (CC: stratum basale)."""
        res = openQs.openQres.copy()
        res.index = [type(df.index[0])(i) for i in res.index] if len(df.index) else res.index
        df = pd.concat([df, res], axis=1)
        for qk, trans_dict in openQs._transcriptions.items():
            if qk not in df.columns:
                continue
            for img_idx, trans_val in trans_dict.items():
                row = type(df.index[0])(img_idx)
                if img_idx == 0 or row not in df.index:
                    continue
                text = trans_val[0] if trans_val else ''
                grade = str(df.loc[row, qk])
                if text and grade in ('CC', 'CX', 'XX'):
                    df.loc[row, qk] = f'{grade}: {text}'
        return df

    def _run_practical(self):
        """
        Grade a lab practical: every form in one stack, against the one key
        the practical's source file is. See practical_scan.py.
        """
        p = practical.load(self.key_file_path)
        n_pages = sheet_layout.practical_pages(len(p.stations))
        self.pages_per_student = n_pages

        # 1. Align every page and read what it is; read the ID on each page 1
        reads, id_reads = [], {}
        blank = 0
        for i, path in enumerate(self.image_list):
            aligned_path = str(self.aligneddir / f'aligned_{i + 1:03d}.jpg')
            # The blank back of a sheet printed on both sides
            if not self.reuse_aligned and practical_scan.is_blank(path):
                blank += 1
                continue
            try:
                if self.reuse_aligned:
                    print(f'Re-reading {i + 1}')
                    aligned = self._load_aligned(path)
                    aligned_path = path
                else:
                    print(f'Processing scan {i + 1}')
                    aligned = Image(path, self.scan_settings).aligned
                    scan_functions.saveimg(i + 1, aligned, self.aligneddir)
            except ValueError as exc:
                print(f'[Practical] Scan {i + 1}: {exc}', flush=True)
                reads.append(practical_scan.PageRead(i + 1, 0, '', None))
                continue
            gray = bubbles.to_gray(aligned)
            lay = sheet_layout.detect_layout(gray)
            page = lay.practical_page
            form = sheet_layout.read_form(gray) if page else ''
            reads.append(practical_scan.PageRead(i + 1, page, form, aligned_path))
            if page == 1:
                id_reads[i + 1] = bubbles.read_sheet(aligned, 0, self.ignores, self.cutoff,
                                                     layout=lay)
        if blank:
            print(f'[Practical] Skipped {blank} blank page(s), the backs of sheets.', flush=True)
        sheets, alerts = practical_scan.group_pages(reads, n_pages)
        for a in alerts:
            self._alert(a)
        if not sheets:
            print('[Practical] No practical form sheets were found in the scans.', flush=True)
            return
        print(f'[Practical] {len(sheets)} students, forms: '
              + ', '.join(f'{f} {sum(s.form == f for s in sheets)}'
                          for f in sorted({s.form for s in sheets})), flush=True)

        # 2. One row per student, with their form; row 0 is the key
        self.resdf = pd.DataFrame('', index=range(len(sheets) + 1),
                                  columns=['LastName', 'FirstName', 'studentID', 'form'])
        self.resdf.loc[0] = ['KEY', '', '', 'ignore']
        self.reads = {}
        for row, sheet in enumerate(sheets, 1):
            r = id_reads[sheet.first_scan]
            self.reads[row] = r
            for col in ('LastName', 'FirstName', 'studentID'):
                self.resdf.loc[row, col] = r.answers[col]
            self.resdf.loc[row, 'form'] = sheet.form
        self._apply_roster()
        self._write_read_alerts()
        for row, sheet in enumerate(sheets, 1):
            problems = sheet.notes + [practical_scan.form_problem(sheet.form, p)]
            for note in filter(None, problems):
                self._alert(f'PRACTICAL: scan {sheet.first_scan} '
                            f'({self._who(row)}): {note}.')

        # 3. Written answers, station by station, each across the students who have it
        labels = [self._who(row) + f'  ·  form {s.form}' for row, s in enumerate(sheets, 1)]
        image_list = [None] + [r.path if r else None for s in sheets for r in s.pages]
        csv_path = outputs.results_csv(self.outdir)
        openQs = self._grade_written(
            image_list, self._key_data, self.key_file_path, csv_path,
            locate=practical_scan.make_locate(sheets, len(p.stations)),
            student_info=practical_scan.make_student_info(sheets, labels))
        self.resdf = self._with_written(self.resdf, openQs)

        # 4. Results, points, Canvas file
        self.resCsv = csv_path
        self.resdf.to_csv(self.resCsv, index=True, index_label='index')
        point_values = self._key_data.get('point_values')
        openQs.save_artifacts(self.resCsv, grade_config={
            'bubbleVal': self.bubbleVal, 'openVal': self.openVal,
            'selectAll': self.markmissing, 'point_values': point_values,
            'key_file': str(Path(self.key_file_path).resolve())})
        grade_functions.gradeResults(self.resCsv, self.markmissing, True, self.bubbleVal,
                                     self.openVal, self.markeddir, self.strictness,
                                     point_values=point_values, key_data=self._key_data)
        outputs.record(self.outdir, [self.resCsv])
        outputs.write(self.outdir)

        # 5. Marked sheets
        if self.save_marked:
            graded = pd.read_csv(self.resCsv, dtype=object).set_index('index')
            practical_scan.mark_sheets(graded, sheets, p, self.markeddir,
                                       grade_functions._get_font(40),
                                       grade_functions._get_font(28))
            print('Saving marked files')
            self.outpdf = FPDF('P', 'pt', 'Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, None)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))
        print('All steps complete!')

    def _who(self, row) -> str:
        '''A student as the grader and ALERT.txt name them: roster name, else the ID.'''
        last, first, sid = (str(self.resdf.loc[row, c])
                            for c in ('LastName', 'FirstName', 'studentID'))
        if last not in ('', '-', 'nan'):
            return f'{last}, {first}'.strip(', ')
        return f'ID {sid}'

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
            is_first_page = (i % pps == 0)
            if self.reuse_aligned:
                if not is_first_page:
                    continue  # aligned images already exist; only scan first page per student
                print('Re-reading {:1d}'.format(i + 1))
                aligned = self._load_aligned(self.image_list[i])
            else:
                img = Image(self.image_list[i], self.scan_settings)
                print('Processing scan {:1d}'.format(i + 1))
                scan_functions.saveimg(i + 1, img.aligned, self.aligneddir)
                if not is_first_page:
                    continue  # aligned image saved; only scan first page per student
                aligned = img.aligned
            page_within = i % pps
            if page_within == 0:   # first page per student — scan MC bubbles
                self._read(i // pps + 1, aligned)
        self._apply_roster()
        self._write_read_alerts()

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
            openQs = self._grade_written([None] + self.aligned_image_list, self._key_data,
                                         self.key_file_path, outputs.results_csv(self.outdir))
        if openQs is not None:
            for k, v in openQs.openQcoords.items():
                self.qAreas[k] = ((v[0], v[1]), (v[2], v[3]))
            # 5. Join the written grades, with their transcriptions
            self.resdf = self._with_written(self.resdf, openQs)

        # 6. Write CSV
        self.resCsv = outputs.results_csv(self.outdir)
        self.resdf.to_csv(self.resCsv, index=True, index_label='index')

        # 7. Save artifacts
        if openQs is not None:
            openQs.save_artifacts(
                self.resCsv,
                grade_config={
                    'bubbleVal': self.bubbleVal,
                    'openVal': self.openVal,
                    'selectAll': self.markmissing,
                    'point_values': (self._key_data or {}).get('point_values') or None,
                })

        # 8. Grade
        _point_values = self._key_data.get('point_values') if self._key_data else None
        grade_functions.gradeResults(
            self.resCsv, self.markmissing, openQs is not None,
            self.bubbleVal, self.openVal, self.markeddir, self.strictness,
            point_values=_point_values, key_data=self._key_data)
        outputs.record(self.outdir, [self.resCsv])
        outputs.write(self.outdir)

        # 9. Mark sheets — None at [0] for synthetic key row, then all student pages in order
        if self.save_marked:
            # Build q_pages: open-ended questions may be on page > 1
            q_pages = {}
            if self.openQ and openQs is not None:
                q_pages.update(openQs._q_pages)
            # [None] at index 0 = synthetic key row (no image); then all student pages
            # Layout: [None, s1_p1, s1_p2, s2_p1, s2_p2, ...]
            marked_list = [None] + self.aligned_image_list
            _areas, _flags = self._row_areas({str(r): r for r in self.reads})
            keyname = grade_functions.markSheets(
                self.resCsv, marked_list, self.markeddir,
                self.qAreas, self.Qdict, self.markmissing, self.corrMark,
                pages_per_student=pps, q_pages=q_pages,
                row_areas=_areas, flags=_flags)

            # 10. Save PDF
            print('Saving marked files')
            self.outpdf = FPDF('P', 'pt', 'Letter')
            scan_functions.savePdf(self.markeddir, self.outpdf, keyname)
            self.outpdf.output(str(self.outdir / 'marked.pdf'))
        print('All steps complete!')


