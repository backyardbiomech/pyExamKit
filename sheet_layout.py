'''
Answer sheet geometry: where every bubble sits, defined once.

The scanner reads bubbles at these centers and answer_sheet.py draws the
printed sheet from them, so the two cannot drift apart. Coordinates are in
the scanner's canonical frame: a US Letter page at 144 dpi (1224 x 1584 px),
which is 2 px per PDF point.

Three layouts exist. 'classic' is the Illustrator sheet in images/ that
predates this module; its numbers are measured from that PDF and must not
change, since printed stock and archived scans depend on them. 'v2' is the
generated sheet, with a gap after every fifth row. 'v2-keyed' is the v2
sheet printed for one exam, whose gaps set off each ordering, matching, and
dropdown question; its rows are described by run sizes that the exam's key
carries (see keyed_layout). The lab practical form sheet (see practical_boxes)
has no answer bubbles: page 1 carries the ID, and every page carries writing
boxes and the form it was printed for. All share the three registration circles, so
one alignment step serves any of them, and the layout is identified after
alignment by a printed code (see LAYOUT_CODE_CELLS).
'''
from dataclasses import dataclass, field

# Canonical frame shared by every layout
PAGE_W, PAGE_H = 1224, 1584
PX_PER_PT = 2.0

# Registration circle centers (x, y) and diameter. Order matches what
# scan_functions.getRegPts returns: bottom-right, bottom-left, top-right.
REG_POINTS = [(1153, 1532), (73, 1532), (1153, 64)]
REG_DIAMETER = 42

BUBBLE_DIAMETER = 22
BUBBLE_PITCH = 26          # center-to-center along a row

# Layout code: four small squares on the bottom margin between the lower
# registration circles, blank on the classic sheet. Cell 0 is always inked
# on a generated sheet (so a stray mark on a classic sheet reads as nothing
# unless it happens to hit cell 0 too); cells 1-3 carry the layout id in
# binary, least significant bit first.
LAYOUT_CODE_SIZE = 16
LAYOUT_CODE_CELLS = [(160 + 28 * i, 1532) for i in range(4)]

LETTERS = 'ABCDEF'
DIGITS = '0123456789'
ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

Row = list[tuple[str, float, float]]   # [(label, cx, cy), ...]


@dataclass
class Layout:
    name: str
    code: int
    # Each dict maps a result key (Q001, ID01, F1, V) to its row of bubbles.
    questions: dict[str, Row]
    id_digits: dict[str, Row]
    name_rows: dict[str, Row] = field(default_factory=dict)
    version: dict[str, Row] = field(default_factory=dict)
    max_questions: int = 150
    # v2-keyed only: row runs, column by column (see keyed_layout)
    columns: list[list[int]] | None = None
    # Practical form sheets only: which page of the sheet this is
    practical_page: int = 0

    def question_rows(self, quests: int) -> dict[str, Row]:
        return {k: v for k, v in self.questions.items() if int(k[1:]) <= quests}

    def q_areas(self, quests: int) -> dict:
        '''
        Question row rectangles in the ((x0, y0), (x1, y1)) form markSheets
        expects. markSheets places marks at x0 + Qdict[letter] - 8, and
        Qdict puts letter i at 14 + 26i, so x0 sits 12 px left of bubble A.
        '''
        areas = {}
        for k, row in self.question_rows(quests).items():
            _, ax, ay = row[0]
            x0, y0 = int(round(ax - 12)), int(round(ay - 13))
            areas[k] = ((x0, y0), (x0 + 160, y0 + 26))
        return areas


def _row(labels: str, x0: float, y0: float, dx: float, dy: float) -> Row:
    return [(lab, x0 + i * dx, y0 + i * dy) for i, lab in enumerate(labels)]


def _classic() -> Layout:
    '''The Illustrator sheet: 5 blocks of 30 questions, names, 8-digit ID.'''
    questions = {}
    col_x = [138, 350, 562, 774, 990]          # bubble A centers
    for i in range(1, 151):
        col, within = divmod(i - 1, 30)
        y = 608 + 30 * within if within < 15 else 1058 + 30 * (within - 15)
        questions[f'Q{i:03d}'] = _row(LETTERS, col_x[col], y, BUBBLE_PITCH, 0)
    id_digits = {f'ID{c + 1:02d}': _row(DIGITS, 890 + 30 * c, 286, 0, BUBBLE_PITCH)
                 for c in range(8)}
    name_rows = {}
    for r in range(3):
        name_rows[f'F{r + 1}'] = _row(ALPHABET, 136, 276 + 28 * r, BUBBLE_PITCH, 0)
    for r in range(5):
        name_rows[f'N{r + 1}'] = _row(ALPHABET, 136, 408 + 28 * r, BUBBLE_PITCH, 0)
    return Layout('classic', 0, questions, id_digits, name_rows)


