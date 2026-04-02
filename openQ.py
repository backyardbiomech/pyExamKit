import base64
import csv
import io
import json
import numpy as np
import pandas as pd
import tkinter as tk
from pathlib import Path
from PIL import Image as PILImage, ImageDraw as PILImageDraw

from ocr import attempt_ocr, suggest_grade
import ai_ocr as _ai_ocr_mod


def load_acceptable_answers_file(path: str) -> tuple:
    """
    Parse a CSV or JSON file of pre-defined acceptable answers.
    Returns (full_credit, partial_credit) where each is {qk: [str, ...]}
    and qk is always 'openQ_N' form.
    Returns ({}, {}) on any error (logs to stdout).

    JSON format (per question):
      {"openQ_1": {"full": ["primary answer"], "partial": ["alias"]}}
      Old format {"openQ_1": ["answer"]} is still supported (all full credit).

    CSV long format (with optional 'credit' column):
      question, answer, credit   (credit = 'full' or 'partial'; default full)
    CSV wide format:
      question, answer1, answer2, ...   (all treated as full credit)
    """
    def _normalise_key(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith('openQ_'):
            return raw
        try:
            return 'openQ_' + str(int(raw))
        except ValueError:
            return 'openQ_' + raw

    p = Path(path)
    if not p.exists():
        print(f'[AccAnswers] File not found: {path}', flush=True)
        return {}, {}

    full_result: dict = {}
    partial_result: dict = {}
    try:
        if p.suffix.lower() == '.json':
            data = json.loads(p.read_text(encoding='utf-8'))
            for raw_key, answers in data.items():
                qk = _normalise_key(raw_key)
                if isinstance(answers, dict):
                    # New format: {"full": [...], "partial": [...]}
                    full_list = answers.get('full', [])
                    part_list = answers.get('partial', [])
                    if isinstance(full_list, list):
                        full_result[qk] = [str(a).strip() for a in full_list if str(a).strip()]
                    elif isinstance(full_list, str) and full_list.strip():
                        full_result[qk] = [full_list.strip()]
                    if isinstance(part_list, list):
                        partial_result[qk] = [str(a).strip() for a in part_list if str(a).strip()]
                    elif isinstance(part_list, str) and part_list.strip():
                        partial_result[qk] = [part_list.strip()]
                elif isinstance(answers, list):
                    # Old format: all full credit
                    full_result[qk] = [str(a).strip() for a in answers if str(a).strip()]
                elif isinstance(answers, str) and answers.strip():
                    full_result[qk] = [answers.strip()]
        else:
            # CSV — detect wide vs long by checking headers
            with open(p, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = [h.strip().lower() for h in (reader.fieldnames or [])]
                # Map lowercase header → original fieldname for case-insensitive lookup
                fieldname_map = {h.strip().lower(): h for h in (reader.fieldnames or [])}
                q_col = fieldname_map.get('question', 'question')
                if 'answer' in headers:
                    a_col = fieldname_map.get('answer', 'answer')
                    has_credit_col = 'credit' in headers
                    c_col = fieldname_map.get('credit', 'credit') if has_credit_col else None
                    # Long format: question, answer[, credit]
                    for row in reader:
                        raw_q = row.get(q_col, '').strip()
                        ans = row.get(a_col, '').strip()
                        if not raw_q or not ans:
                            continue
                        qk = _normalise_key(raw_q)
                        credit = row.get(c_col, 'full').strip().lower() if c_col else 'full'
                        if credit == 'partial':
                            partial_result.setdefault(qk, [])
                            if ans.lower() not in [a.lower() for a in partial_result[qk]]:
                                partial_result[qk].append(ans)
                        else:
                            full_result.setdefault(qk, [])
                            if ans.lower() not in [a.lower() for a in full_result[qk]]:
                                full_result[qk].append(ans)
                else:
                    # Wide format: question, answer1, answer2, ... (all full credit)
                    ans_cols = [h for h in (reader.fieldnames or [])
                                if h.strip().lower() != 'question']
                    for row in reader:
                        raw_q = row.get(q_col, '').strip()
                        if not raw_q:
                            continue
                        qk = _normalise_key(raw_q)
                        full_result.setdefault(qk, [])
                        for col in ans_cols:
                            val = row.get(col, '').strip()
                            if val and val.lower() not in [a.lower() for a in full_result[qk]]:
                                full_result[qk].append(val)
    except Exception as exc:
        print(f'[AccAnswers] Failed to parse {path}: {exc}', flush=True)
        return {}, {}

    total = len(set(list(full_result.keys()) + list(partial_result.keys())))
    print(f'[AccAnswers] Loaded pre-defined answers for {total} question(s).', flush=True)
    return full_result, partial_result


def _pil_to_tkphoto(pil_img, master=None):
    """Convert a PIL Image to tk.PhotoImage via PNG bytes (no _imagingtk needed)."""
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue())
    kwargs = {'data': b64}
    if master is not None:
        kwargs['master'] = master
    return tk.PhotoImage(**kwargs)


class OpenQs(object):
    '''
    Handles open-ended question area selection and grading using Tkinter windows.

    Usage (same external API as before):
        openQs = OpenQs(aligned_image_list, parent=root_tk_window)
        openQs.openQcoords   – dict of {question_key: (x1,y1,x2,y2)}
        openQs.openQres      – DataFrame of grades ('CC','CX','XX')
    '''

    def __init__(self, image_list, parent=None, ai_ocr=False, api_key='',
                 ai_context='', preloaded_file: str = '', review_perfect: bool = True):
        self.openQcoords = {}
        self.openQkeyimgs = {}
        self.openQkeytext = {}   # OCR text from each key crop
        self._ai_texts: dict[str, dict[int, str]] = {}  # {qkey: {img_idx: text}}
        self.acceptable_answers: dict[str, list] = {}   # {qk: [str, ...]}
        self.partial_credit_answers: dict[str, list] = {}  # {qk: [str, ...]}
        self._transcriptions: dict[str, dict] = {}      # {qk: {img_idx: (text, conf)}}
        self._preloaded_file = preloaded_file
        self._review_perfect = review_perfect

        # Obtain the Tkinter root window
        if parent is not None:
            self._root = parent
        else:
            self._root = tk._default_root
            if self._root is None:
                self._root = tk.Tk()
                self._root.withdraw()

        self._ai_ocr = ai_ocr   # used by _openQkey to skip TrOCR when Claude is active

        # Phase 1: let user draw boxes on the key image
        self._openQkey(image_list[0])

        if not self.openQcoords:
            # User closed without drawing anything
            cols = []
            self.openQres = pd.DataFrame(index=range(len(image_list)), columns=cols)
            return

        # Step 4a: seed acceptable_answers from key OCR and merge any pre-loaded file
        for qk, txt in self.openQkeytext.items():
            self.acceptable_answers[qk] = [txt] if txt else []

        preloaded: dict = {}
        preloaded_partial: dict = {}
        if self._preloaded_file:
            preloaded, preloaded_partial = load_acceptable_answers_file(self._preloaded_file)
            for qk, ans_list in preloaded.items():
                existing_lower = [a.lower() for a in self.acceptable_answers.get(qk, [])]
                for ans in ans_list:
                    if ans.lower() not in existing_lower:
                        self.acceptable_answers.setdefault(qk, []).append(ans)
                        existing_lower.append(ans.lower())
            for qk, ans_list in preloaded_partial.items():
                existing_lower = [a.lower() for a in self.partial_credit_answers.get(qk, [])]
                for ans in ans_list:
                    if ans.lower() not in existing_lower:
                        self.partial_credit_answers.setdefault(qk, []).append(ans)
                        existing_lower.append(ans.lower())
        if ai_ocr and len(image_list) > 1:
            # Ensure we have an API key — prompt on first use if missing
            if not api_key:
                api_key = _ai_ocr_mod.load_config().get('anthropic_api_key', '')
            if not api_key:
                api_key = self._prompt_api_key()
            if not api_key:
                print('[AI OCR] No API key provided — skipping AI OCR.', flush=True)
                ai_ocr = False
        if ai_ocr and len(image_list) > 1:
            print('[AI OCR] Running batch handwriting recognition…', flush=True)
            for qk, qv in self.openQcoords.items():
                crops, ids = [], []
                # Include key image as id '0' so all labels are numeric
                key_arr = np.array(PILImage.open(image_list[0]).convert('RGB'))
                crops.append(key_arr[qv[1]:qv[3], qv[0]:qv[2]])
                ids.append('0')
                for idx in range(1, len(image_list)):
                    arr = np.array(PILImage.open(image_list[idx]).convert('RGB'))
                    crops.append(arr[qv[1]:qv[3], qv[0]:qv[2]])
                    ids.append(str(idx))
                batch = _ai_ocr_mod.recognize_batch(
                    crops, ids,
                    context=ai_context,
                    api_key=api_key,
                )
                # '0' is the key image; remaining entries are students
                ai_key_txt = batch.pop('0', '')
                if ai_key_txt:
                    self.openQkeytext[qk] = ai_key_txt
                self._ai_texts[qk] = {int(sid): text for sid, text in batch.items()}
                # Step 4b: re-sync acceptable_answers with the AI-read key text
                actual_key = self.openQkeytext[qk]
                self.acceptable_answers[qk] = [actual_key] if actual_key else []
                for _ans in preloaded.get(qk, []):
                    _existing_lower = [a.lower() for a in self.acceptable_answers[qk]]
                    if _ans.lower() not in _existing_lower:
                        self.acceptable_answers[qk].append(_ans)
                for _ans in preloaded_partial.get(qk, []):
                    _existing_lower = [a.lower() for a in self.partial_credit_answers.get(qk, [])]
                    if _ans.lower() not in _existing_lower:
                        self.partial_credit_answers.setdefault(qk, []).append(_ans)
                print(f'[AI OCR]   {qk}: {len(batch)}/{len(ids) - 1} transcribed.', flush=True)
            print('[AI OCR] Batch transcription complete.', flush=True)

        cols = ['openQ_' + str(i) for i in range(1, len(self.openQcoords) + 1)]
        self.openQres = pd.DataFrame('', index=range(len(image_list)), columns=cols)
        self.openQres.loc[0] = 'CC'

        # Phase 2: grade each student's answers for each open-ended question
        openqs = sorted(list(self.openQcoords))
        qi = 0
        while qi < len(openqs):
            if qi < 0:
                qi = 0
            k = openqs[qi]
            v = self.openQcoords[k]
            idx = 1
            went_back_q = False
            while idx < len(image_list):
                if idx < 1:
                    idx = 1
                grade = self._gradeOneAnswer(image_list[idx], k, v, img_idx=idx)
                if grade == 'back':
                    idx -= 1
                    if idx == 0:
                        # Back past start of this question → go to previous question
                        qi -= 1
                        went_back_q = True
                        break
                    continue
                self.openQres.loc[idx, k] = grade
                idx += 1
            if went_back_q:
                continue   # restart outer loop at new qi
            qi += 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prompt_api_key(self) -> str:
        """
        Show a modal dialog asking the user to paste their Anthropic API key.
        Saves it to ~/.pyexamscan_config.json and returns the key string.
        Returns '' if the user cancels or leaves the field blank.
        """
        result = {'key': ''}

        dlg = tk.Toplevel(self._root)
        dlg.title('AI OCR — API Key Required')
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text='Anthropic API Key', font=('Arial', 13, 'bold')).pack(
            anchor='w', padx=16, pady=(14, 2))
        tk.Label(
            dlg,
            text='An API key is required to use Claude for handwriting recognition.\n'
                 'Paste your key below. It will be saved to\n'
                 '~/.pyexamscan_config.json (readable only by you).\n\n'
                 'Get a key at console.anthropic.com.',
            justify='left',
        ).pack(anchor='w', padx=16, pady=(0, 8))

        key_var = tk.StringVar()
        key_entry = tk.Entry(dlg, textvariable=key_var, width=52, show='*',
                             font=('Courier', 11))
        key_entry.pack(padx=16, pady=(0, 4))

        show_var = tk.BooleanVar(value=False)
        def _toggle_show():
            key_entry.config(show='' if show_var.get() else '*')
        tk.Checkbutton(dlg, text='Show key', variable=show_var,
                       command=_toggle_show).pack(anchor='w', padx=16)

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(10, 14), padx=16, anchor='e')

        def _save():
            raw = key_var.get().strip()
            if raw:
                _ai_ocr_mod.save_config({'anthropic_api_key': raw})
                result['key'] = raw
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        tk.Button(btn_frame, text='Save & Continue', command=_save,
                  bg='#2563eb', fg='white', padx=8).pack(side='left', padx=(0, 8))
        tk.Button(btn_frame, text='Skip AI OCR', command=_cancel,
                  padx=8).pack(side='left')

        dlg.bind('<Return>', lambda e: _save())
        dlg.bind('<Escape>', lambda e: _cancel())
        key_entry.focus_force()
        self._root.wait_window(dlg)
        return result['key']

    def _openQkey(self, imgpath):
        '''
        Open a Tkinter window showing the key image at 50% size.
        The user draws rectangles around each open-ended answer area.
        Pressing 'g' or clicking 'Done' closes the window and proceeds.
        '''
        fullimg = PILImage.open(imgpath).convert('RGB')
        dispres = 0.5
        W, H = fullimg.size
        disp_w = max(1, int(W * dispres))
        disp_h = max(1, int(H * dispres))
        dispimg = fullimg.resize((disp_w, disp_h), PILImage.LANCZOS)
        full_arr = np.array(fullimg)

        win = tk.Toplevel(self._root)
        win.title("Draw boxes around open-ended answer areas — press G or click Done when finished")
        win.resizable(False, False)

        canvas = tk.Canvas(win, width=disp_w, height=disp_h, cursor='crosshair')
        canvas.pack()

        tk.Label(win, text="Left-click drag to draw a box. Press Undo to remove last box.").pack()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill='x', pady=4)

        state = {
            'drawing': False,
            'sx': 0, 'sy': 0,
            'tk_img': None,
        }
        coords = self.openQcoords  # reference to the instance dict

        def redraw(current_rect=None):
            img = dispimg.copy()
            draw = PILImageDraw.Draw(img)
            for qk, qv in coords.items():
                x1 = int(qv[0] * dispres)
                y1 = int(qv[1] * dispres)
                x2 = int(qv[2] * dispres)
                y2 = int(qv[3] * dispres)
                draw.rectangle([x1, y1, x2, y2], outline=(60, 100, 220), width=2)
                draw.text((x1 + 4, y1 + 2), qk, fill=(60, 100, 220))
            if current_rect:
                draw.rectangle(current_rect, outline=(220, 100, 60), width=2)
            state['tk_img'] = _pil_to_tkphoto(img, master=win)
            canvas.create_image(0, 0, anchor='nw', image=state['tk_img'])

        def on_press(event):
            state['drawing'] = True
            state['sx'], state['sy'] = event.x, event.y

        def on_drag(event):
            if state['drawing']:
                redraw([state['sx'], state['sy'], event.x, event.y])

        def on_release(event):
            if not state['drawing']:
                return
            state['drawing'] = False
            ex, ey = event.x, event.y
            if abs(ex - state['sx']) < 5 or abs(ey - state['sy']) < 5:
                return   # ignore tiny accidental clicks
            last = len(coords)
            qk = 'openQ_' + str(last + 1)
            x1 = int(min(state['sx'], ex) / dispres)
            y1 = int(min(state['sy'], ey) / dispres)
            x2 = int(max(state['sx'], ex) / dispres)
            y2 = int(max(state['sy'], ey) / dispres)
            coords[qk] = (x1, y1, x2, y2)
            redraw()

        def undo():
            if coords:
                last_key = sorted(coords.keys())[-1]
                del coords[last_key]
                redraw()

        def done():
            win.destroy()

        canvas.bind('<ButtonPress-1>', on_press)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_release)
        win.bind('<g>', lambda e: done())
        win.bind('<G>', lambda e: done())

        tk.Button(btn_frame, text='Undo last box', command=undo).pack(side='left', padx=6)
        tk.Button(btn_frame, text='Done', command=done).pack(side='right', padx=6)

        redraw()
        win.focus_force()
        self._root.wait_window(win)

        # Extract full-resolution key crops and OCR each with local model.
        # When AI OCR is active, skip the heavy TrOCR load — the AI batch will
        # overwrite the key text via label '0' anyway.
        for qk, qv in self.openQcoords.items():
            crop = full_arr[qv[1]:qv[3], qv[0]:qv[2]]
            self.openQkeyimgs[qk] = crop
            if not getattr(self, '_ai_ocr', False):
                ocr_text, _conf = attempt_ocr(crop)
                self.openQkeytext[qk] = ocr_text
            else:
                self.openQkeytext[qk] = ''

    def _gradeOneAnswer(self, filename, k, v, img_idx=None):
        '''
        Show the key crop (top) and student answer crop (bottom).
        If OCR is confident enough, shows a suggestion the grader can accept with Enter.
        Otherwise grader simply presses C / P / X.
        The key OCR text is editable so the grader can correct it once if needed.
        Returns one of 'CC', 'CX', 'XX', or 'back'.
        '''
        full_arr = np.array(PILImage.open(filename).convert('RGB'))
        student_crop = full_arr[v[1]:v[3], v[0]:v[2]]

        # Use AI-transcribed text when available, otherwise fall back to local OCR.
        ai_text = self._ai_texts.get(k, {}).get(img_idx) if img_idx is not None else None
        if ai_text is not None:
            student_text = ai_text
            ocr_conf = 0.90   # treat AI result as high confidence
            ocr_source = 'AI'
        else:
            student_text, ocr_conf = attempt_ocr(student_crop)
            ocr_source = 'OCR'
        key_text = self.openQkeytext.get(k, '')
        # Store transcription for retroactive re-grading
        if img_idx is not None:
            self._transcriptions.setdefault(k, {})[img_idx] = (student_text, ocr_conf)
        _key_list = self.acceptable_answers.get(k) or ([key_text] if key_text else [])
        _partial_list = self.partial_credit_answers.get(k, [])
        suggestion = suggest_grade(student_text, _key_list, ocr_conf,
                                   partial_texts=_partial_list)

        # Auto-grade perfect matches without showing the window
        if not self._review_perfect and suggestion == 'CC':
            return 'CC'
        # Auto-grade defined partial-credit matches (explicitly defined → no review needed)
        if _partial_list and suggestion == 'CX':
            return 'CX'

        # Stack key and student crops vertically with a separator
        key_crop = self.openQkeyimgs[k]
        w = max(key_crop.shape[1], student_crop.shape[1])

        def pad_to_width(arr, target_w):
            if arr.shape[1] == target_w:
                return arr
            pad = np.full((arr.shape[0], target_w - arr.shape[1], 3), 255, dtype=np.uint8)
            return np.hstack([arr, pad])

        separator = np.full((4, w, 3), 100, dtype=np.uint8)
        stacked = np.vstack([
            pad_to_width(key_crop, w),
            separator,
            pad_to_width(student_crop, w),
        ])
        pil_stacked = PILImage.fromarray(stacked)
        max_w = 700
        if pil_stacked.width > max_w:
            scale = max_w / pil_stacked.width
            pil_stacked = pil_stacked.resize(
                (int(pil_stacked.width * scale), int(pil_stacked.height * scale)),
                PILImage.LANCZOS,
            )

        result = {'grade': None}

        win = tk.Toplevel(self._root)
        win.title(f'Grading {k}  —  C: correct   P: partial   X: wrong   B: go back')
        win.resizable(False, False)
        _win_bg = win.cget('bg')

        tk.Label(win, text='KEY (top) ↕ Student (bottom)',
                 font=('Arial', 12, 'bold')).pack(anchor='w', padx=8, pady=(6, 0))
        tk_img = _pil_to_tkphoto(pil_stacked, master=win)
        img_lbl = tk.Label(win, image=tk_img)
        img_lbl.pack(padx=8, pady=4)
        img_lbl.tk_img = tk_img

        # ── Editable key text (so grader can correct a mis-read key once) ──
        key_frame = tk.Frame(win)
        key_frame.pack(fill='x', padx=8, pady=(0, 2))
        tk.Label(key_frame, text='Key answer:', font=('Arial', 11)).pack(side='left')
        key_var = tk.StringVar(value=key_text)
        key_entry = tk.Entry(key_frame, textvariable=key_var, width=36, font=('Arial', 12))
        key_entry.pack(side='left', padx=6)

        # ── Suggestion label (updates as grader edits the key text) ─────────────────
        sg_bg_map  = {'CC': '#16a34a', 'CX': '#b45309', 'XX': '#dc2626'}
        sg_word_map = {'CC': '✓  CORRECT — press Enter',
                       'CX': '~  PARTIAL — press Enter',
                       'XX': '✗  WRONG — press Enter'}
        sg_label = tk.Label(win, font=('Arial', 14, 'bold'), padx=12, pady=6)
        sg_label.pack(fill='x', padx=8, pady=(4, 2))

        current_suggestion = {'val': suggestion}

        def _update_suggestion(*_):
            edited_key = key_var.get().strip()
            # Keep acceptable_answers[k][0] in sync with the editable key field
            if edited_key and self.acceptable_answers.get(k):
                self.acceptable_answers[k][0] = edited_key
            elif edited_key:
                self.acceptable_answers[k] = [edited_key]
            _key_list = self.acceptable_answers.get(k) or ([edited_key] if edited_key else [])
            _pt_list = self.partial_credit_answers.get(k, [])
            sug = suggest_grade(student_text, _key_list, ocr_conf, partial_texts=_pt_list)
            current_suggestion['val'] = sug
            if sug:
                sg_label.config(
                    text=f'{ocr_source}: "{student_text}"  →  {sg_word_map[sug]}',
                    bg=sg_bg_map[sug], fg='white')
            else:
                if student_text:
                    lbl = f'{ocr_source}: "{student_text}"  —  not confident enough to suggest'
                else:
                    lbl = 'No text detected — grade manually'
                sg_label.config(text=lbl, bg=_win_bg, fg='gray40')

        key_var.trace_add('write', _update_suggestion)
        _update_suggestion()

        # ── Acceptable answers panel ───────────────────────────────────────────────
        aa_frame = tk.Frame(win)
        aa_frame.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(aa_frame, text='Acceptable answers:', font=('Arial', 11)).pack(
            side='left', anchor='n', pady=2)

        aa_list_frame = tk.Frame(aa_frame)
        aa_list_frame.pack(side='left', padx=6)
        aa_listbox = tk.Listbox(aa_list_frame, height=3, width=30, font=('Arial', 11),
                                selectmode=tk.SINGLE, exportselection=False,
                                takefocus=False)
        aa_scrollbar = tk.Scrollbar(aa_list_frame, orient='vertical',
                                    command=aa_listbox.yview)
        aa_listbox.configure(yscrollcommand=aa_scrollbar.set)
        aa_listbox.pack(side='left')
        aa_scrollbar.pack(side='left', fill='y')

        aa_btn_frame = tk.Frame(aa_frame)
        aa_btn_frame.pack(side='left', padx=4, anchor='n')

        regrade_status_var = tk.StringVar(value='')
        regrade_status_lbl = tk.Label(aa_btn_frame, textvariable=regrade_status_var,
                                      font=('Arial', 10), fg='#16a34a',
                                      wraplength=160, justify='left')

        def _refresh_aa_listbox():
            aa_listbox.delete(0, tk.END)
            for i, ans in enumerate(self.acceptable_answers.get(k, [])):
                prefix = '(primary) ' if i == 0 else ''
                aa_listbox.insert(tk.END, prefix + ans)

        def _add_student_answer():
            if not student_text or student_text == '[?]':
                return
            count = self._add_acceptable_and_regrade(k, student_text, img_idx)
            _refresh_aa_listbox()
            if count > 0:
                regrade_status_var.set(f'Added. {count} previous student(s) upgraded.')
            else:
                regrade_status_var.set('Added (no previous upgrades).')
            _update_suggestion()

        def _remove_selected_aa():
            sel = aa_listbox.curselection()
            if not sel:
                return
            idx_sel = sel[0]
            if idx_sel == 0:
                return  # don't allow removing the primary answer
            del self.acceptable_answers[k][idx_sel]
            _refresh_aa_listbox()
            regrade_status_var.set('')
            _update_suggestion()

        add_btn_state = 'normal' if (student_text and student_text != '[?]') else 'disabled'
        tk.Button(aa_btn_frame, text='Add student answer', font=('Arial', 10),
                  state=add_btn_state,
                  command=_add_student_answer).pack(anchor='w', pady=(0, 2))
        tk.Button(aa_btn_frame, text='Remove selected', font=('Arial', 10),
                  command=_remove_selected_aa).pack(anchor='w', pady=(0, 2))
        regrade_status_lbl.pack(anchor='w')
        _refresh_aa_listbox()

        # ── Partial credit answers panel ──────────────────────────────────────────
        pa_frame = tk.Frame(win)
        pa_frame.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(pa_frame, text='Partial credit\nanswers:', font=('Arial', 11)).pack(
            side='left', anchor='n', pady=2)

        pa_list_frame = tk.Frame(pa_frame)
        pa_list_frame.pack(side='left', padx=6)
        pa_listbox = tk.Listbox(pa_list_frame, height=3, width=30, font=('Arial', 11),
                                selectmode=tk.SINGLE, exportselection=False,
                                takefocus=False)
        pa_scrollbar = tk.Scrollbar(pa_list_frame, orient='vertical',
                                    command=pa_listbox.yview)
        pa_listbox.configure(yscrollcommand=pa_scrollbar.set)
        pa_listbox.pack(side='left')
        pa_scrollbar.pack(side='left', fill='y')

        pa_btn_frame = tk.Frame(pa_frame)
        pa_btn_frame.pack(side='left', padx=4, anchor='n')

        def _refresh_pa_listbox():
            pa_listbox.delete(0, tk.END)
            for ans in self.partial_credit_answers.get(k, []):
                pa_listbox.insert(tk.END, ans)

        def _add_student_as_partial():
            if not student_text or student_text == '[?]':
                return
            count = self._add_acceptable_and_regrade(k, student_text, img_idx, grade='CX')
            _refresh_pa_listbox()
            if count > 0:
                regrade_status_var.set(f'Added partial. {count} previous student(s) upgraded.')
            else:
                regrade_status_var.set('Added as partial (no previous upgrades).')
            _update_suggestion()

        def _remove_selected_pa():
            sel = pa_listbox.curselection()
            if not sel:
                return
            del self.partial_credit_answers[k][sel[0]]
            _refresh_pa_listbox()
            regrade_status_var.set('')
            _update_suggestion()

        tk.Button(pa_btn_frame, text='Add as partial credit', font=('Arial', 10),
                  state=add_btn_state,
                  command=_add_student_as_partial).pack(anchor='w', pady=(0, 2))
        tk.Button(pa_btn_frame, text='Remove selected', font=('Arial', 10),
                  command=_remove_selected_pa).pack(anchor='w', pady=(0, 2))
        _refresh_pa_listbox()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill='x', padx=8, pady=(4, 8))

        def set_grade(g):
            # Persist any key text correction for subsequent students
            self.openQkeytext[k] = key_var.get()
            result['grade'] = g
            win.destroy()

        tk.Button(btn_frame, text='Correct  [C]', bg='#90EE90', width=14,
                  command=lambda: set_grade('CC')).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Partial  [P]', bg='#FFD700', width=14,
                  command=lambda: set_grade('CX')).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Wrong    [X]', bg='#FFB6C1', width=14,
                  command=lambda: set_grade('XX')).pack(side='left', padx=4)
        tk.Button(btn_frame, text='← Back  [B]', width=14,
                  command=lambda: set_grade('back')).pack(side='left', padx=4)

        for key_char, grade in [('c', 'CC'), ('C', 'CC'),
                                 ('p', 'CX'), ('P', 'CX'),
                                 ('x', 'XX'), ('X', 'XX'),
                                 ('b', 'back'), ('B', 'back')]:
            def _make_handler(g):
                def handler(e):
                    if win.focus_get() is key_entry:
                        return
                    set_grade(g)
                return handler
            win.bind(key_char, _make_handler(grade))

        def _on_return(e):
            if win.focus_get() is key_entry:
                win.focus_set()  # move focus out of entry so Enter on next press grades
                return
            if current_suggestion['val']:
                set_grade(current_suggestion['val'])
        win.bind('<Return>', _on_return)

        win.focus_force()
        self._root.wait_window(win)
        return result['grade'] if result['grade'] is not None else 'XX'

    # ------------------------------------------------------------------
    def _add_acceptable_and_regrade(self, qk: str, new_text: str,
                                     current_idx: int, grade: str = 'CC') -> int:
        """
        Add new_text to acceptable_answers[qk] (grade='CC', full credit) or
        partial_credit_answers[qk] (grade='CX', partial credit).
        Re-grades already-graded rows 1..current_idx-1 for qk.
        Only upgrades existing grades (XX→CC, XX→CX, CX→CC).
        Returns the number of grades that were upgraded.
        """
        new_text = new_text.strip()
        if not new_text:
            return 0
        target_dict = self.partial_credit_answers if grade == 'CX' else self.acceptable_answers
        existing_lower = [a.lower() for a in target_dict.get(qk, [])]
        if new_text.lower() in existing_lower:
            return 0
        target_dict.setdefault(qk, []).append(new_text)

        grade_rank = {'CC': 3, 'CX': 2, 'XX': 1, '': 0}
        upgraded = 0
        transcriptions_for_q = self._transcriptions.get(qk, {})
        for prev_idx in range(1, current_idx):
            if prev_idx not in transcriptions_for_q:
                continue
            text, conf = transcriptions_for_q[prev_idx]
            if not text:
                continue
            old_grade = (self.openQres.loc[prev_idx, qk]
                         if prev_idx in self.openQres.index else '')
            new_sug = suggest_grade(
                text,
                self.acceptable_answers.get(qk, []),
                conf,
                partial_texts=self.partial_credit_answers.get(qk, []),
            )
            if new_sug and grade_rank.get(new_sug, 0) > grade_rank.get(str(old_grade), 0):
                self.openQres.loc[prev_idx, qk] = new_sug
                upgraded += 1
        return upgraded

    def save_artifacts(self, csv_path: str, grade_config: dict | None = None) -> None:
        """
        Save acceptable answers, transcriptions, and optionally grade config
        alongside results.csv so post-session re-grading can use them.
          {stem}_openq_answers.json
          {stem}_openq_transcriptions.json
          {stem}_openq_gradeconfig.json  (only written when grade_config provided)
        """
        stem = str(Path(csv_path).with_suffix(''))

        try:
            merged_answers: dict = {}
            for qk in set(list(self.acceptable_answers.keys()) +
                          list(self.partial_credit_answers.keys())):
                merged_answers[qk] = {
                    'full': self.acceptable_answers.get(qk, []),
                    'partial': self.partial_credit_answers.get(qk, []),
                }
            Path(stem + '_openq_answers.json').write_text(
                json.dumps(merged_answers, indent=2), encoding='utf-8')

            trans_serialisable = {
                qk: {str(idx): list(v) for idx, v in per_q.items()}
                for qk, per_q in self._transcriptions.items()
            }
            Path(stem + '_openq_transcriptions.json').write_text(
                json.dumps(trans_serialisable, indent=2), encoding='utf-8')

            if grade_config:
                Path(stem + '_openq_gradeconfig.json').write_text(
                    json.dumps(grade_config, indent=2), encoding='utf-8')
        except Exception as exc:
            print(f'[OpenQ] save_artifacts failed: {exc}', flush=True)


