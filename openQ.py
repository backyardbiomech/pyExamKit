import base64
import csv
import io
import json
import numpy as np
import pandas as pd
import tkinter as tk
import tkinter.messagebox
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


def _openq_sort_key(k: str) -> int:
    """Numeric sort key for openQ_N keys so openQ_2 sorts before openQ_10."""
    try:
        return int(k.rsplit('_', 1)[-1])
    except (ValueError, IndexError):
        return 0


def _load_aligned_arr(imgpath: str) -> 'np.ndarray':
    """
    Load a scan image (JPEG or PDF) and return the aligned numpy array.
    PDFs are rendered at 200 dpi (first page only) via fitz before alignment.
    Raises on failure.
    """
    from image import Image as _Image
    from settings import Settings as _Settings
    p = Path(imgpath)
    if p.suffix.lower() == '.pdf':
        import fitz as _fitz
        import tempfile
        doc = _fitz.open(str(p))
        page = doc[0]
        mat = _fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=_fitz.csRGB)
        doc.close()
        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmp_path = tmp.name
        tmp.close()
        pix.save(tmp_path)
        try:
            return _Image(tmp_path, _Settings()).aligned
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return _Image(imgpath, _Settings()).aligned


def _pdf_page_count(pdfpath: str) -> int:
    """Return the number of pages in a PDF file. Returns 1 for non-PDFs."""
    if Path(pdfpath).suffix.lower() != '.pdf':
        return 1
    import fitz as _fitz
    doc = _fitz.open(str(pdfpath))
    n = len(doc)
    doc.close()
    return n


def _load_aligned_arr_page(pdfpath: str, page_idx: int) -> 'np.ndarray':
    """Render one page of a PDF (0-based index) and return the aligned numpy array."""
    from image import Image as _Image
    from settings import Settings as _Settings
    import fitz as _fitz
    import tempfile
    doc = _fitz.open(str(pdfpath))
    page = doc[page_idx]
    mat = _fitz.Matrix(200 / 72, 200 / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=_fitz.csRGB)
    doc.close()
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    tmp_path = tmp.name
    tmp.close()
    pix.save(tmp_path)
    try:
        return _Image(tmp_path, _Settings()).aligned
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def load_key_file(path: str) -> dict | None:
    """
    Load an exam key file (JSON or CSV).
    CSV files (.csv) are dispatched to load_key_csv().
    JSON files return the parsed/normalised dict with keys:
      bubble_answers, open_questions
    Returns None on failure.
    """
    p = Path(path)
    if not p.exists():
        print(f'[KeyFile] Not found: {path}', flush=True)
        return None
    # Dispatch CSV format
    if p.suffix.lower() == '.csv':
        return load_key_csv(path)
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Root must be a JSON object')

        # Normalise bubble answer keys: "Q1" / "1" → "Q001"
        raw_bubble = data.get('bubble_answers', {})
        norm_bubble: dict = {}
        for k, v in raw_bubble.items():
            k = str(k).strip()
            if k.upper().startswith('Q'):
                try:
                    norm_bubble['Q' + format(int(k[1:]), '03d')] = str(v).strip()
                    continue
                except ValueError:
                    pass
            norm_bubble[k] = str(v).strip()
        data['bubble_answers'] = norm_bubble

        # Normalise open-question keys: "1" → "openQ_1"
        raw_oq = data.get('open_questions', {})
        norm_oq: dict = {}
        for k, v in raw_oq.items():
            k = str(k).strip()
            if not k.startswith('openQ_'):
                try:
                    k = 'openQ_' + str(int(k))
                except ValueError:
                    k = 'openQ_' + k
            norm_oq[k] = v
        data['open_questions'] = norm_oq

        return data
    except Exception as exc:
        print(f'[KeyFile] Failed to load {path}: {exc}', flush=True)
        return None


