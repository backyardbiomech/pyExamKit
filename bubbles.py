'''
Adaptive bubble reading.

Each bubble gets a fill score: how much darker its interior is than an
empty bubble of the same letter on the same sheet. A bubble counts as filled
relative to the student's own pencil: its score must reach a fraction of
that student's typical fill, clear an absolute floor, and be at least half
as dark as the darkest bubble in its row. The first rule lets a light
shader's marks count; the row rule is what drops an erasure left beside a
fresh mark. Bubbles close to the line are reported rather than silently
decided. The reasoning and the measurements behind the defaults are in
docs/dev/answer-sheet-redesign.md.
'''
from dataclasses import dataclass, field

import numpy as np

import sheet_layout

# Set from 69 real pencil sheets (docs/dev/answer-sheet-redesign.md). The
# cutoff is exposed in the GUI; any value from 0.30 to 0.45 read that stack
# identically, and 0.35 centers the line on its lightest sheet.
CUTOFF = 0.35         # fraction of the student's fill level
FLOOR = 0.06          # minimum fill score to count at all
ROW_RATIO = 0.5       # fraction of the darkest bubble in the same row
BAND = 0.15           # a lone mark this far (x fill level) under the cutoff is flagged
ROW_BAND = 0.1        # a mark this close to ROW_RATIO of its row's darkest is flagged
LIGHT_SHEET = 0.25    # sheets whose fill level is under this are reported
FALLBACK_FILL = 0.45  # fill level assumed when a sheet has too few marks
MEASURE_RADIUS = 7    # px; inside the printed ring even when 2 px misaligned

_GRAY = np.array([0.2125, 0.7154, 0.0721])


def to_gray(img) -> np.ndarray:
    '''RGB or grayscale uint8 array -> float grayscale 0-255.'''
    img = np.asarray(img)
    if img.ndim == 3:
        return img.astype(np.float64) @ _GRAY
    return img.astype(np.float64)


def _disk(r):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


_DISK = _disk(MEASURE_RADIUS)


def darkness(gray: np.ndarray, rows: dict, paper: float) -> dict[str, np.ndarray]:
    '''Raw darkness (0 = paper, 1 = black) of every bubble in `rows`.'''
    r = MEASURE_RADIUS
    h, w = gray.shape
    out = {}
    for key, row in rows.items():
        vals = np.empty(len(row))
        for j, (_, cx, cy) in enumerate(row):
            x, y = int(round(cx)), int(round(cy))
            if r <= x < w - r and r <= y < h - r:
                patch = gray[y - r:y + r + 1, x - r:x + r + 1]
                vals[j] = patch[_DISK].mean()
            else:
                vals[j] = paper
        out[key] = np.clip(1 - vals / paper, 0, 1)
    return out


def fill_scores(dark: dict[str, np.ndarray], exclude=()) -> dict[str, np.ndarray]:
    '''
    Subtract the printed ink of an empty bubble. Each label (letter or digit)
    gets its own baseline, the 25th percentile of that label down the grid,
    since nearly every bubble in a column is empty. Too few rows for that
    and the whole grid shares one baseline.
    '''
    base_keys = [k for k in dark if k not in exclude] or list(dark)
    stack = np.vstack([dark[k] for k in base_keys])
    if stack.shape[0] >= 4:
        baseline = np.percentile(stack, 25, axis=0)
    else:
        baseline = np.full(stack.shape[1], np.percentile(stack, 25))
    return {k: np.clip(v - baseline, 0, None) for k, v in dark.items()}


def fill_level(scores: dict[str, np.ndarray], floor=FLOOR) -> float:
    '''The student's typical mark: median of each answered row's darkest bubble.'''
    maxes = [v.max() for v in scores.values() if v.max() >= floor]
    if len(maxes) < 3:
        return FALLBACK_FILL
    return float(np.median(maxes))


@dataclass
class Flag:
    field: str      # Q012, ID03, V ...
    label: str      # the bubble's letter or digit
    reason: str
    score: float


@dataclass
class SheetRead:
    answers: dict                      # same keys and values as the old rundots
    layout: sheet_layout.Layout
    fill_level: float
    cut: float
    flags: list[Flag] = field(default_factory=list)
    version: str = '-'