class RegradeDialog:
    """
    Post-session re-grader dialog.
    Loads {stem}_openq_answers.json and {stem}_openq_transcriptions.json,
    lets the user edit acceptable answers, then calls regrade_open_questions()
    and gradeResults() when the user clicks Apply.
    """

    def __init__(self, parent, csv_path: str, on_complete=None):
        self._parent = parent
        self._csv_path = csv_path
        self._on_complete = on_complete

        stem = str(Path(csv_path).with_suffix(''))
        answers_path = stem + '_openq_answers.json'
        trans_path   = stem + '_openq_transcriptions.json'

        if not Path(answers_path).exists():
            import tkinter.messagebox as mb
            mb.showerror('Re-grader',
                         f'Cannot find:\n{answers_path}\n\n'
                         'Run a scan with open-ended questions first.',
                         parent=self._parent)
            return

        raw_answers = json.loads(Path(answers_path).read_text(encoding='utf-8'))
        self._acceptable_answers = {}
        self._partial_credit_answers = {}
        for qk, val in raw_answers.items():
            if isinstance(val, dict):
                # New format: {"full": [...], "partial": [...]}
                self._acceptable_answers[qk] = val.get('full', [])
                self._partial_credit_answers[qk] = val.get('partial', [])
            elif isinstance(val, list):
                # Old format: all full credit
                self._acceptable_answers[qk] = val
        self._transcriptions = (
            json.loads(Path(trans_path).read_text(encoding='utf-8'))
            if Path(trans_path).exists() else {})

        self._build_ui()

    def _build_ui(self):
        win = tk.Toplevel(self._parent)
        win.title('Re-grade Open Questions')
        win.resizable(True, True)
        win.grab_set()
        self._win = win

        _F  = ('Arial', 12)
        _FB = ('Arial', 12, 'bold')
        _FM = ('Arial', 13, 'bold')
        _FC = ('Courier', 11)

        # ── Left panel: question list ─────────────────────────────────────
        left = tk.Frame(win)
        left.pack(side='left', fill='y', padx=8, pady=8)
        tk.Label(left, text='Questions:', font=_FM).pack(anchor='w')
        q_listbox = tk.Listbox(left, width=18, font=_F,
                               exportselection=False)
        q_listbox.pack(fill='both', expand=True)
        for qk in sorted(set(list(self._acceptable_answers.keys()) +
                              list(self._partial_credit_answers.keys()))):
            q_listbox.insert(tk.END, qk)

        # ── Right panel: editor + transcriptions ──────────────────────────
        right = tk.Frame(win)
        right.pack(side='left', fill='both', expand=True, padx=8, pady=8)

        tk.Label(right, text='Acceptable answers for selected question:',
                 font=_FM).pack(anchor='w')
        aa_listbox = tk.Listbox(right, height=8, font=_F,
                                exportselection=False)
        aa_listbox.pack(fill='x', pady=(2, 4))

        entry_frame = tk.Frame(right)
        entry_frame.pack(fill='x', pady=2)
        tk.Label(entry_frame, text='New answer:', font=_F).pack(side='left')
        new_ans_var = tk.StringVar()
        new_ans_entry = tk.Entry(entry_frame, textvariable=new_ans_var,
                                 width=30, font=_F)
        new_ans_entry.pack(side='left', padx=6)

        btn_row = tk.Frame(right)
        btn_row.pack(fill='x', pady=2)
        current_q = {'k': None}

        def _refresh_aa():
            aa_listbox.delete(0, tk.END)
            k = current_q['k']
            if not k:
                return
            for i, ans in enumerate(self._acceptable_answers.get(k, [])):
                prefix = '(primary) ' if i == 0 else ''
                aa_listbox.insert(tk.END, prefix + ans)

        def _on_q_select(event):
            sel = q_listbox.curselection()
            if not sel:
                return
            current_q['k'] = q_listbox.get(sel[0])
            _refresh_aa()
            _refresh_pa()
            trans_text.configure(state='normal')
            trans_text.delete('1.0', 'end')
            k = current_q['k']
            q_trans = self._transcriptions.get(k, {})
            if q_trans:
                for idx_str in sorted(q_trans.keys(), key=lambda x: int(x)):
                    text, conf = q_trans[idx_str][0], q_trans[idx_str][1]
                    trans_text.insert(
                        'end',
                        f'  Student {idx_str}: "{text}"  (conf={conf:.2f})\n')
            else:
                trans_text.insert('end', '  (no transcriptions available)\n')
            trans_text.configure(state='disabled')

        q_listbox.bind('<<ListboxSelect>>', _on_q_select)

        def _add_answer():
            k = current_q['k']
            if not k:
                return
            new = new_ans_var.get().strip()
            if not new:
                return
            existing_lower = [a.lower() for a in
                              self._acceptable_answers.get(k, [])]
            if new.lower() not in existing_lower:
                self._acceptable_answers.setdefault(k, []).append(new)
                _refresh_aa()
            new_ans_var.set('')

        def _remove_answer():
            k = current_q['k']
            if not k:
                return
            sel = aa_listbox.curselection()
            if not sel or sel[0] == 0:
                return  # don't remove primary
            del self._acceptable_answers[k][sel[0]]
            _refresh_aa()

        new_ans_entry.bind('<Return>', lambda e: _add_answer())
        tk.Button(btn_row, text='Add', command=_add_answer,
                  bg='#90EE90', font=_F).pack(side='left', padx=(0, 4))
        tk.Button(btn_row, text='Remove selected',
                  command=_remove_answer, font=_F).pack(side='left', padx=(0, 4))

        # ── Partial credit answers ────────────────────────────────────────────────
        tk.Label(right, text='Partial credit answers (auto-graded CX):',
                 font=_FB).pack(anchor='w', pady=(6, 0))
        pa_listbox = tk.Listbox(right, height=4, font=_F, exportselection=False)
        pa_listbox.pack(fill='x', pady=(2, 4))

        pa_entry_frame = tk.Frame(right)
        pa_entry_frame.pack(fill='x', pady=2)
        tk.Label(pa_entry_frame, text='New partial:', font=_F).pack(side='left')
        new_partial_var = tk.StringVar()
        new_partial_entry = tk.Entry(pa_entry_frame, textvariable=new_partial_var,
                                     width=30, font=_F)
        new_partial_entry.pack(side='left', padx=6)

        pa_btn_row = tk.Frame(right)
        pa_btn_row.pack(fill='x', pady=2)

        def _refresh_pa():
            pa_listbox.delete(0, tk.END)
            k = current_q['k']
            if not k:
                return
            for ans in self._partial_credit_answers.get(k, []):
                pa_listbox.insert(tk.END, ans)

        def _add_partial():
            k = current_q['k']
            if not k:
                return
            new = new_partial_var.get().strip()
            if not new:
                return
            existing_lower = [a.lower() for a in
                              self._partial_credit_answers.get(k, [])]
            if new.lower() not in existing_lower:
                self._partial_credit_answers.setdefault(k, []).append(new)
                _refresh_pa()
            new_partial_var.set('')

        def _remove_partial():
            k = current_q['k']
            if not k:
                return
            sel = pa_listbox.curselection()
            if not sel:
                return
            del self._partial_credit_answers[k][sel[0]]
            _refresh_pa()

        new_partial_entry.bind('<Return>', lambda e: _add_partial())
        tk.Button(pa_btn_row, text='Add partial', command=_add_partial,
                  bg='#FFD700', font=_F).pack(side='left', padx=(0, 4))
        tk.Button(pa_btn_row, text='Remove selected',
                  command=_remove_partial, font=_F).pack(side='left', padx=(0, 4))

        tk.Label(right, text='Student transcriptions (read-only):',
                 font=_FB).pack(anchor='w', pady=(6, 0))
        trans_text = tk.Text(right, height=6, state='disabled', font=_FC)
        trans_text.pack(fill='x')

        # ── Bottom buttons ────────────────────────────────────────────────
        btn_bottom = tk.Frame(win)
        btn_bottom.pack(fill='x', padx=8, pady=8, side='bottom')
        status_var = tk.StringVar(value='')
        tk.Label(btn_bottom, textvariable=status_var,
                 font=_F, fg='#16a34a').pack(side='left')

        def _apply():
            import grade_functions
            stem = str(Path(self._csv_path).with_suffix(''))
            try:
                # Save updated answers JSON (merged format)
                merged = {}
                for qk in set(list(self._acceptable_answers.keys()) +
                              list(self._partial_credit_answers.keys())):
                    merged[qk] = {
                        'full': self._acceptable_answers.get(qk, []),
                        'partial': self._partial_credit_answers.get(qk, []),
                    }
                Path(stem + '_openq_answers.json').write_text(
                    json.dumps(merged, indent=2), encoding='utf-8')
                # Re-grade CSV
                n = grade_functions.regrade_open_questions(
                    self._csv_path, self._acceptable_answers, self._transcriptions,
                    partial_answers=self._partial_credit_answers)
            except Exception as exc:
                status_var.set(f'Error: {exc}')
                return
            # Recalculate scores using saved grade config if available
            try:
                config_path = Path(stem + '_openq_gradeconfig.json')
                if config_path.exists():
                    cfg = json.loads(config_path.read_text(encoding='utf-8'))
                    bubble_val = float(cfg.get('bubbleVal', 1))
                    open_val   = float(cfg.get('openVal', 2))
                    select_all = bool(cfg.get('selectAll', False))
                else:
                    bubble_val, open_val, select_all = 1.0, 2.0, False
                df_check = pd.read_csv(self._csv_path)
                has_open = any(c.startswith('openQ_') for c in df_check.columns)
                grade_functions.gradeResults(
                    self._csv_path,
                    selectAll=select_all,
                    openQ=has_open,
                    bubbleVal=bubble_val,
                    openVal=open_val,
                    markeddir=Path(self._csv_path).parent / 'marked',
                )
            except Exception as exc:
                print(f'[Regrade] gradeResults error: {exc}', flush=True)

            status_var.set(
                f'Done. {n} grade(s) upgraded and scores recalculated.')
            if self._on_complete:
                self._on_complete(n)

        tk.Button(btn_bottom, text='▶  Apply Re-grading', command=_apply,
                  font=('Arial', 12, 'bold'), padx=10).pack(side='right', padx=4)
        tk.Button(btn_bottom, text='Close', command=win.destroy,
                  font=_F, padx=8).pack(side='right', padx=4)
