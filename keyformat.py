"""
keyformat.py

Single source of truth for the exam key CSV format shared between the
scanner (this repo) and the exam builder (pyExamPaper). Nothing else in
either codebase should read or write a key CSV directly.

Canonical columns, always written in this order:
    type, question, page, x1, y1, x2, y2, answer, partial_answers, points

Two layouts exist on disk today. The nine-column layout (no ``points``)
was written by this scanner's own key-saving code before this module
existed. The ten-column layout, with ``points``, is written by
pyExamPaper's key_generator.py. Both are accepted on read — csv.DictReader
keys off the header row, so a missing ``points`` column simply yields no
point values. Only the ten-column layout is ever written, so a key that
round-trips through this module keeps whatever per-question points it
had.

Encoding: written as plain UTF-8, no byte-order mark, matching
key_generator.py. Read as utf-8-sig, which transparently strips a BOM
when one is present (files written by the old nine-column scanner code)
and behaves as plain UTF-8 when one is not.
"""
import csv
import json
from pathlib import Path

KEY_CSV_HEADER = ['type', 'question', 'page', 'x1', 'y1', 'x2', 'y2',
                   'answer', 'partial_answers', 'points']


def _openq_sort_key(k: str) -> tuple:
    """Sort key for openQ_N labels so openQ_2 sorts before openQ_10,
    and openQ_1A/openQ_1B sort between openQ_1 and openQ_2."""
    suffix = k.rsplit('_', 1)[-1] if '_' in k else k
    num_part = ''
    alpha_part = suffix
    for i, c in enumerate(suffix):
        if c.isdigit():
            num_part += c
        else:
            alpha_part = suffix[i:]
            break
    else:
        alpha_part = ''
    return (int(num_part) if num_part else 0, alpha_part.lower())


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
      type, question, page, x1, y1, x2, y2, answer, partial_answers, points
      type is 'bubble' or 'open'.
      answer       — the primary (full-credit) answer; pipe-separated for multiple
      partial_answers — pipe-separated partial-credit answers (optional)
      points       — per-question point value (optional; nine-column files omit it)

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
    point_values: dict = {}

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
                    pts_str = (row.get('points') or '').strip()
                    if pts_str:
                        try:
                            point_values[_norm_bubble_key(question)] = float(pts_str)
                        except ValueError:
                            pass

                elif row_type == 'open':
                    qk = _norm_open_key(question)
                    if qk not in open_questions:
                        open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                    # Coordinates (float-safe: CSV may store ints as "1.0")
                    try:
                        x1 = int(float(row.get('x1') or 0))
                        y1 = int(float(row.get('y1') or 0))
                        x2 = int(float(row.get('x2') or 0))
                        y2 = int(float(row.get('y2') or 0))
                        if any(c != 0 for c in (x1, y1, x2, y2)):
                            open_questions[qk]['coords'] = [x1, y1, x2, y2]
                    except (ValueError, TypeError, OverflowError):
                        pass
                    # Page (float-safe)
                    try:
                        pv = (row.get('page') or '').strip()
                        open_questions[qk]['page'] = max(1, int(float(pv))) if pv else 1
                    except (ValueError, TypeError, OverflowError):
                        pass
                    # Full-credit answers (pipe-separated)
                    for ans in _parse_pipe(row.get('answer') or ''):
                        if ans.lower() not in [a.lower() for a in open_questions[qk]['full']]:
                            open_questions[qk]['full'].append(ans)
                    # Partial-credit answers (pipe-separated)
                    for ans in _parse_pipe(row.get('partial_answers') or ''):
                        if ans.lower() not in [a.lower() for a in open_questions[qk]['partial']]:
                            open_questions[qk]['partial'].append(ans)
                    # Points
                    pts_str = (row.get('points') or '').strip()
                    if pts_str:
                        try:
                            point_values[_norm_open_key(question)] = float(pts_str)
                        except ValueError:
                            pass

                # ── Tall/legacy format ───────────────────────────────────
                elif row_type == 'open_coords':
                    qk = _norm_open_key(question)
                    if qk not in open_questions:
                        open_questions[qk] = {'full': [], 'partial': [], 'coords': None, 'page': 1}
                    try:
                        x1 = int(float(row.get('x1') or 0))
                        y1 = int(float(row.get('y1') or 0))
                        x2 = int(float(row.get('x2') or 0))
                        y2 = int(float(row.get('y2') or 0))
                        if any(c != 0 for c in (x1, y1, x2, y2)):
                            open_questions[qk]['coords'] = [x1, y1, x2, y2]
                    except (ValueError, TypeError, OverflowError):
                        pass
                    try:
                        pv = (row.get('page') or '').strip()
                        open_questions[qk]['page'] = max(1, int(float(pv))) if pv else 1
                    except (ValueError, TypeError, OverflowError):
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

    blank_keys = [qk for qk, ans in bubble_answers.items() if not ans]
    if blank_keys:
        print(f'[KeyFile] WARNING: {len(blank_keys)} bubble question(s) have a blank answer '
              f'in the key file — scan will likely produce incorrect results. '
              f'Fix these before scanning: {", ".join(sorted(blank_keys))}', flush=True)

    print(f'[KeyFile] Loaded CSV key: {len(bubble_answers)} bubble answer(s), '
          f'{len(open_questions)} open question(s).', flush=True)
    result = {'bubble_answers': bubble_answers, 'open_questions': open_questions}
    if metadata:
        result['metadata'] = metadata
    if point_values:
        result['point_values'] = point_values
    return result


def save_key_csv(path: str, data: dict) -> None:
    """
    Write a CSV exam key file in the canonical wide, ten-column format.
    Columns: type, question, page, x1, y1, x2, y2, answer, partial_answers, points
      metadata rows: type=metadata, question=field_name, answer=value
      bubble rows:   type=bubble, answer=letter(s), all coordinate columns blank
      open rows:     type=open, answer=pipe-separated full-credit answers,
                     partial_answers=pipe-separated partial-credit answers
      points         — data['point_values'][question], blank when not known

    Always writes plain UTF-8 with no byte-order mark.
    """
    bubble = data.get('bubble_answers', {})
    open_qs = data.get('open_questions', {})
    meta = data.get('metadata', {})
    points = data.get('point_values', {})

    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(KEY_CSV_HEADER)

        # Metadata rows (num_questions, questions_to_skip)
        if meta.get('num_questions'):
            writer.writerow(['metadata', 'num_questions', '', '', '', '', '',
                             meta['num_questions'], '', ''])
        if meta.get('questions_to_skip'):
            writer.writerow(['metadata', 'questions_to_skip', '', '', '', '', '',
                             meta['questions_to_skip'], '', ''])

        # Bubble answers (sorted by question key)
        for qk in sorted(bubble.keys()):
            writer.writerow(['bubble', qk, '', '', '', '', '', bubble[qk], '',
                             points.get(qk, '')])

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
            writer.writerow(['open', qk, page, x1, y1, x2, y2, full_ans, partial_ans,
                             points.get(qk, '')])


def save_key_file(path: str, data: dict) -> None:
    """Write an exam key file. Dispatches to CSV or JSON based on file extension."""
    if Path(path).suffix.lower() == '.csv':
        save_key_csv(path, data)
        return
    Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')