def decide_multi(key, labels, scores, cut, F, band=BAND, row_ratio=ROW_RATIO):
    '''
    A question row, where more than one bubble may legitimately be filled.
    Returns (answer string, flags).

    Only calls that could go either way are flagged. On real sheets a lone
    mark just over the cutoff was always an answer, and an erasure beside a
    fresh mark was always well under half its darkness, so neither is
    flagged; what is flagged is a mark near half the darkness of its row's
    darkest, and a lone light mark just under the cutoff.
    '''
    top = scores.max()
    kept = [s >= cut and s >= row_ratio * top for s in scores]
    marked, flags = [lab for lab, k in zip(labels, kept) if k], []
    for lab, s, k in zip(labels, scores, kept):
        close_to_row = top > 0 and abs(s / top - row_ratio) < ROW_BAND
        if s >= cut and not k and close_to_row:
            flags.append(Flag(key, lab, 'lighter than another mark in the row; read as erased', s))
        elif k and len(marked) > 1 and close_to_row:
            flags.append(Flag(key, lab, 'much lighter than another mark in the row; '
                              'read as filled', s))
    if not marked and top >= FLOOR and top >= cut - band * F:
        lab = labels[int(np.argmax(scores))]
        flags.append(Flag(key, lab, 'a light mark just under the cutoff; read as blank', top))
    return (''.join(marked) or '-'), flags


def decide_one(key, labels, scores, cut, F, band=BAND, row_ratio=ROW_RATIO):
    '''A row where exactly one bubble belongs (an ID digit, a name letter).'''
    order = np.argsort(scores)[::-1]
    best, second = scores[order[0]], scores[order[1]]
    flags = []
    if best < cut:
        if best >= FLOOR and cut - best < band * F:
            flags.append(Flag(key, labels[order[0]], 'close to the cutoff; read as empty', best))
        return '-', flags
    if second >= cut and second >= row_ratio * best:
        flags.append(Flag(key, labels[order[1]],
                          f'second bubble filled; read as {labels[order[0]]}', second))
    return labels[order[0]], flags


def read_sheet(aligned, quests: int, ignores=None, cutoff: float = CUTOFF,
               layout: sheet_layout.Layout | None = None) -> SheetRead:
    '''
    Read an aligned page. Returns answers in the dictionary shape the rest of
    the pipeline already uses: Q001.. -> 'A', 'AC', '-' or 'ignore';
    LastName, FirstName, studentID.
    '''
    gray = to_gray(aligned)
    if layout is None:
        layout = sheet_layout.detect_layout(gray)
    ignores = set(int(i) for i in (ignores or []))
    # The paper level: the page is mostly blank, so a high percentile is paper.
    paper = max(float(np.percentile(gray, 95)), 1.0)

    q_rows = layout.question_rows(quests)
    ignored = {k for k in q_rows if int(k[1:]) in ignores}
    q_scores = fill_scores(darkness(gray, q_rows, paper), exclude=ignored)
    F = fill_level({k: v for k, v in q_scores.items() if k not in ignored})
    cut = max(FLOOR, cutoff * F)

    answers, flags = {}, []
    for k, row in q_rows.items():
        if k in ignored:
            answers[k] = 'ignore'
            continue
        ans, fl = decide_multi(k, [lab for lab, _, _ in row], q_scores[k], cut, F)
        answers[k] = ans
        flags += fl

    def read_one_per_row(rows):
        if not rows:
            return {}
        scores = fill_scores(darkness(gray, rows, paper))
        res = {}
        for k, row in rows.items():
            res[k], fl = decide_one(k, [lab for lab, _, _ in row], scores[k], cut, F)
            flags.extend(fl)
        return res

    ids = read_one_per_row(layout.id_digits)
    names = read_one_per_row(layout.name_rows)
    version = read_one_per_row(layout.version).get('V', '-')

    # A sheet without name bubbles reads like a blank name grid: '-'
    answers['LastName'] = ''.join(names.get(f'N{i}', '') for i in range(1, 6)) or '-'
    answers['FirstName'] = ''.join(names.get(f'F{i}', '') for i in range(1, 4)) or '-'
    answers['studentID'] = ''.join(ids[k] for k in sorted(ids))
    return SheetRead(answers, layout, F, cut, flags, version)