# ── v2: the generated sheet ────────────────────────────────────────────────
# Question grid: five columns of 30, a gap after every fifth row.
V2_Q_COL_X = [126, 346, 566, 786, 1006]     # bubble A centers
V2_Q_TOP = 580                              # row 1 center
V2_Q_ROW = 28                               # row pitch
V2_Q_GROUP_GAP = 14                         # extra space after every 5 rows
V2_ID_X = 890                               # first ID column center
V2_ID_TOP = 250                             # digit 0 center
V2_ID_COL = 30
V2_VERSION_Y = 420
V2_VERSION_X = 250                          # bubble A center


def v2_question_y(within: int) -> float:
    '''Center y of the row at 0-based position `within` a 30-row column.'''
    return V2_Q_TOP + V2_Q_ROW * within + V2_Q_GROUP_GAP * (within // 5)


def _v2_header() -> tuple[dict[str, Row], dict[str, Row]]:
    '''ID digits and version row, the same on every v2 sheet.'''
    id_digits = {f'ID{c + 1:02d}': _row(DIGITS, V2_ID_X + V2_ID_COL * c, V2_ID_TOP,
                                        0, BUBBLE_PITCH)
                 for c in range(8)}
    version = {'V': _row('ABCDEF', V2_VERSION_X, V2_VERSION_Y, BUBBLE_PITCH + 8, 0)}
    return id_digits, version


def _v2() -> Layout:
    questions = {}
    for i in range(1, 151):
        col, within = divmod(i - 1, 30)
        questions[f'Q{i:03d}'] = _row(LETTERS, V2_Q_COL_X[col], v2_question_y(within),
                                      BUBBLE_PITCH, 0)
    id_digits, version = _v2_header()
    return Layout('v2', 1, questions, id_digits, version=version)


# ── v2-keyed: gaps where the exam needs them ───────────────────────────────
# A column is a stack of runs, consecutive rows with a gap after each. The
# standard column is six runs of five. The page height allows any column
# whose last row sits no lower than the standard column's, and a gap is half
# a row, so a column fits when 2 x rows + runs <= 66.
COLUMN_BUDGET = 2 * 30 + 6


class RunsError(ValueError):
    '''Row runs that cannot be printed; the message is shown to the user.'''


def column_fits(runs: list[int]) -> bool:
    return 2 * sum(runs) + len(runs) <= COLUMN_BUDGET


def pack_runs(runs: list[int]) -> list[list[int]]:
    '''
    Fill columns with runs in order, starting a new column when the next run
    would not fit. A run is never split, so a question's rows stay together.
    '''
    columns: list[list[int]] = [[]]
    for n in runs:
        if not column_fits([n]):
            raise RunsError(f'A question with {n} answer rows is longer than a sheet column.')
        if not column_fits(columns[-1] + [n]):
            columns.append([])
        columns[-1].append(n)
    if len(columns) > len(V2_Q_COL_X):
        raise RunsError(f'These questions need {len(columns)} answer-sheet columns, and the '
                        f'sheet has {len(V2_Q_COL_X)}. Each ordering, matching, or dropdown '
                        f'question adds a gap, and gaps take room; drop some questions.')
    return columns


def standard_columns(rows: int) -> list[list[int]]:
    '''The run sizes of the standard v2 grid cut to `rows` rows.'''
    runs = [5] * (rows // 5) + ([rows % 5] if rows % 5 else [])
    return [runs[i:i + 6] for i in range(0, len(runs), 6)]


def format_columns(columns: list[list[int]]) -> str:
    '''The key's form: runs comma-separated, columns slash-separated.'''
    return '/'.join(','.join(str(n) for n in col) for col in columns)


def parse_columns(text: str) -> list[list[int]]:
    try:
        columns = [[int(n) for n in col.split(',')] for col in str(text).strip().split('/')]
    except ValueError:
        raise RunsError(f'Unreadable answer-sheet rows in the key: "{text}".') from None
    if (not columns or len(columns) > len(V2_Q_COL_X)
            or any(not col or min(col) < 1 or not column_fits(col) for col in columns)):
        raise RunsError(f'Impossible answer-sheet rows in the key: "{text}".')
    return columns


def keyed_layout(columns: list[list[int]]) -> Layout:
    '''The question grid for a sheet printed with these runs.'''
    questions = {}
    q = 1
    for col, runs in enumerate(columns):
        y = V2_Q_TOP
        for n in runs:
            for _ in range(n):
                questions[f'Q{q:03d}'] = _row(LETTERS, V2_Q_COL_X[col], y, BUBBLE_PITCH, 0)
                q += 1
                y += V2_Q_ROW
            y += V2_Q_GROUP_GAP
    id_digits, version = _v2_header()
    return Layout('v2-keyed', 2, questions, id_digits, version=version,
                  max_questions=q - 1, columns=[list(c) for c in columns])


def _v2_keyed_unknown() -> Layout:
    '''What detection returns for a code-2 sheet: the header, no grid yet.'''
    id_digits, version = _v2_header()
    return Layout('v2-keyed', 2, {}, id_digits, version=version, max_questions=0)


# ── Lab practical form sheets ──────────────────────────────────────────────
# Each station is a row of two writing boxes, left for the form's first
# letter and right for its second. Page 1 keeps the v2 name line and ID block;
# the stations start below the ID bubbles. Every page carries the form as
# four squares beside the layout code, one per letter A to D, inked when the
# form has that letter. The layout code says which page it is.
PRACTICAL_CODES = {1: 3, 2: 4, 3: 5}       # page -> layout code
FORM_CELLS = [(300 + 28 * i, 1532) for i in range(4)]
FORM_LETTERS = 'ABCD'
P_BOX_H = 72
P_PITCH = 86                                # box top to next box top
P_FIRST_TOP = {1: 540, 2: 150, 3: 150}      # first box top on each page
P_BOTTOM = 1490                             # no box runs below this
P_BOX_X = [(118, 600), (668, 1150)]         # left and right box, x0 to x1
P_CROP_INSET = 4                            # crops stay clear of the printed border


def practical_rows_per_page(page: int) -> int:
    return (P_BOTTOM - P_BOX_H - P_FIRST_TOP[page]) // P_PITCH + 1


def practical_pages(stations: int) -> int:
    '''Pages a form sheet with this many stations needs.'''
    total = 0
    for page in P_FIRST_TOP:
        total += practical_rows_per_page(page)
        if stations <= total:
            return page
    raise RunsError(f'A form sheet holds at most {total} stations; this practical has {stations}.')


def practical_boxes(stations: int) -> dict[tuple[int, int], tuple[int, tuple[int, int, int, int]]]:
    '''
    {(station, slot): (page, (x0, y0, x1, y1))}: the printed box for each
    station's left (slot 0) and right (slot 1) answer, in the canonical frame.
    The same on every form; which letter a slot holds depends on the form.
    '''
    practical_pages(stations)                 # raises when they do not fit
    boxes, station = {}, 1
    for page in P_FIRST_TOP:
        for r in range(practical_rows_per_page(page)):
            if station > stations:
                return boxes
            y0 = P_FIRST_TOP[page] + r * P_PITCH
            for slot, (x0, x1) in enumerate(P_BOX_X):
                boxes[(station, slot)] = (page, (x0, y0, x1, y0 + P_BOX_H))
            station += 1
    return boxes


def practical_crop(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    i = P_CROP_INSET
    return (x0 + i, y0 + i, x1 - i, y1 - i)


def _practical_page(page: int) -> Layout:
    id_digits = _v2_header()[0] if page == 1 else {}
    return Layout(f'practical-{page}', PRACTICAL_CODES[page], {}, id_digits,
                  max_questions=0, practical_page=page)


LAYOUTS = {lay.code: lay for lay in (_classic(), _v2(), _v2_keyed_unknown(),
                                     *(_practical_page(p) for p in PRACTICAL_CODES))}
CLASSIC = LAYOUTS[0]
V2 = LAYOUTS[1]
V2_KEYED = LAYOUTS[2]


def _inked(gray, cells) -> list[bool]:
    half = LAYOUT_CODE_SIZE // 2 - 2           # sample inside the square
    inked = []
    for cx, cy in cells:
        patch = gray[cy - half:cy + half, cx - half:cx + half]
        inked.append(patch.size > 0 and float(patch.mean()) < 110)
    return inked


def read_form(gray) -> str:
    '''The form printed on an aligned practical page, such as 'AC'.'''
    return ''.join(c for c, on in zip(FORM_LETTERS, _inked(gray, FORM_CELLS)) if on)


def detect_layout(gray) -> Layout:
    '''
    Read the layout code from an aligned grayscale page (uint8 or float,
    0-255). Unknown codes fall back to classic, since a stray pencil mark is
    the likeliest cause.
    '''
    inked = _inked(gray, LAYOUT_CODE_CELLS)
    if not inked[0]:
        return CLASSIC
    code = sum(1 << i for i, on in enumerate(inked[1:]) if on)
    return LAYOUTS.get(code, CLASSIC)
