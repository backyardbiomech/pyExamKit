import base64
import io
import numpy as np
import pandas as pd
import tkinter as tk
from PIL import Image as PILImage, ImageDraw as PILImageDraw

from ocr import attempt_ocr, suggest_grade


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

    def __init__(self, image_list, parent=None):
        self.openQcoords = {}
        self.openQkeyimgs = {}
        self.openQkeytext = {}   # OCR text from each key crop

        # Obtain the Tkinter root window
        if parent is not None:
            self._root = parent
        else:
            self._root = tk._default_root
            if self._root is None:
                self._root = tk.Tk()
                self._root.withdraw()

        # Phase 1: let user draw boxes on the key image
        self._openQkey(image_list[0])

        if not self.openQcoords:
            # User closed without drawing anything
            cols = []
            self.openQres = pd.DataFrame(index=range(len(image_list)), columns=cols)
            return

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
                grade = self._gradeOneAnswer(image_list[idx], k, v)
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

        # Extract full-resolution key crops and attempt OCR on each
        for qk, qv in self.openQcoords.items():
            crop = full_arr[qv[1]:qv[3], qv[0]:qv[2]]
            self.openQkeyimgs[qk] = crop
            ocr_text, _conf = attempt_ocr(crop)
            self.openQkeytext[qk] = ocr_text

    def _gradeOneAnswer(self, filename, k, v):
        '''
        Show the key crop (top) and student answer crop (bottom).
        If OCR is confident enough, shows a suggestion the grader can accept with Enter.
        Otherwise grader simply presses C / P / X.
        The key OCR text is editable so the grader can correct it once if needed.
        Returns one of 'CC', 'CX', 'XX', or 'back'.
        '''
        full_arr = np.array(PILImage.open(filename).convert('RGB'))
        student_crop = full_arr[v[1]:v[3], v[0]:v[2]]

        student_text, ocr_conf = attempt_ocr(student_crop)
        key_text = self.openQkeytext.get(k, '')
        suggestion = suggest_grade(student_text, key_text, ocr_conf)

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

        tk.Label(win, text='KEY (top) ↕ Student (bottom)',
                 font=('Arial', 10, 'bold')).pack(anchor='w', padx=8, pady=(6, 0))
        tk_img = _pil_to_tkphoto(pil_stacked, master=win)
        img_lbl = tk.Label(win, image=tk_img)
        img_lbl.pack(padx=8, pady=4)
        img_lbl.tk_img = tk_img

        # ── Editable key text (so grader can correct a mis-read key once) ──
        key_frame = tk.Frame(win)
        key_frame.pack(fill='x', padx=8, pady=(0, 2))
        tk.Label(key_frame, text='Key answer:', font=('Arial', 9)).pack(side='left')
        key_var = tk.StringVar(value=key_text)
        key_entry = tk.Entry(key_frame, textvariable=key_var, width=36, font=('Arial', 10))
        key_entry.pack(side='left', padx=6)

        # ── Suggestion label (static — based on OCR result) ────────────────
        sg_color_map = {'CC': '#1a6e1a', 'CX': '#8b5a00', 'XX': '#8b0000'}
        sg_text_map  = {'CC': f'OCR: "{student_text}"  →  Suggested: CORRECT  (Enter)',
                        'CX': f'OCR: "{student_text}"  →  Suggested: PARTIAL   (Enter)',
                        'XX': f'OCR: "{student_text}"  →  Suggested: WRONG     (Enter)'}
        sg_label = tk.Label(win, font=('Arial', 11, 'bold'))
        sg_label.pack(pady=(2, 0))

        current_suggestion = {'val': suggestion}

        def _update_suggestion(*_):
            edited_key = key_var.get()
            sug = suggest_grade(student_text, edited_key, ocr_conf)
            current_suggestion['val'] = sug
            if sug:
                sg_label.config(
                    text=sg_text_map.get(sug, '').replace(key_text, edited_key),
                    fg=sg_color_map[sug])
            else:
                lbl = f'OCR: "{student_text}"  —  not confident enough to suggest' if student_text else 'No text detected — grade manually'
                sg_label.config(text=lbl, fg='gray40')

        key_var.trace_add('write', _update_suggestion)
        _update_suggestion()

        # ── Grade buttons ──────────────────────────────────────────────────
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)

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