def load_key_csv(path: str) -> dict | None:
    """
    Load a CSV exam key file.

    Wide format (one row per question — preferred):
      type, question, page, x1, y1, x2, y2, answer, partial_answers
      type is 'bubble' or 'open'.
      answer       — the primary (full-credit) answer; pipe-separated for multiple
      partial_answers — pipe-separated partial-credit answers (optional)

    Tall/legacy format also accepted (one row per answer):
      type is 'bubble', 'open_coords', 'open_full', or 'open_partial'

    Rows with blank type or type starting with '#' are skipped.
    Returns the same dict shape as load_key_file(), or None on failure.
    """
    def _norm_bubble_key(raw: str) -> str:
        raw = raw.strip()
        if raw.upper().startswith('Q'):
            try:
                return 'Q' + format(int(raw[1:]), '03d')
            except ValueError:
                pass
        try:
            return 'Q' + format(int(raw), '03d')
        except ValueError:
            return raw

    def _norm_open_key(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith('openQ_'):
            return raw
        try:
            return 'openQ_' + str(int(raw))
        except ValueError:
            return 'openQ_' + raw

    def _parse_pipe(cell: str) -> list[str]:
        """Split a pipe-separated cell, strip each part, drop empties."""
        return [v.strip() for v in cell.split('|') if v.strip()]

    p = Path(path)
    if not p.exists():
        print(f'[KeyFile] Not found: {path}', flush=True)
        return None

    bubble_answers: dict = {}
    open_questions: dict = {}
    metadata: dict = {}

    try:
        with open(p, newline='', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row_type = (row.get('type') or '').strip().lower()
                if not row_type or row_type.startswith('#'):
                    continue

                question = (row.get('question') or '').strip()
                if not question:
                    continue

                # ── Metadata row ─────────────────────────────────────────
                if row_type == 'metadata':
                    value = (row.get('answer') or '').strip()
                    if question == 'num_questions' and value:
                        try:
                            metadata['num_questions'] = int(value)
                        except ValueError:
                            pass
                    elif question == 'questions_to_skip' and value:
                        metadata['questions_to_skip'] = value
                    continue

                # ── Wide format ──────────────────────────────────────────
                if row_type == 'bubble':
                    answer = (row.get('answer') or row.get('value') or '').strip()
                    bubble_answers[_norm_bubble_key(question)] = answer

                elif row_type == 'open':
                    qk = _norm_open_key(question)
                    if qk not in open_questions:
                        open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                    # Coordinates
                    try:
                        x1 = int(row.get('x1') or 0)
                        y1 = int(row.get('y1') or 0)
                        x2 = int(row.get('x2') or 0)
                        y2 = int(row.get('y2') or 0)
                        if any(c != 0 for c in (x1, y1, x2, y2)):
                            open_questions[qk]['coords'] = [x1, y1, x2, y2]
                    except (ValueError, TypeError):
                        pass
                    # Page
                    try:
                        pv = (row.get('page') or '').strip()
                        open_questions[qk]['page'] = max(1, int(pv)) if pv else 1
                    except (ValueError, TypeError):
                        pass
                    # Full-credit answers (pipe-separated)
                    for ans in _parse_pipe(row.get('answer') or ''):
                        if ans.lower() not in [a.lower() for a in open_questions[qk]['full']]:
                            open_questions[qk]['full'].append(ans)
                    # Partial-credit answers (pipe-separated)
                    for ans in _parse_pipe(row.get('partial_answers') or ''):
                        if ans.lower() not in [a.lower() for a in open_questions[qk]['partial']]:
                            open_questions[qk]['partial'].append(ans)

                # ── Tall/legacy format ───────────────────────────────────
                elif row_type == 'open_coords':
                    qk = _norm_open_key(question)
                    if qk not in open_questions:
                        open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                    try:
                        x1 = int(row.get('x1') or 0)
                        y1 = int(row.get('y1') or 0)
                        x2 = int(row.get('x2') or 0)
                        y2 = int(row.get('y2') or 0)
                        if any(c != 0 for c in (x1, y1, x2, y2)):
                            open_questions[qk]['coords'] = [x1, y1, x2, y2]
                    except (ValueError, TypeError):
                        pass
                    try:
                        pv = (row.get('page') or '').strip()
                        open_questions[qk]['page'] = max(1, int(pv)) if pv else 1
                    except (ValueError, TypeError):
                        pass

                elif row_type == 'open_full':
                    value = (row.get('value') or '').strip()
                    if value:
                        qk = _norm_open_key(question)
                        if qk not in open_questions:
                            open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                        if value.lower() not in [a.lower() for a in open_questions[qk]['full']]:
                            open_questions[qk]['full'].append(value)

                elif row_type == 'open_partial':
                    value = (row.get('value') or '').strip()
                    if value:
                        qk = _norm_open_key(question)
                        if qk not in open_questions:
                            open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                        if value.lower() not in [a.lower() for a in open_questions[qk]['partial']]:
                            open_questions[qk]['partial'].append(value)

    except Exception as exc:
        print(f'[KeyFile] Failed to load CSV {path}: {exc}', flush=True)
        return None

    print(f'[KeyFile] Loaded CSV key: {len(bubble_answers)} bubble answer(s), '
          f'{len(open_questions)} open question(s).', flush=True)
    result = {'bubble_answers': bubble_answers, 'open_questions': open_questions}
    if metadata:
        result['metadata'] = metadata
    return result


def save_key_csv(path: str, data: dict) -> None:
    """
    Write a CSV exam key file in wide format (one row per question).
    Columns: type, question, page, x1, y1, x2, y2, answer, partial_answers
      metadata rows: type=metadata, question=field_name, answer=value
      bubble rows:   type=bubble, answer=letter(s), all coordinate columns blank
      open rows:     type=open, answer=pipe-separated full-credit answers,
                     partial_answers=pipe-separated partial-credit answers
    """
    bubble = data.get('bubble_answers', {})
    open_qs = data.get('open_questions', {})
    meta = data.get('metadata', {})

    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh)
        writer.writerow(['type', 'question', 'page', 'x1', 'y1', 'x2', 'y2',
                         'answer', 'partial_answers'])

        # Metadata rows (num_questions, questions_to_skip)
        if meta.get('num_questions'):
            writer.writerow(['metadata', 'num_questions', '', '', '', '', '',
                             meta['num_questions'], ''])
        if meta.get('questions_to_skip'):
            writer.writerow(['metadata', 'questions_to_skip', '', '', '', '', '',
                             meta['questions_to_skip'], ''])

        # Bubble answers (sorted by question key)
        for qk in sorted(bubble.keys()):
            writer.writerow(['bubble', qk, '', '', '', '', '', bubble[qk], ''])

        # Open-ended questions (sorted numerically so openQ_2 precedes openQ_10)
        for qk in sorted(open_qs.keys(), key=_openq_sort_key):
            qdata = open_qs[qk]
            page = qdata.get('page', 1) or 1
            coords = qdata.get('coords')
            if coords and len(coords) == 4:
                x1, y1, x2, y2 = (int(c) for c in coords)
            else:
                x1, y1, x2, y2 = ('', '', '', '')
            full_ans = '|'.join(qdata.get('full', []))
            partial_ans = '|'.join(qdata.get('partial', []))
            writer.writerow(['open', qk, page, x1, y1, x2, y2, full_ans, partial_ans])


def save_key_file(path: str, data: dict) -> None:
    """Write an exam key file. Dispatches to CSV or JSON based on file extension."""
    if Path(path).suffix.lower() == '.csv':
        save_key_csv(path, data)
        return
    Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')


class OpenQs(object):
    '''
    Handles open-ended question area selection and grading using Tkinter windows.

    Usage (same external API as before):
        openQs = OpenQs(aligned_image_list, parent=root_tk_window)
        openQs.openQcoords   – dict of {question_key: (x1,y1,x2,y2)}
        openQs.openQres      – DataFrame of grades ('CC','CX','XX')
    '''

    def __init__(self, image_list, parent=None, ai_ocr=False, api_key='',
                 ai_context='', preloaded_file: str = '', review_perfect: bool = True,
                 key_file_data: dict | None = None, key_file_path: str = '',
                 pages_per_student: int = 1, ignores=None):
        self._ignores: list[int] = sorted(ignores) if ignores else []
        self.openQcoords = {}
        self.openQkeyimgs = {}
        self.openQkeytext = {}   # OCR text from each key crop
        self._ai_texts: dict[str, dict[int, str]] = {}  # {qkey: {img_idx: text}}
        self.acceptable_answers: dict[str, list] = {}   # {qk: [str, ...]}
        self.partial_credit_answers: dict[str, list] = {}  # {qk: [str, ...]}
        self._transcriptions: dict[str, dict] = {}      # {qk: {img_idx: (text, conf)}}
        self._preloaded_file = preloaded_file
        self._review_perfect = review_perfect
        self._key_file_mode = key_file_data is not None
        self._key_file_path = key_file_path
        self._pages_per_student = max(1, int(pages_per_student))
        self._q_pages: dict[str, int] = {}

        # Obtain the Tkinter root window
        if parent is not None:
            self._root = parent
        else:
            self._root = tk._default_root
            if self._root is None:
                self._root = tk.Tk()
                self._root.withdraw()

        self._ai_ocr = ai_ocr   # used by _openQkey to skip TrOCR when Claude is active

        # Phase 1: set up open-ended question coords and answer keys
        if key_file_data is not None:
            open_qs = key_file_data.get('open_questions', {})
            # Populate page mapping from key file data
            for qk, qdata in open_qs.items():
                self._q_pages[qk] = int(qdata.get('page', 1) or 1)
            # Pre-load coords for questions that have them
            for qk, qdata in open_qs.items():
                raw_coords = qdata.get('coords')
                if raw_coords and len(raw_coords) == 4:
                    self.openQcoords[qk] = tuple(int(c) for c in raw_coords)
            # Pre-load answers and key text from key file
            for qk, qdata in open_qs.items():
                full_list = [str(a).strip() for a in qdata.get('full', []) if str(a).strip()]
                part_list = [str(a).strip() for a in qdata.get('partial', []) if str(a).strip()]
                self.acceptable_answers[qk] = full_list
                self.partial_credit_answers[qk] = part_list
                self.openQkeytext[qk] = full_list[0] if full_list else ''
                self.openQkeyimgs[qk] = None   # no key scan image
            # If any questions are missing coords, show draw UI on first available student image
            missing_coords = [qk for qk in open_qs if qk not in self.openQcoords]
            if missing_coords or not open_qs:
                first_student = next((img for img in image_list if img is not None), None)
                coords_before = set(self.openQcoords.keys())
                self._openQkey(first_student)
                # Newly drawn questions get None for key image (student scan, not key)
                for qk in self.openQcoords:
                    if qk not in self.openQkeyimgs:
                        self.openQkeyimgs[qk] = None
                    if qk not in self.openQkeytext:
                        self.openQkeytext[qk] = ''
                    if qk not in self.acceptable_answers:
                        self.acceptable_answers[qk] = []
                    if qk not in self.partial_credit_answers:
                        self.partial_credit_answers[qk] = []
                # Offer to save newly drawn coords back to the key file
                newly_drawn = {qk: self.openQcoords[qk]
                               for qk in self.openQcoords if qk not in coords_before}
                if newly_drawn and key_file_path:
                    updated_oqs = dict(open_qs)
                    for qk, coord_tuple in newly_drawn.items():
                        if qk not in updated_oqs:
                            updated_oqs[qk] = {'full': [], 'partial': []}
                        updated_oqs[qk] = dict(updated_oqs[qk])
                        updated_oqs[qk]['coords'] = list(coord_tuple)
                    new_data = dict(key_file_data)
                    new_data['open_questions'] = updated_oqs
                    try:
                        save_key_file(key_file_path, new_data)
                        print('[KeyFile] Saved drawn coordinates back to key file.', flush=True)
                    except Exception as exc:
                        print(f'[KeyFile] Could not save coords: {exc}', flush=True)
        else:
            # Existing behavior: draw boxes on the key scan (image_list[0])
            self._openQkey(image_list[0])

        if not self.openQcoords:
            # User closed without drawing anything
            cols = []
            _n_students = max(1, (len(image_list) - 1) // self._pages_per_student)
            self.openQres = pd.DataFrame(index=range(_n_students + 1), columns=cols)
            return

        # Step 4a: seed acceptable_answers from key OCR (skip in key-file mode — already set)
        if not self._key_file_mode:
            for qk, txt in self.openQkeytext.items():
                self.acceptable_answers[qk] = [txt] if txt else []

        # Merge any preloaded acceptable-answers file (additive; never overwrites existing)
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
            _pps = self._pages_per_student
            _n_students = max(1, (len(image_list) - 1) // _pps)
            for qk, qv in self.openQcoords.items():
                crops, ids = [], []
                # Include key image as id '0' when available (not in key-file mode)
                if image_list[0] is not None:
                    key_arr = np.array(PILImage.open(image_list[0]).convert('RGB'))
                    crops.append(key_arr[qv[1]:qv[3], qv[0]:qv[2]])
                    ids.append('0')
                _page = self._q_pages.get(qk, 1)
                for s_idx in range(_n_students):
                    actual_pos = 1 + s_idx * _pps + (_page - 1)
                    if actual_pos >= len(image_list):
                        continue
                    img_file = image_list[actual_pos]
                    if img_file is None:
                        continue
                    arr = np.array(PILImage.open(img_file).convert('RGB'))
                    crops.append(arr[qv[1]:qv[3], qv[0]:qv[2]])
                    ids.append(str(s_idx + 1))  # 1-indexed student id = resdf row
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
                # Only overwrite primary answer when NOT in key-file mode
                if not self._key_file_mode:
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

        _pps = self._pages_per_student
        _n_students = max(1, (len(image_list) - 1) // _pps)
        cols = sorted(self.openQcoords.keys(), key=_openq_sort_key)
        self.openQres = pd.DataFrame('', index=range(_n_students + 1), columns=cols)
        self.openQres.loc[0] = 'CC'

        # Phase 2: grade each student's answers for each open-ended question
        openqs = sorted(list(self.openQcoords), key=_openq_sort_key)
        qi = 0
        while qi < len(openqs):
            if qi < 0:
                qi = 0
            k = openqs[qi]
            v = self.openQcoords[k]
            _page = self._q_pages.get(k, 1)
            s_idx = 0
            went_back_q = False
            while s_idx < _n_students:
                if s_idx < 0:
                    s_idx = 0
                actual_pos = 1 + s_idx * _pps + (_page - 1)
                img_path = image_list[actual_pos] if actual_pos < len(image_list) else None
                grade = self._gradeOneAnswer(img_path, k, v, img_idx=s_idx + 1)
                if grade == 'back':
                    s_idx -= 1
                    if s_idx < 0:
                        # Back past start of this question → go to previous question
                        qi -= 1
                        went_back_q = True
                        break
                    continue
                self.openQres.loc[s_idx + 1, k] = grade
                s_idx += 1
            if went_back_q:
                continue   # restart outer loop at new qi
            qi += 1

    def _get_question_label(self, box_index: int, parent=None) -> str:
        '''
        Return a question label for a newly drawn box (0-based index).
        If the ignores list has a number at this index, use it as the default.
        Prompts the user via a Tkinter dialog so they can override.
        '''
        if box_index < len(self._ignores):
            default_num = self._ignores[box_index]
        else:
            default_num = box_index + 1
        dlg_parent = parent if parent is not None else self._root
        try:
            from tkinter import simpledialog
            dlg_parent.lift()
            result = simpledialog.askinteger(
                'Open-Ended Question Number',
                f'Enter the question number for this open-ended answer box\n(default: {default_num}):',
                initialvalue=default_num,
                parent=dlg_parent,
            )
            if result is not None:
                return 'openQ_' + str(result)
        except Exception:
            pass
        return 'openQ_' + str(default_num)

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
        imgpath may be None (key-file mode, all coords already loaded) — returns immediately.
        '''
        if imgpath is None:
            return
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
                rx1, ry1, rx2, ry2 = current_rect
                draw.rectangle(
                    [min(rx1, rx2), min(ry1, ry2), max(rx1, rx2), max(ry1, ry2)],
                    outline=(220, 100, 60), width=2)
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
            box_index = len(coords)
            qk = self._get_question_label(box_index, parent=win)
            # ensure no duplicate labels
            while qk in coords:
                try:
                    base, num = qk.rsplit('_', 1)
                    qk = f'{base}_{int(num) + 1}'
                except ValueError:
                    qk = qk + '_2'
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

        # Build display image — stack key crop (if available) above student crop
        key_crop = self.openQkeyimgs.get(k)
        if key_crop is not None:
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
        else:
            # Key-file mode: no key scan image — show student crop alone
            pil_stacked = PILImage.fromarray(student_crop)

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
        # Pin every grading window to the same screen position so they don't cascade.
        # On the first call _grading_win_geometry is unset; we let the window land
        # wherever the WM puts it, then record that position for all future calls.
        if hasattr(self, '_grading_win_geometry') and self._grading_win_geometry:
            win.geometry(self._grading_win_geometry)
        _win_bg = win.cget('bg')

        if key_crop is not None:
            header_text = 'KEY (top) ↕ Student (bottom)'
        else:
            header_text = 'Student answer (answers imported from key file)'
        tk.Label(win, text=header_text,
                 font=('Arial', 12, 'bold')).pack(anchor='w', padx=8, pady=(6, 0))
        tk_img = _pil_to_tkphoto(pil_stacked, master=win)
        img_lbl = tk.Label(win, image=tk_img)
        img_lbl.pack(padx=8, pady=4)
        img_lbl.tk_img = tk_img

        # In key-file mode, show a read-only panel of the key answers
        if key_crop is None:
            _full = self.acceptable_answers.get(k, [])
            _part = self.partial_credit_answers.get(k, [])
            _full_str = '  |  '.join(_full) if _full else '(none)'
            _part_str = '  |  '.join(_part) if _part else '(none)'
            key_info_frame = tk.Frame(win, bg='#e8f4e8', relief='groove', bd=1)
            key_info_frame.pack(fill='x', padx=8, pady=(0, 4))
            tk.Label(key_info_frame, text=f'✓ Full credit: {_full_str}',
                     font=('Arial', 11), bg='#e8f4e8', fg='#166534',
                     anchor='w', justify='left', wraplength=680).pack(
                fill='x', padx=8, pady=(4, 2))
            tk.Label(key_info_frame, text=f'~ Partial credit: {_part_str}',
                     font=('Arial', 11), bg='#e8f4e8', fg='#92400e',
                     anchor='w', justify='left', wraplength=680).pack(
                fill='x', padx=8, pady=(2, 4))

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
            # Capture position before destroying — picks up any move the user made.
            self._grading_win_geometry = f'+{win.winfo_x()}+{win.winfo_y()}'
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
        into the app_data/ subfolder next to results.csv.
          app_data/{stem}_openq_answers.json
          app_data/{stem}_openq_transcriptions.json
          app_data/{stem}_openq_gradeconfig.json  (only written when grade_config provided)
        """
        app_data_dir = Path(csv_path).parent / 'app_data'
        app_data_dir.mkdir(exist_ok=True)
        stem = str(app_data_dir / Path(csv_path).stem)

        try:
            merged_answers: dict = {}
            for qk in set(list(self.acceptable_answers.keys()) +
                          list(self.partial_credit_answers.keys())):
                coords = self.openQcoords.get(qk)
                merged_answers[qk] = {
                    'full': self.acceptable_answers.get(qk, []),
                    'partial': self.partial_credit_answers.get(qk, []),
                    'coords': list(coords) if coords else None,
                }
            # Also save coords for any questions that have them but no answers yet
            for qk, coords in self.openQcoords.items():
                if qk not in merged_answers:
                    merged_answers[qk] = {
                        'full': [],
                        'partial': [],
                        'coords': list(coords),
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

            # Write updated acceptable/partial answers back to the key file
            if self._key_file_mode and self._key_file_path:
                try:
                    current_key = load_key_file(self._key_file_path) or {}
                    open_qs = dict(current_key.get('open_questions', {}))
                    for qk in set(list(self.acceptable_answers.keys()) +
                                  list(self.partial_credit_answers.keys()) +
                                  list(self.openQcoords.keys())):
                        entry = dict(open_qs.get(qk, {}))
                        entry['full'] = self.acceptable_answers.get(qk, [])
                        entry['partial'] = self.partial_credit_answers.get(qk, [])
                        coords = self.openQcoords.get(qk)
                        if coords:
                            entry['coords'] = list(coords)
                        if 'page' not in entry:
                            entry['page'] = self._q_pages.get(qk, 1)
                        open_qs[qk] = entry
                    current_key['open_questions'] = open_qs
                    save_key_file(self._key_file_path, current_key)
                    print(f'[OpenQ] Key file updated → {self._key_file_path}', flush=True)
                except Exception as _kexc:
                    print(f'[OpenQ] Could not update key file: {_kexc}', flush=True)
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

        # Prefer new app_data/ layout; fall back to old layout for existing runs
        app_data_dir = Path(csv_path).parent / 'app_data'
        new_stem = str(app_data_dir / Path(csv_path).stem)
        old_stem = str(Path(csv_path).with_suffix(''))
        if Path(new_stem + '_openq_answers.json').exists():
            stem = new_stem
        else:
            stem = old_stem
        self._artifact_stem = stem

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
            stem = self._artifact_stem
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


class KeyFileEditorDialog:
    """
    GUI dialog for creating and editing JSON exam key files.

    Opens a two-panel modal window:
      Left  — scrollable question list (bubble + open-ended) + add/remove buttons.
      Right — editor form that changes based on the selected question type.
               Bubble:       Q number + answer entry.
               Open-ended:   full/partial answer listboxes + coordinate fields
                              + "Draw on image…" button.

    Usage:
        dlg = KeyFileEditorDialog(parent, path='')
        # After the user saves and closes, dlg.saved_path holds the file path
        # (empty string if the user cancelled without saving).
    """

    def __init__(self, parent, path: str = ''):
        self._parent = parent
        self._path = path
        self.saved_path = ''

        # Internal data model
        self._bubble: dict = {}   # {qk: answer_str}
        self._open_qs: dict = {}  # {qk: {"full": [...], "partial": [...], "coords": [...] or None}}

        if path and Path(path).exists():
            data = load_key_file(path)
            if data:
                self._bubble = dict(data.get('bubble_answers', {}))
                # Deep-copy open question entries
                for qk, qdata in data.get('open_questions', {}).items():
                    _c = qdata.get('coords')
                    self._open_qs[qk] = {
                        'full': list(qdata.get('full', [])),
                        'partial': list(qdata.get('partial', [])),
                        'coords': list(_c) if _c and len(_c) == 4 else None,
                        'page': int(qdata.get('page', 1) or 1),
                    }

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        win = tk.Toplevel(self._parent)
        win.title('Key File Editor')
        win.resizable(True, True)
        win.grab_set()
        self._win = win

        _F  = ('Arial', 11)
        _FB = ('Arial', 11, 'bold')

        # ── Header: current file path ─────────────────────────────────────
        hdr = tk.Frame(win)
        hdr.pack(fill='x', padx=8, pady=(8, 4))
        tk.Label(hdr, text='File:', font=_FB).pack(side='left')
        self._path_var = tk.StringVar(value=self._path or '(unsaved new file)')
        tk.Label(hdr, textvariable=self._path_var, font=_F,
                 fg='#374151', anchor='w').pack(side='left', padx=6)

        # ── Main body ─────────────────────────────────────────────────────
        body = tk.Frame(win)
        body.pack(fill='both', expand=True, padx=8, pady=4)

        # ── Left panel: question list ─────────────────────────────────────
        left = tk.Frame(body, width=230)
        left.pack(side='left', fill='y', padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text='Questions', font=_FB).pack(anchor='w')

        list_frame = tk.Frame(left)
        list_frame.pack(fill='both', expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient='vertical')
        self._q_listbox = tk.Listbox(
            list_frame, width=28, font=_F,
            exportselection=False,
            yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._q_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self._q_listbox.pack(side='left', fill='both', expand=True)

        q_btn_frame = tk.Frame(left)
        q_btn_frame.pack(fill='x', pady=(4, 0))
        tk.Button(q_btn_frame, text='+ Bubble Q', font=_F,
                  command=self._add_bubble_q).pack(side='left', padx=(0, 4))
        tk.Button(q_btn_frame, text='+ Open-Ended Q', font=_F,
                  command=self._add_open_q).pack(side='left', padx=(0, 4))
        tk.Button(q_btn_frame, text='Remove', font=_F,
                  command=self._remove_q).pack(side='left')

        # ── Right panel: editor (rebuilt dynamically on selection) ────────
        self._right = tk.Frame(body)
        self._right.pack(side='left', fill='both', expand=True)
        self._current_q: dict = {'key': None, 'type': None}  # 'bubble' or 'open'

        # ── Bottom bar ────────────────────────────────────────────────────
        bot = tk.Frame(win)
        bot.pack(fill='x', padx=8, pady=(4, 8))
        self._status_var = tk.StringVar(value='')
        tk.Label(bot, textvariable=self._status_var, font=_F,
                 fg='#16a34a').pack(side='left')
        tk.Button(bot, text='Save As…', font=_F,
                  command=self._save_as).pack(side='right', padx=(4, 0))
        tk.Button(bot, text='Save', font=_FB, bg='#bbf7d0',
                  command=self._save).pack(side='right', padx=4)
        tk.Button(bot, text='Close', font=_F,
                  command=win.destroy).pack(side='right', padx=4)

        # ── Bind events ──────────────────────────────────────────────────
        self._q_listbox.bind('<<ListboxSelect>>', self._on_q_select)
        win.protocol('WM_DELETE_WINDOW', win.destroy)

        # Populate the list
        self._refresh_q_list()

        self._parent.wait_window(win)

    # ------------------------------------------------------------------
    # Question list helpers
    # ------------------------------------------------------------------

    def _q_display_text(self, qk: str) -> str:
        if qk in self._bubble:
            return f'{qk}  →  {self._bubble[qk]}'
        qdata = self._open_qs.get(qk, {})
        n_full = len(qdata.get('full', []))
        n_part = len(qdata.get('partial', []))
        has_coords = '✓' if qdata.get('coords') else '–'
        return f'{qk}  ({n_full}F / {n_part}P  coords:{has_coords})'

    def _refresh_q_list(self, select_key: str | None = None):
        self._q_listbox.delete(0, tk.END)
        all_keys = (
            sorted(self._bubble.keys()) +
            sorted(self._open_qs.keys(), key=_openq_sort_key)
        )
        for k in all_keys:
            self._q_listbox.insert(tk.END, self._q_display_text(k))
        if select_key and select_key in all_keys:
            idx = all_keys.index(select_key)
            self._q_listbox.selection_set(idx)
            self._q_listbox.see(idx)

    def _current_selected_qk(self) -> str | None:
        sel = self._q_listbox.curselection()
        if not sel:
            return None
        all_keys = sorted(self._bubble.keys()) + sorted(self._open_qs.keys(), key=_openq_sort_key)
        idx = sel[0]
        if idx < len(all_keys):
            return all_keys[idx]
        return None

    def _on_q_select(self, event=None):
        self._commit_current_edit()
        qk = self._current_selected_qk()
        if qk is None:
            return
        for w in self._right.winfo_children():
            w.destroy()
        if qk in self._bubble:
            self._current_q['key'] = qk
            self._current_q['type'] = 'bubble'
            self._build_bubble_editor(qk)
        else:
            self._current_q['key'] = qk
            self._current_q['type'] = 'open'
            self._build_open_editor(qk)

    # ------------------------------------------------------------------
    # Add / Remove questions
    # ------------------------------------------------------------------

    def _add_bubble_q(self):
        self._commit_current_edit()
        dlg = tk.Toplevel(self._win)
        dlg.title('Add Bubble Question')
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text='Question number (1–150):', font=('Arial', 11)).grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky='w')
        num_var = tk.StringVar()
        num_entry = tk.Entry(dlg, textvariable=num_var, width=8, font=('Arial', 11))
        num_entry.grid(row=0, column=1, padx=10, pady=(10, 4), sticky='w')
        tk.Label(dlg, text='Answer (e.g. A or BCE or ignore):',
                 font=('Arial', 11)).grid(row=1, column=0, padx=10, pady=4, sticky='w')
        ans_var = tk.StringVar()
        ans_entry = tk.Entry(dlg, textvariable=ans_var, width=12, font=('Arial', 11))
        ans_entry.grid(row=1, column=1, padx=10, pady=4, sticky='w')
        status = tk.Label(dlg, text='', font=('Arial', 10), fg='red')
        status.grid(row=2, column=0, columnspan=2, padx=10)

        def _do_add():
            raw = num_var.get().strip()
            _raw_ans = ans_var.get().strip()
            ans = _raw_ans.lower() if _raw_ans.lower() == 'ignore' else _raw_ans.upper()
            if not raw:
                status.config(text='Enter a question number.')
                return
            try:
                n = int(raw)
                if not (1 <= n <= 150):
                    raise ValueError
            except ValueError:
                status.config(text='Number must be 1–150.')
                return
            qk = 'Q' + format(n, '03d')
            self._bubble[qk] = ans if ans else '-'
            self._refresh_q_list(select_key=qk)
            dlg.destroy()
            self._on_q_select()

        btn_row = tk.Frame(dlg)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(4, 10), padx=10, sticky='e')
        tk.Button(btn_row, text='Add', command=_do_add,
                  font=('Arial', 11), bg='#bbf7d0').pack(side='left', padx=(0, 6))
        tk.Button(btn_row, text='Cancel', command=dlg.destroy,
                  font=('Arial', 11)).pack(side='left')
        num_entry.focus_force()
        ans_entry.bind('<Return>', lambda e: _do_add())
        dlg.bind('<Escape>', lambda e: dlg.destroy())
        self._win.wait_window(dlg)
        self._win.grab_set()  # restore grab after inner modal closes

    def _add_open_q(self):
        self._commit_current_edit()
        existing_n = []
        for k in self._open_qs:
            try:
                existing_n.append(int(k.split('_')[-1]))
            except ValueError:
                pass
        next_n = max(existing_n, default=0) + 1
        qk = f'openQ_{next_n}'
        self._open_qs[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
        self._refresh_q_list(select_key=qk)
        self._on_q_select()

    def _remove_q(self):
        self._commit_current_edit()
        qk = self._current_selected_qk()
        if qk is None:
            return
        if tkinter.messagebox.askyesno(
                'Remove question',
                f'Remove "{qk}" from the key file?',
                parent=self._win):
            self._bubble.pop(qk, None)
            self._open_qs.pop(qk, None)
            self._current_q['key'] = None
            self._current_q['type'] = None
            for w in self._right.winfo_children():
                w.destroy()
            self._refresh_q_list()

    # ------------------------------------------------------------------
    # Bubble editor
    # ------------------------------------------------------------------

    def _build_bubble_editor(self, qk: str):
        _F = ('Arial', 11)
        _FB = ('Arial', 11, 'bold')
        f = self._right
        tk.Label(f, text=f'Bubble Question: {qk}', font=_FB).pack(anchor='w', pady=(4, 8))
        row_frame = tk.Frame(f)
        row_frame.pack(fill='x', padx=4)
        tk.Label(row_frame, text='Answer:', font=_F).pack(side='left')
        self._bubble_ans_var = tk.StringVar(value=self._bubble.get(qk, ''))
        tk.Entry(row_frame, textvariable=self._bubble_ans_var, width=18,
                 font=('Courier', 13)).pack(side='left', padx=6)
        ignore_var = tk.BooleanVar(value=(self._bubble.get(qk, '').lower() == 'ignore'))
        def _toggle_ignore():
            if ignore_var.get():
                self._bubble_ans_var.set('ignore')
            else:
                if self._bubble_ans_var.get().lower() == 'ignore':
                    self._bubble_ans_var.set('')
        tk.Checkbutton(row_frame, text='Ignore this question', variable=ignore_var,
                       command=_toggle_ignore, font=_F).pack(side='left', padx=8)
        tk.Label(f, text='Enter answer letters (A–E) or "ignore".', font=('Arial', 10),
                 fg='gray50').pack(anchor='w', padx=4, pady=(4, 0))

    # ------------------------------------------------------------------
    # Open-ended editor
    # ------------------------------------------------------------------

    def _build_open_editor(self, qk: str):
        _F  = ('Arial', 11)
        _FB = ('Arial', 11, 'bold')
        f = self._right
        tk.Label(f, text=f'Open-Ended Question: {qk}', font=_FB).pack(anchor='w', pady=(4, 6))

        qdata = self._open_qs[qk]

        # ── Full-credit answers ───────────────────────────────────────────
        tk.Label(f, text='Full-credit answers (first = primary):', font=_F).pack(anchor='w')
        full_list_frame = tk.Frame(f)
        full_list_frame.pack(fill='x', padx=4, pady=(2, 0))
        full_scroll = tk.Scrollbar(full_list_frame, orient='vertical')
        self._full_listbox = tk.Listbox(full_list_frame, height=5, font=_F,
                                        exportselection=False,
                                        yscrollcommand=full_scroll.set)
        full_scroll.config(command=self._full_listbox.yview)
        full_scroll.pack(side='right', fill='y')
        self._full_listbox.pack(side='left', fill='x', expand=True)
        for ans in qdata.get('full', []):
            self._full_listbox.insert(tk.END, ans)
        _full_edit_idx = [None]  # mutable container: index being edited, or None

        full_input_frame = tk.Frame(f)
        full_input_frame.pack(fill='x', padx=4, pady=(2, 4))
        self._full_new_var = tk.StringVar()
        full_entry = tk.Entry(full_input_frame, textvariable=self._full_new_var,
                              width=32, font=_F)
        full_entry.pack(side='left', padx=(0, 6))

        def _add_full():
            new = self._full_new_var.get().strip()
            if not new:
                return
            if _full_edit_idx[0] is not None:
                others = [self._full_listbox.get(i) for i in range(self._full_listbox.size())
                          if i != _full_edit_idx[0]]
                if new.lower() not in [e.lower() for e in others]:
                    self._full_listbox.delete(_full_edit_idx[0])
                    self._full_listbox.insert(_full_edit_idx[0], new)
                _full_edit_idx[0] = None
                self._full_new_var.set('')
                return
            existing = [self._full_listbox.get(i) for i in range(self._full_listbox.size())]
            if new.lower() not in [e.lower() for e in existing]:
                self._full_listbox.insert(tk.END, new)
            self._full_new_var.set('')

        def _remove_full():
            sel = self._full_listbox.curselection()
            if sel:
                self._full_listbox.delete(sel[0])
                _full_edit_idx[0] = None
                self._full_new_var.set('')

        def _on_full_double(event):
            s = self._full_listbox.curselection()
            if s:
                _full_edit_idx[0] = s[0]
                self._full_new_var.set(self._full_listbox.get(s[0]))
                full_entry.focus_set()
                full_entry.select_range(0, tk.END)

        full_entry.bind('<Return>', lambda e: _add_full())
        self._full_listbox.bind('<Double-Button-1>', _on_full_double)
        tk.Button(full_input_frame, text='Add', command=_add_full,
                  font=_F, bg='#bbf7d0').pack(side='left', padx=(0, 4))
        tk.Button(full_input_frame, text='Remove selected', command=_remove_full,
                  font=_F).pack(side='left')
        tk.Label(f, text='(Double-click an answer to edit it in place)',
                 font=('Arial', 9), fg='gray50').pack(anchor='w', padx=4)

        # ── Partial-credit answers ────────────────────────────────────────
        tk.Label(f, text='Partial-credit answers (auto-graded CX):', font=_F).pack(
            anchor='w', pady=(8, 0))
        part_list_frame = tk.Frame(f)
        part_list_frame.pack(fill='x', padx=4, pady=(2, 0))
        part_scroll = tk.Scrollbar(part_list_frame, orient='vertical')
        self._part_listbox = tk.Listbox(part_list_frame, height=4, font=_F,
                                        exportselection=False,
                                        yscrollcommand=part_scroll.set)
        part_scroll.config(command=self._part_listbox.yview)
        part_scroll.pack(side='right', fill='y')
        self._part_listbox.pack(side='left', fill='x', expand=True)
        for ans in qdata.get('partial', []):
            self._part_listbox.insert(tk.END, ans)

        part_input_frame = tk.Frame(f)
        part_input_frame.pack(fill='x', padx=4, pady=(2, 4))
        self._part_new_var = tk.StringVar()
        part_entry = tk.Entry(part_input_frame, textvariable=self._part_new_var,
                              width=32, font=_F)
        part_entry.pack(side='left', padx=(0, 6))

        def _add_part():
            new = self._part_new_var.get().strip()
            if not new:
                return
            existing = [self._part_listbox.get(i) for i in range(self._part_listbox.size())]
            if new.lower() not in [e.lower() for e in existing]:
                self._part_listbox.insert(tk.END, new)
            self._part_new_var.set('')

        def _remove_part():
            sel = self._part_listbox.curselection()
            if sel:
                self._part_listbox.delete(sel[0])

        part_entry.bind('<Return>', lambda e: _add_part())
        tk.Button(part_input_frame, text='Add', command=_add_part,
                  font=_F, bg='#fef08a').pack(side='left', padx=(0, 4))
        tk.Button(part_input_frame, text='Remove selected', command=_remove_part,
                  font=_F).pack(side='left')

        # ── Coordinates ───────────────────────────────────────────────────
        tk.Frame(f, height=1, bg='gray70').pack(fill='x', padx=4, pady=(8, 4))
        tk.Label(f, text='Answer area coordinates (aligned-image pixels):', font=_F).pack(
            anchor='w', padx=4)
        coord_frame = tk.Frame(f)
        coord_frame.pack(fill='x', padx=4, pady=(2, 4))

        coords = qdata.get('coords') or [0, 0, 0, 0]
        self._coord_vars = [tk.StringVar(value=str(int(c))) for c in coords]
        for i, label in enumerate(['X1:', 'Y1:', 'X2:', 'Y2:']):
            tk.Label(coord_frame, text=label, font=_F).grid(row=0, column=i*2, padx=(6 if i else 0, 2))
            tk.Entry(coord_frame, textvariable=self._coord_vars[i],
                     width=6, font=_F).grid(row=0, column=i*2+1, padx=(0, 6))

        _has_coords = bool(qdata.get('coords'))
        coord_status = '✓ Coordinates set' if _has_coords else '⚠ No coordinates — will prompt at scan time'
        self._coord_status_var = tk.StringVar(value=coord_status)
        self._coord_status_lbl = tk.Label(f, textvariable=self._coord_status_var,
                                          font=('Arial', 10),
                                          fg='#166534' if _has_coords else '#92400e')
        self._coord_status_lbl.pack(anchor='w', padx=4)

        coord_btn_frame = tk.Frame(f)
        coord_btn_frame.pack(fill='x', padx=4, pady=(2, 0))
        tk.Button(coord_btn_frame, text='Clear coordinates', font=_F,
                  command=lambda: self._clear_coords(qk)).pack(side='left', padx=(0, 6))
        tk.Button(coord_btn_frame, text='Draw on image…', font=_F, bg='#dbeafe',
                  command=lambda: self._draw_on_image(qk)).pack(side='left')

        # ── Page number ───────────────────────────────────────────────────
        tk.Frame(f, height=1, bg='gray70').pack(fill='x', padx=4, pady=(8, 4))
        page_outer = tk.Frame(f)
        page_outer.pack(fill='x', padx=4)
        tk.Label(page_outer, text='Page number (for multi-page exams):', font=_F).pack(side='left')
        self._page_var = tk.StringVar(value=str(self._open_qs[qk].get('page', 1) or 1))
        tk.Entry(page_outer, textvariable=self._page_var, width=5, font=_F).pack(side='left', padx=6)
        tk.Label(page_outer, text='(1 = first/only page)', font=('Arial', 9),
                 fg='gray50').pack(side='left')

    def _clear_coords(self, qk: str):
        if qk in self._open_qs:
            self._open_qs[qk]['coords'] = None
            for v in self._coord_vars:
                v.set('0')
            self._coord_status_var.set('⚠ No coordinates — will prompt at scan time')

    def _draw_on_image(self, qk: str):
        """Let the user pick a scan image and draw a single box on it to set coords."""
        from tkinter import filedialog as _fd
        imgpath = _fd.askopenfilename(
            title='Choose a scan image (JPG/PDF) to draw the answer area on',
            filetypes=[('JPEG', '*.jpg'), ('JPEG', '*.jpeg'), ('PDF', '*.pdf')],
            parent=self._win)
        if not imgpath:
            return

        # Align the image exactly as the scanner would
        try:
            aligned_arr = _load_aligned_arr(imgpath)
        except Exception as exc:
            tkinter.messagebox.showerror('Draw on image',
                                    f'Could not load/align image:\n{exc}',
                                    parent=self._win)
            return

        pil_full = PILImage.fromarray(aligned_arr)
        dispres = 0.5
        W, H = pil_full.size
        disp_w = max(1, int(W * dispres))
        disp_h = max(1, int(H * dispres))
        pil_disp = pil_full.resize((disp_w, disp_h), PILImage.LANCZOS)

        # Show current coords as pre-drawn box if set
        current_coords = self._open_qs[qk].get('coords')
        drawn = {'box': list(current_coords) if current_coords and len(current_coords) == 4 else None}

        draw_win = tk.Toplevel(self._win)
        draw_win.title(f'Draw answer area for {qk} — press G or Done when finished')
        draw_win.resizable(False, False)
        draw_win.grab_set()

        canvas = tk.Canvas(draw_win, width=disp_w, height=disp_h, cursor='crosshair')
        canvas.pack()
        tk.Label(draw_win, text='Left-click drag to draw a box. Drag again to redraw.',
                 font=('Arial', 10)).pack()

        state = {'drawing': False, 'sx': 0, 'sy': 0, 'tk_img': None}

        def redraw(current_rect=None):
            img = pil_disp.copy()
            draw = PILImageDraw.Draw(img)
            if drawn['box']:
                b = drawn['box']
                x1, y1, x2, y2 = (int(c * dispres) for c in b)
                draw.rectangle([x1, y1, x2, y2], outline=(60, 100, 220), width=2)
                draw.text((x1 + 4, y1 + 2), qk, fill=(60, 100, 220))
            if current_rect:
                rx1, ry1, rx2, ry2 = current_rect
                draw.rectangle(
                    [min(rx1, rx2), min(ry1, ry2), max(rx1, rx2), max(ry1, ry2)],
                    outline=(220, 100, 60), width=2)
            state['tk_img'] = _pil_to_tkphoto(img, master=draw_win)
            canvas.create_image(0, 0, anchor='nw', image=state['tk_img'])

        def on_press(e):
            state['drawing'] = True
            state['sx'], state['sy'] = e.x, e.y

        def on_drag(e):
            if state['drawing']:
                redraw([state['sx'], state['sy'], e.x, e.y])

        def on_release(e):
            if not state['drawing']:
                return
            state['drawing'] = False
            ex, ey = e.x, e.y
            if abs(ex - state['sx']) < 5 or abs(ey - state['sy']) < 5:
                return
            drawn['box'] = [
                int(min(state['sx'], ex) / dispres),
                int(min(state['sy'], ey) / dispres),
                int(max(state['sx'], ex) / dispres),
                int(max(state['sy'], ey) / dispres),
            ]
            redraw()

        def done():
            draw_win.destroy()

        canvas.bind('<ButtonPress-1>', on_press)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_release)
        draw_win.bind('<g>', lambda e: done())
        draw_win.bind('<G>', lambda e: done())

        btn_f = tk.Frame(draw_win)
        btn_f.pack(fill='x', pady=4)
        tk.Button(btn_f, text='Done', command=done,
                  font=('Arial', 11)).pack(side='right', padx=6)

        redraw()
        draw_win.focus_force()
        self._win.wait_window(draw_win)
        self._win.grab_set()  # restore grab after inner draw modal closes

        if drawn['box']:
            # Store coords and update UI
            self._open_qs[qk]['coords'] = drawn['box']
            for i, v in enumerate(self._coord_vars):
                v.set(str(drawn['box'][i]))
            self._coord_status_var.set('✓ Coordinates set')
            if hasattr(self, '_coord_status_lbl'):
                self._coord_status_lbl.config(fg='#166534')
            self._refresh_q_list(select_key=qk)

    # ------------------------------------------------------------------
    # Commit edits
    # ------------------------------------------------------------------

    def _commit_current_edit(self):
        """Read the right-panel form values back into the data model."""
        qk = self._current_q.get('key')
        if qk is None:
            return
        if self._current_q['type'] == 'bubble':
            if hasattr(self, '_bubble_ans_var') and qk in self._bubble:
                _raw = self._bubble_ans_var.get().strip()
                self._bubble[qk] = _raw.lower() if _raw.lower() == 'ignore' else (_raw.upper() or '-')
        elif self._current_q['type'] == 'open':
            if qk not in self._open_qs:
                return
            if hasattr(self, '_full_listbox'):
                self._open_qs[qk]['full'] = [
                    self._full_listbox.get(i) for i in range(self._full_listbox.size())]
            if hasattr(self, '_part_listbox'):
                self._open_qs[qk]['partial'] = [
                    self._part_listbox.get(i) for i in range(self._part_listbox.size())]
            if hasattr(self, '_coord_vars'):
                try:
                    vals = [int(v.get()) for v in self._coord_vars]
                    if any(c != 0 for c in vals):
                        self._open_qs[qk]['coords'] = vals
                    else:
                        self._open_qs[qk]['coords'] = None
                except ValueError:
                    pass  # leave coords unchanged if entry is bad
            if hasattr(self, '_page_var'):
                try:
                    self._open_qs[qk]['page'] = max(1, int(self._page_var.get()))
                except ValueError:
                    pass  # leave page unchanged if entry is bad
        # Refresh list text (counts may have changed)
        self._refresh_q_list(select_key=qk)

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _to_data(self) -> dict:
        self._commit_current_edit()
        _skip_ns = []
        for qk in self._open_qs:
            try:
                _skip_ns.append(int(qk.split('_')[-1]))
            except ValueError:
                pass
        _skip_str = ','.join(str(n) for n in sorted(_skip_ns))
        _total = sum(1 for v in self._bubble.values() if v != 'ignore')
        return {
            'bubble_answers': dict(self._bubble),
            'open_questions': {
                qk: {
                    'full': list(qdata.get('full', [])),
                    'partial': list(qdata.get('partial', [])),
                    'coords': qdata.get('coords'),
                    'page': qdata.get('page', 1),
                }
                for qk, qdata in self._open_qs.items()
            },
            'metadata': {
                'num_questions': _total,
                'questions_to_skip': _skip_str,
            },
        }

    def _save(self):
        if not self._path:
            self._save_as()
            return
        try:
            save_key_file(self._path, self._to_data())
            self.saved_path = self._path
            self._path_var.set(self._path)
            self._status_var.set(f'Saved: {Path(self._path).name}')
        except Exception as exc:
            tkinter.messagebox.showerror('Save error', str(exc), parent=self._win)

    def _save_as(self):
        from tkinter import filedialog as _fd
        path = _fd.asksaveasfilename(
            title='Save key file as…',
            defaultextension='.json',
            filetypes=[('CSV key file', '*.csv'),
                       ('JSON files', '*.json')],
            parent=self._win)
        if not path:
            return
        self._path = path
        self._save()


class KeyBuilderDialog:
    """
    Image-first GUI dialog for building a new exam key CSV from template scan images.

    Modes
    -----
    'blank'  (default) — draw coordinate boxes around open-ended answer areas only.
                         MC bubble answers must be added manually.
    'filled'           — load an instructor-filled answer sheet:
                         * MC bubbles are auto-scanned when the page is loaded.
                         * After drawing open-ended boxes the user can click
                           'Scan handwriting (OCR)' to pre-fill answers.

    Parameters
    ----------
    mode             : 'blank' or 'filled'
    num_mc_questions : number of bubble questions to scan (0 = skip bubble scan)
    ignores          : list of question numbers to skip (e.g. [3, 7])
    use_ai           : use Claude AI OCR instead of local TrOCR
    api_key          : Anthropic API key
    ai_context       : subject-specific hint for the AI model

    Usage:
        dlg = KeyBuilderDialog(parent)
        if dlg.saved_path:
            print(f'Key saved to {dlg.saved_path}')
    """

    def __init__(self, parent, path: str = '', mode: str = 'blank',
                 num_mc_questions: int = 0, ignores=None,
                 use_ai: bool = False, api_key: str = '', ai_context: str = ''):
        self._parent = parent
        self._path = path
        self.saved_path: str = ''
        self._mode = mode                      # 'blank' or 'filled'
        self._num_mc_questions = max(0, int(num_mc_questions))
        self._ignores = ignores                # list[int] | None
        self._use_ai = use_ai
        self._api_key = api_key
        self._ai_context = ai_context

        # Page data
        self._pages: list[dict] = []
        # Each page: {'img_path': str, 'aligned_arr': np.ndarray, 'pil_disp': PILImage}

        # Question data
        self._questions: dict = {}
        # {qk: {'page': int, 'coords': [x1,y1,x2,y2] or None, 'full': [str,...], 'partial': [str,...]}}

        self._bubble: dict = {}
        # {qk: answer_str}

        self._current_page_idx: int = 0
        self._current_q_key: str | None = None

        # Pre-load an existing key file if given
        if path and Path(path).exists():
            data = load_key_file(path)
            if data:
                self._bubble = dict(data.get('bubble_answers', {}))
                for qk, qdata in data.get('open_questions', {}).items():
                    _c = qdata.get('coords')
                    self._questions[qk] = {
                        'page': int(qdata.get('page', 1) or 1),
                        'coords': list(_c) if _c and len(_c) == 4 else None,
                        'full': list(qdata.get('full', [])),
                        'partial': list(qdata.get('partial', [])),
                    }

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        win = tk.Toplevel(self._parent)
        win.title('Build Exam Key')
        win.resizable(True, True)
        win.grab_set()
        self._win = win

        _F  = ('Arial', 11)
        _FB = ('Arial', 11, 'bold')

        # ── Persistent bottom bar (always visible) ────────────────────────
        bot_bar = tk.Frame(win)
        bot_bar.pack(side='bottom', fill='x', padx=8, pady=(4, 8))
        self._status_var = tk.StringVar(value='')
        tk.Label(bot_bar, textvariable=self._status_var, font=_F, fg='#16a34a').pack(side='left')
        tk.Button(bot_bar, text='Close', font=_F,
                  command=win.destroy).pack(side='right', padx=(4, 0))
        tk.Button(bot_bar, text='Save key as CSV…', font=_FB, bg='#bbf7d0',
                  command=self._save_csv).pack(side='right', padx=4)

        # ── Top: page navigation bar ──────────────────────────────────────
        top_bar = tk.Frame(win)
        top_bar.pack(side='top', fill='x', padx=8, pady=(8, 4))

        tk.Button(top_bar, text='Add page image…', font=_F,
                  command=self._add_page).pack(side='left', padx=(0, 4))
        tk.Button(top_bar, text='Remove page', font=_F,
                  command=self._remove_page).pack(side='left', padx=(0, 12))

        self._page_nav_var = tk.StringVar(value='No pages loaded')
        tk.Label(top_bar, textvariable=self._page_nav_var, font=_F).pack(side='left', padx=(0, 8))

        tk.Button(top_bar, text='← Prev', font=_F,
                  command=self._prev_page).pack(side='left', padx=(0, 2))
        tk.Button(top_bar, text='Next →', font=_F,
                  command=self._next_page).pack(side='left', padx=(0, 4))

        # ── Vertical PanedWindow: canvas pane (top) / data pane (bottom) ─
        paned = tk.PanedWindow(win, orient='vertical', sashrelief='raised', sashwidth=6)
        paned.pack(side='top', fill='both', expand=True, padx=8, pady=(0, 4))

        # ── Canvas pane ───────────────────────────────────────────────────
        canvas_outer = tk.Frame(paned, relief='sunken', bd=1)
        paned.add(canvas_outer, minsize=120)

        self._canvas_w = 700
        self._canvas_h = 320
        canvas_scroll_x = tk.Scrollbar(canvas_outer, orient='horizontal')
        canvas_scroll_y = tk.Scrollbar(canvas_outer, orient='vertical')
        self._canvas = tk.Canvas(canvas_outer,
                                 width=self._canvas_w, height=self._canvas_h,
                                 cursor='crosshair', bg='#d0d0d0',
                                 xscrollcommand=canvas_scroll_x.set,
                                 yscrollcommand=canvas_scroll_y.set)
        canvas_scroll_x.config(command=self._canvas.xview)
        canvas_scroll_y.config(command=self._canvas.yview)
        canvas_scroll_y.pack(side='right', fill='y')
        canvas_scroll_x.pack(side='bottom', fill='x')
        self._canvas.pack(side='left', fill='both', expand=True)

        # Drawing events
        self._draw_state = {'drawing': False, 'sx': 0, 'sy': 0, 'tk_img': None}
        self._canvas.bind('<ButtonPress-1>', self._on_canvas_press)
        self._canvas.bind('<B1-Motion>', self._on_canvas_drag)
        self._canvas.bind('<ButtonRelease-1>', self._on_canvas_release)

        inst_row = tk.Frame(canvas_outer)
        inst_row.pack(side='bottom', fill='x', padx=4, pady=2)
        if self._mode == 'filled':
            inst_text = ('Instructor-filled mode: MC bubbles auto-scanned on load. '
                         'Draw boxes for handwritten areas, then click “Scan handwriting (OCR)”.')
            tk.Button(inst_row, text='Scan handwriting (OCR)',
                      command=self._scan_handwriting_ocr,
                      font=_F, bg='#dbeafe').pack(side='right', padx=4)
        else:
            inst_text = 'Left-click drag to mark each open-ended question area.'
        tk.Label(inst_row, text=inst_text,
                 font=('Arial', 10), fg='gray40').pack(side='left')
        tk.Button(inst_row, text='Undo last box', font=_F,
                  command=self._undo_last_box).pack(side='right', padx=4)

        # ── Data pane (left list + right answer editor) ───────────────────
        data_pane = tk.Frame(paned)
        paned.add(data_pane, minsize=160)

        # ── Left column: question list + MC answers ───────────────────────
        left = tk.Frame(data_pane, width=260)
        left.pack(side='left', fill='y', padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text='Open-ended Questions', font=_FB).pack(anchor='w')
        tk.Label(left,
                 text='Draw a box on the image, then\ntype the answer in the right panel.',
                 font=('Arial', 9), fg='gray50', justify='left').pack(anchor='w', pady=(0, 4))
        q_list_frame = tk.Frame(left)
        q_list_frame.pack(fill='both', expand=True)
        q_scrollbar = tk.Scrollbar(q_list_frame, orient='vertical')
        self._q_listbox = tk.Listbox(q_list_frame, height=4, font=_F,
                                     exportselection=False,
                                     yscrollcommand=q_scrollbar.set)
        q_scrollbar.config(command=self._q_listbox.yview)
        q_scrollbar.pack(side='right', fill='y')
        self._q_listbox.pack(side='left', fill='both', expand=True)
        self._q_listbox.bind('<<ListboxSelect>>', self._on_q_select)

        tk.Frame(left, height=1, bg='gray70').pack(fill='x', pady=(4, 2))
        tk.Label(left, text='Bubble (MC) Answers', font=_FB).pack(anchor='w')
        mc_list_frame = tk.Frame(left)
        mc_list_frame.pack(fill='both', expand=True)
        mc_scrollbar = tk.Scrollbar(mc_list_frame, orient='vertical')
        self._mc_listbox = tk.Listbox(mc_list_frame, height=4, font=_F,
                                      exportselection=False,
                                      yscrollcommand=mc_scrollbar.set)
        mc_scrollbar.config(command=self._mc_listbox.yview)
        mc_scrollbar.pack(side='right', fill='y')
        self._mc_listbox.pack(side='left', fill='both', expand=True)

        mc_btn_row = tk.Frame(left)
        mc_btn_row.pack(fill='x', pady=(4, 0))
        tk.Button(mc_btn_row, text='+Add MC answer', font=_F,
                  command=self._add_mc_answer).pack(side='left', padx=(0, 4))
        tk.Button(mc_btn_row, text='Remove', font=_F,
                  command=self._remove_mc_answer).pack(side='left')

        # ── Right column: scrollable answer editor ────────────────────────
        right_outer = tk.Frame(data_pane)
        right_outer.pack(side='left', fill='both', expand=True)

        right_scroll = tk.Scrollbar(right_outer, orient='vertical')
        right_scroll.pack(side='right', fill='y')
        right_canvas = tk.Canvas(right_outer, yscrollcommand=right_scroll.set,
                                 highlightthickness=0)
        right_canvas.pack(side='left', fill='both', expand=True)
        right_scroll.config(command=right_canvas.yview)

        self._right = tk.Frame(right_canvas)
        self._right_window_id = right_canvas.create_window((0, 0), window=self._right, anchor='nw')

        def _on_right_configure(event):
            right_canvas.configure(scrollregion=right_canvas.bbox('all'))
            right_canvas.itemconfig(self._right_window_id, width=right_canvas.winfo_width())

        self._right.bind('<Configure>', _on_right_configure)
        right_canvas.bind('<Configure>', lambda e: right_canvas.itemconfig(
            self._right_window_id, width=e.width))

        tk.Label(self._right, text='Select a question to edit its answers.',
                 font=_F, fg='gray50').pack(anchor='w', pady=8)

        # Size window to fit screen without going off the bottom
        win.update_idletasks()
        screen_h = win.winfo_screenheight()
        win.geometry(f'960x{min(780, screen_h - 80)}')

        win.protocol('WM_DELETE_WINDOW', win.destroy)

        # Populate lists
        self._refresh_q_list()
        self._refresh_mc_list()

        self._parent.wait_window(win)

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    def _add_page(self):
        from tkinter import filedialog as _fd
        imgpath = _fd.askopenfilename(
            title='Choose a template scan image for this page',
            filetypes=[('JPEG', '*.jpg'), ('JPEG', '*.jpeg'), ('PDF', '*.pdf')],
            parent=self._win)
        if not imgpath:
            return

        is_pdf = Path(imgpath).suffix.lower() == '.pdf'
        try:
            n_pdf_pages = _pdf_page_count(imgpath) if is_pdf else 1
        except Exception as exc:
            tkinter.messagebox.showerror('Load image',
                                         f'Could not read PDF:\n{exc}',
                                         parent=self._win)
            return

        first_new_idx = len(self._pages)  # index of first page we're about to add

        for pdf_page_idx in range(n_pdf_pages):
            try:
                if is_pdf:
                    aligned_arr = _load_aligned_arr_page(imgpath, pdf_page_idx)
                else:
                    aligned_arr = _load_aligned_arr(imgpath)
            except Exception as exc:
                tkinter.messagebox.showerror(
                    'Load image',
                    f'Could not load/align '
                    f'{"page " + str(pdf_page_idx + 1) + " of " if is_pdf else ""}{imgpath}:\n{exc}',
                    parent=self._win)
                # Continue loading the remaining pages rather than aborting entirely
                continue

            pil_full = PILImage.fromarray(aligned_arr)
            dispres = 0.5
            W, H = pil_full.size
            disp_w = max(1, int(W * dispres))
            disp_h = max(1, int(H * dispres))
            pil_disp = pil_full.resize((disp_w, disp_h), PILImage.LANCZOS)

            self._pages.append({
                'img_path': imgpath,
                'aligned_arr': aligned_arr,
                'pil_full': pil_full,
                'pil_disp': pil_disp,
                'dispres': dispres,
            })

        if len(self._pages) == first_new_idx:
            return  # nothing was added (all pages failed)

        self._current_page_idx = first_new_idx
        self._show_page()

        # Auto-scan bubbles only on the very first page of the whole key (index 0)
        if self._mode == 'filled' and self._num_mc_questions > 0 and first_new_idx == 0:
            self._auto_scan_bubbles(0)

    def _remove_page(self):
        if not self._pages:
            return
        if not tkinter.messagebox.askyesno(
                'Remove page',
                f'Remove page {self._current_page_idx + 1}?',
                parent=self._win):
            return
        page_num = self._current_page_idx + 1
        # Remove questions on this page
        to_delete = [qk for qk, qd in self._questions.items() if qd.get('page') == page_num]
        for qk in to_delete:
            del self._questions[qk]
        # Shift page numbers of questions on later pages
        for qk, qd in self._questions.items():
            if qd.get('page', 1) > page_num:
                qd['page'] -= 1
        del self._pages[self._current_page_idx]
        self._current_page_idx = min(self._current_page_idx, max(0, len(self._pages) - 1))
        self._refresh_q_list()
        self._show_page()

    def _prev_page(self):
        if self._current_page_idx > 0:
            self._commit_answer_edit()
            self._current_page_idx -= 1
            self._show_page()

    def _next_page(self):
        if self._current_page_idx < len(self._pages) - 1:
            self._commit_answer_edit()
            self._current_page_idx += 1
            self._show_page()

    def _show_page(self):
        if not self._pages:
            self._page_nav_var.set('No pages loaded')
            self._canvas.delete('all')
            self._canvas.configure(scrollregion=(0, 0, self._canvas_w, self._canvas_h))
            return
        page_data = self._pages[self._current_page_idx]
        pil_disp = page_data['pil_disp']
        self._page_nav_var.set(
            f'Page {self._current_page_idx + 1} of {len(self._pages)}')
        # Update scrollregion to full image size; canvas widget itself stays fixed
        self._canvas.configure(scrollregion=(0, 0, pil_disp.width, pil_disp.height))
        self._redraw_canvas()

    def _redraw_canvas(self, current_rect=None):
        if not self._pages:
            return
        page_data = self._pages[self._current_page_idx]
        pil_disp = page_data['pil_disp']
        dispres = page_data['dispres']
        page_num = self._current_page_idx + 1

        img = pil_disp.copy()
        draw = PILImageDraw.Draw(img)
        for qk, qd in self._questions.items():
            if qd.get('page') == page_num and qd.get('coords'):
                c = qd['coords']
                x1, y1, x2, y2 = (int(v * dispres) for v in c)
                draw.rectangle([x1, y1, x2, y2], outline=(60, 100, 220), width=2)
                draw.text((x1 + 4, y1 + 2), qk, fill=(60, 100, 220))
        if current_rect:
            rx1, ry1, rx2, ry2 = current_rect
            draw.rectangle(
                [min(rx1, rx2), min(ry1, ry2), max(rx1, rx2), max(ry1, ry2)],
                outline=(220, 100, 60), width=2)

        self._draw_state['tk_img'] = _pil_to_tkphoto(img, master=self._win)
        self._canvas.delete('all')
        self._canvas.create_image(0, 0, anchor='nw', image=self._draw_state['tk_img'])

    # ------------------------------------------------------------------
    # Drawing events — convert widget coords to canvas (scroll) coords
    # ------------------------------------------------------------------

    def _canvas_coords(self, event):
        """Convert event widget coords to canvas coords accounting for scroll offset."""
        return (self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))

    def _on_canvas_press(self, event):
        if not self._pages:
            return
        self._draw_state['drawing'] = True
        cx, cy = self._canvas_coords(event)
        self._draw_state['sx'] = cx
        self._draw_state['sy'] = cy

    def _on_canvas_drag(self, event):
        if self._draw_state['drawing'] and self._pages:
            cx, cy = self._canvas_coords(event)
            self._redraw_canvas([self._draw_state['sx'], self._draw_state['sy'], cx, cy])

    def _on_canvas_release(self, event):
        if not self._draw_state['drawing']:
            return
        self._draw_state['drawing'] = False
        if not self._pages:
            return
        sx, sy = self._draw_state['sx'], self._draw_state['sy']
        ex, ey = self._canvas_coords(event)
        if abs(ex - sx) < 5 or abs(ey - sy) < 5:
            return  # ignore tiny accidental clicks

        page_data = self._pages[self._current_page_idx]
        dispres = page_data['dispres']
        page_num = self._current_page_idx + 1

        # Determine default question number using ignores list
        existing_ns = []
        for k in self._questions:
            try:
                existing_ns.append(int(k.split('_')[-1]))
            except ValueError:
                pass
        box_index = len(self._questions)
        if self._ignores and box_index < len(self._ignores):
            default_n = int(self._ignores[box_index])
        else:
            # Also consider the highest bubble question number so that open-ended
            # questions drawn after all skip slots continue from beyond the last bubble.
            bubble_ns = []
            for bk in self._bubble:
                try:
                    bubble_ns.append(int(bk[1:]))  # 'Q010' → 10
                except (ValueError, IndexError):
                    pass
            default_n = max(existing_ns + bubble_ns, default=0) + 1

        # Prompt user to confirm/override the question number
        from tkinter import simpledialog as _sd
        self._win.lift()
        chosen = _sd.askinteger(
            'Open-Ended Question Number',
            f'Enter the question number for this answer box\n(default: {default_n}):',
            initialvalue=default_n,
            parent=self._win,
        )
        if chosen is None:
            return  # user cancelled — discard the drawn box
        qk = f'openQ_{chosen}'
        # avoid duplicate keys by incrementing
        while qk in self._questions:
            chosen += 1
            qk = f'openQ_{chosen}'

        x1 = int(min(sx, ex) / dispres)
        y1 = int(min(sy, ey) / dispres)
        x2 = int(max(sx, ex) / dispres)
        y2 = int(max(sy, ey) / dispres)

        self._questions[qk] = {
            'page': page_num,
            'coords': [x1, y1, x2, y2],
            'full': [],
            'partial': [],
        }
        self._redraw_canvas()
        self._refresh_q_list(select_key=qk)
        # Immediately open the answer editor so the user can type the answer
        self._on_q_select()

    # ------------------------------------------------------------------
    # Filled-sheet helpers
    # ------------------------------------------------------------------

    def _auto_scan_bubbles(self, page_idx: int):
        """Scan MC bubble answers from the aligned image at page_idx.

        Uses the same pipeline as the main Scanner so coordinates and
        thresholds are identical.  Results are merged into self._bubble.
        """
        from settings import Settings as _Settings
        import scan_functions as _sf
        import init_functions as _if

        page_data = self._pages[page_idx]
        aligned_arr = page_data['aligned_arr']

        settings = _Settings()
        settings.sigma = 0.25  # default fill threshold

        try:
            scanimg = _sf.autothresh(aligned_arr.copy(), settings)
            qAreas, idAreas, nAreas = _if.makeAreaDict(self._num_mc_questions)
            Ndict, Idict, Qdict = _if.makeResDict()
            qRes = _sf.rundots(scanimg, qAreas, idAreas, nAreas,
                               self._ignores, Qdict, Idict, Ndict)
        except Exception as exc:
            tkinter.messagebox.showerror(
                'Auto-scan bubbles',
                f'Could not scan bubble answers:\n{exc}',
                parent=self._win)
            return

        count = 0
        for qk, ans in qRes.items():
            if (qk.startswith('Q') and qk[1:].isdigit()
                    and ans not in ('', None, '-')):
                self._bubble[qk] = ans
                count += 1
        # Mark ignored questions as 'ignore' in the bubble dict
        if self._ignores:
            for q_num in self._ignores:
                iqk = 'Q' + format(int(q_num), '03d')  # cast: ast.literal_eval may produce floats
                self._bubble[iqk] = 'ignore'

        self._refresh_mc_list()
        self._status_var.set(
            f'Auto-scanned {self._num_mc_questions} MC question(s): '
            f'{count} answer(s) found. Review the MC list below.')

    def _scan_handwriting_ocr(self):
        """OCR the drawn open-ended boxes on the current page.

        Uses Claude AI (batch) when use_ai is True and api_key is set,
        otherwise falls back to local TrOCR via attempt_ocr().
        Results pre-fill the 'full' answer list for each question.
        """
        if not self._pages:
            return
        # Commit any in-progress edits before querying/overwriting the data model
        self._commit_answer_edit()
        page_num = self._current_page_idx + 1
        page_data = self._pages[self._current_page_idx]
        arr = np.array(page_data['pil_full'].convert('RGB'))

        qs_on_page = {
            qk: qd
            for qk, qd in self._questions.items()
            if qd.get('page') == page_num and qd.get('coords')
        }
        if not qs_on_page:
            tkinter.messagebox.showinfo(
                'Scan Handwriting',
                'No question boxes are drawn on this page yet.\n'
                'Draw boxes around the handwritten answer areas first.',
                parent=self._win)
            return

        if self._use_ai and not self._api_key:
            self._status_var.set(
                'AI OCR requested but no API key configured \u2014 '
                'falling back to local OCR. Use "Configure API Key\u2026" on the Build Key tab.')
            self._win.update()

        self._status_var.set('Running OCR \u2014 please wait\u2026')
        self._win.update()

        try:
            if self._use_ai and self._api_key:
                crops = []
                ids = []
                for qk, qd in qs_on_page.items():
                    c = qd['coords']
                    crops.append(arr[c[1]:c[3], c[0]:c[2]])
                    ids.append(qk)
                results = _ai_ocr_mod.recognize_batch(
                    crops, ids,
                    context=self._ai_context,
                    api_key=self._api_key)
                for qk, text in results.items():
                    if text and qk in self._questions:
                        self._questions[qk]['full'] = [text]
            else:
                from ocr import attempt_ocr as _attempt_ocr
                for qk, qd in qs_on_page.items():
                    c = qd['coords']
                    crop = arr[c[1]:c[3], c[0]:c[2]]
                    text, _conf = _attempt_ocr(crop)
                    if text:
                        self._questions[qk]['full'] = [text]
        except Exception as exc:
            tkinter.messagebox.showerror(
                'Scan Handwriting',
                f'OCR failed:\n{exc}',
                parent=self._win)
            self._status_var.set('OCR error — see message above.')
            return

        self._refresh_q_list()
        if self._current_q_key in qs_on_page:
            self._build_answer_editor(self._current_q_key)
        n = len(qs_on_page)
        self._status_var.set(
            f'OCR complete \u2014 {n} question(s) processed. '
            'Review and edit answers as needed.')

    def _undo_last_box(self):
        page_num = self._current_page_idx + 1
        # Find the highest-numbered question on this page
        candidates = [qk for qk, qd in self._questions.items()
                      if qd.get('page') == page_num]
        if not candidates:
            return
        last_key = sorted(candidates, key=_openq_sort_key)[-1]
        del self._questions[last_key]
        if self._current_q_key == last_key:
            self._current_q_key = None
            for w in self._right.winfo_children():
                w.destroy()
            tk.Label(self._right, text='Select a question to edit its answers.',
                     font=('Arial', 11), fg='gray50').pack(anchor='w', pady=8)
        self._redraw_canvas()
        self._refresh_q_list()

    # ------------------------------------------------------------------
    # Question list
    # ------------------------------------------------------------------

    def _q_display_text(self, qk: str) -> str:
        qd = self._questions.get(qk, {})
        n_full = len(qd.get('full', []))
        n_part = len(qd.get('partial', []))
        has_coords = '✓' if qd.get('coords') else '–'
        page = qd.get('page', 1)
        return f'{qk}  p{page}  ({n_full}F/{n_part}P  box:{has_coords})'

    def _refresh_q_list(self, select_key: str | None = None):
        yview_top = self._q_listbox.yview()[0]  # save scroll fraction before rebuild
        self._q_listbox.delete(0, tk.END)
        all_keys = sorted(self._questions.keys(), key=_openq_sort_key)
        for qk in all_keys:
            self._q_listbox.insert(tk.END, self._q_display_text(qk))
        if select_key and select_key in all_keys:
            idx = all_keys.index(select_key)
            self._q_listbox.selection_clear(0, tk.END)
            self._q_listbox.selection_set(idx)
            self._q_listbox.see(idx)
        else:
            # No explicit navigation — restore previous scroll position
            self._q_listbox.yview_moveto(yview_top)

    def _on_q_select(self, event=None):
        # Capture the clicked index BEFORE _commit_answer_edit rebuilds the list
        # (rebuilding resets curselection to the previously committed key).
        sel = self._q_listbox.curselection()
        self._commit_answer_edit()
        if not sel:
            return
        all_keys = sorted(self._questions.keys(), key=_openq_sort_key)
        idx = sel[0]
        if idx >= len(all_keys):
            return
        qk = all_keys[idx]
        self._current_q_key = qk
        self._build_answer_editor(qk)
        # Re-apply selection to clicked row (commit may have moved highlight)
        self._q_listbox.selection_clear(0, tk.END)
        self._q_listbox.selection_set(idx)

    # ------------------------------------------------------------------
    # Answer editor
    # ------------------------------------------------------------------

    def _build_answer_editor(self, qk: str):
        for w in self._right.winfo_children():
            w.destroy()
        _F  = ('Arial', 11)
        _FB = ('Arial', 11, 'bold')
        f = self._right
        qd = self._questions[qk]
        page = qd.get('page', 1)

        tk.Label(f, text=f'{qk}  —  page {page}', font=_FB).pack(anchor='w', pady=(4, 6))

        # ── Full-credit answers ────────────────────────────────────────────
        tk.Label(f, text='Full-credit answers (first = primary):', font=_F).pack(anchor='w')
        fl_frame = tk.Frame(f)
        fl_frame.pack(fill='x', padx=4, pady=(2, 0))
        fl_scroll = tk.Scrollbar(fl_frame, orient='vertical')
        self._fl_listbox = tk.Listbox(fl_frame, height=4, font=_F,
                                      exportselection=False, yscrollcommand=fl_scroll.set)
        fl_scroll.config(command=self._fl_listbox.yview)
        fl_scroll.pack(side='right', fill='y')
        self._fl_listbox.pack(side='left', fill='x', expand=True)
        for ans in qd.get('full', []):
            self._fl_listbox.insert(tk.END, ans)
        _fl_edit_idx = [None]  # mutable container: index being edited, or None

        fl_inp = tk.Frame(f)
        fl_inp.pack(fill='x', padx=4, pady=(2, 4))
        self._fl_new_var = tk.StringVar()
        fl_entry = tk.Entry(fl_inp, textvariable=self._fl_new_var, width=30, font=_F)
        fl_entry.pack(side='left', padx=(0, 6))

        def _add_full():
            new = self._fl_new_var.get().strip()
            if not new:
                return
            if _fl_edit_idx[0] is not None:
                others = [self._fl_listbox.get(i) for i in range(self._fl_listbox.size())
                          if i != _fl_edit_idx[0]]
                if new.lower() not in [e.lower() for e in others]:
                    self._fl_listbox.delete(_fl_edit_idx[0])
                    self._fl_listbox.insert(_fl_edit_idx[0], new)
                _fl_edit_idx[0] = None
                self._fl_new_var.set('')
                return
            existing = [self._fl_listbox.get(i) for i in range(self._fl_listbox.size())]
            if new.lower() not in [e.lower() for e in existing]:
                self._fl_listbox.insert(tk.END, new)
            self._fl_new_var.set('')

        def _remove_full():
            sel = self._fl_listbox.curselection()
            if sel:
                self._fl_listbox.delete(sel[0])
                _fl_edit_idx[0] = None
                self._fl_new_var.set('')

        def _on_fl_double(event):
            s = self._fl_listbox.curselection()
            if s:
                _fl_edit_idx[0] = s[0]
                self._fl_new_var.set(self._fl_listbox.get(s[0]))
                fl_entry.focus_set()
                fl_entry.select_range(0, tk.END)

        fl_entry.bind('<Return>', lambda e: _add_full())
        self._fl_listbox.bind('<Double-Button-1>', _on_fl_double)
        tk.Button(fl_inp, text='Add', command=_add_full, font=_F, bg='#bbf7d0').pack(side='left', padx=(0, 4))
        tk.Button(fl_inp, text='Remove selected', command=_remove_full, font=_F).pack(side='left')
        tk.Label(f, text='(Double-click an answer to edit it in place)',
                 font=('Arial', 9), fg='gray50').pack(anchor='w', padx=4)

        # ── Partial-credit answers ─────────────────────────────────────────
        tk.Label(f, text='Partial-credit answers (auto-graded CX):', font=_F).pack(
            anchor='w', pady=(8, 0))
        pl_frame = tk.Frame(f)
        pl_frame.pack(fill='x', padx=4, pady=(2, 0))
        pl_scroll = tk.Scrollbar(pl_frame, orient='vertical')
        self._pl_listbox = tk.Listbox(pl_frame, height=3, font=_F,
                                      exportselection=False, yscrollcommand=pl_scroll.set)
        pl_scroll.config(command=self._pl_listbox.yview)
        pl_scroll.pack(side='right', fill='y')
        self._pl_listbox.pack(side='left', fill='x', expand=True)
        for ans in qd.get('partial', []):
            self._pl_listbox.insert(tk.END, ans)

        pl_inp = tk.Frame(f)
        pl_inp.pack(fill='x', padx=4, pady=(2, 4))
        self._pl_new_var = tk.StringVar()
        pl_entry = tk.Entry(pl_inp, textvariable=self._pl_new_var, width=30, font=_F)
        pl_entry.pack(side='left', padx=(0, 6))

        def _add_partial():
            new = self._pl_new_var.get().strip()
            if not new:
                return
            existing = [self._pl_listbox.get(i) for i in range(self._pl_listbox.size())]
            if new.lower() not in [e.lower() for e in existing]:
                self._pl_listbox.insert(tk.END, new)
            self._pl_new_var.set('')

        def _remove_partial():
            sel = self._pl_listbox.curselection()
            if sel:
                self._pl_listbox.delete(sel[0])

        pl_entry.bind('<Return>', lambda e: _add_partial())
        tk.Button(pl_inp, text='Add', command=_add_partial, font=_F, bg='#fef08a').pack(side='left', padx=(0, 4))
        tk.Button(pl_inp, text='Remove selected', command=_remove_partial, font=_F).pack(side='left')

    def _commit_answer_edit(self):
        """Flush listbox contents back into self._questions for the current question."""
        qk = self._current_q_key
        if qk is None or qk not in self._questions:
            return
        if hasattr(self, '_fl_listbox'):
            self._questions[qk]['full'] = [
                self._fl_listbox.get(i) for i in range(self._fl_listbox.size())]
        if hasattr(self, '_pl_listbox'):
            self._questions[qk]['partial'] = [
                self._pl_listbox.get(i) for i in range(self._pl_listbox.size())]
        # Refresh display text (counts only) without scrolling or moving selection.
        # The caller (_on_q_select or similar) is responsible for updating selection.
        self._refresh_q_list()

    # ------------------------------------------------------------------
    # MC answer management
    # ------------------------------------------------------------------

    def _refresh_mc_list(self):
        self._mc_listbox.delete(0, tk.END)
        for qk in sorted(self._bubble.keys()):
            self._mc_listbox.insert(tk.END, f'{qk}  →  {self._bubble[qk]}')

    def _add_mc_answer(self):
        dlg = tk.Toplevel(self._win)
        dlg.title('Add Bubble Question')
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text='Question number (1–150):', font=('Arial', 11)).grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky='w')
        num_var = tk.StringVar()
        num_entry = tk.Entry(dlg, textvariable=num_var, width=8, font=('Arial', 11))
        num_entry.grid(row=0, column=1, padx=10, pady=(10, 4), sticky='w')
        tk.Label(dlg, text='Answer (e.g. A or BCE or ignore):',
                 font=('Arial', 11)).grid(row=1, column=0, padx=10, pady=4, sticky='w')
        ans_var = tk.StringVar()
        ans_entry = tk.Entry(dlg, textvariable=ans_var, width=12, font=('Arial', 11))
        ans_entry.grid(row=1, column=1, padx=10, pady=4, sticky='w')
        status_lbl = tk.Label(dlg, text='', font=('Arial', 10), fg='red')
        status_lbl.grid(row=2, column=0, columnspan=2, padx=10)

        def _do_add():
            raw = num_var.get().strip()
            _raw_ans = ans_var.get().strip()
            ans = _raw_ans.lower() if _raw_ans.lower() == 'ignore' else _raw_ans.upper()
            if not raw:
                status_lbl.config(text='Enter a question number.')
                return
            try:
                n = int(raw)
                if not (1 <= n <= 150):
                    raise ValueError
            except ValueError:
                status_lbl.config(text='Number must be 1–150.')
                return
            qk = 'Q' + format(n, '03d')
            self._bubble[qk] = ans if ans else '-'
            self._refresh_mc_list()
            dlg.destroy()

        btn_row = tk.Frame(dlg)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(4, 10), padx=10, sticky='e')
        tk.Button(btn_row, text='Add', command=_do_add,
                  font=('Arial', 11), bg='#bbf7d0').pack(side='left', padx=(0, 6))
        tk.Button(btn_row, text='Cancel', command=dlg.destroy,
                  font=('Arial', 11)).pack(side='left')
        num_entry.focus_force()
        ans_entry.bind('<Return>', lambda e: _do_add())
        dlg.bind('<Escape>', lambda e: dlg.destroy())
        self._win.wait_window(dlg)
        self._win.grab_set()

    def _remove_mc_answer(self):
        sel = self._mc_listbox.curselection()
        if not sel:
            return
        all_mc = sorted(self._bubble.keys())
        idx = sel[0]
        if idx < len(all_mc):
            del self._bubble[all_mc[idx]]
            self._refresh_mc_list()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_csv(self):
        self._commit_answer_edit()
        from tkinter import filedialog as _fd
        path = _fd.asksaveasfilename(
            title='Save key as CSV…',
            defaultextension='.csv',
            filetypes=[('CSV key file', '*.csv')],
            parent=self._win)
        if not path:
            return
        try:
            _skip_ns = []
            for qk in self._questions:
                try:
                    _skip_ns.append(int(qk.split('_')[-1]))
                except ValueError:
                    pass
            _skip_str = ','.join(str(n) for n in sorted(_skip_ns))
            _total = self._num_mc_questions
            save_key_file(path, {
                'bubble_answers': dict(self._bubble),
                'open_questions': {
                    qk: {
                        'full': list(qd.get('full', [])),
                        'partial': list(qd.get('partial', [])),
                        'coords': qd.get('coords'),
                        'page': qd.get('page', 1),
                    }
                    for qk, qd in self._questions.items()
                },
                'metadata': {
                    'num_questions': _total,
                    'questions_to_skip': _skip_str,
                },
            })
            self.saved_path = path
            self._status_var.set(f'Saved: {Path(path).name}')
        except Exception as exc:
            tkinter.messagebox.showerror('Save error', str(exc), parent=self._win)
