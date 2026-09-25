'''
Answer sheet geometry: where every bubble sits, defined once.

The scanner reads bubbles at these centers and answer_sheet.py draws the
printed sheet from them, so the two cannot drift apart. Coordinates are in
the scanner's canonical frame: a US Letter page at 144 dpi (1224 x 1584 px),
which is 2 px per PDF point.

Two layouts exist. 'classic' is the Illustrator sheet in images/ that
predates this module; its numbers are measured from that PDF and must not
change, since printed stock and archived scans depend on them. 'v2' is the
generated sheet. Both share the three registration circles, so one
alignment step serves either, and the layout is identified after alignment
by a printed code (see LAYOUT_CODE_CELLS).
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
V2_Q_TOP = 610                              # row 1 center
V2_Q_ROW = 28                               # row pitch
V2_Q_GROUP_GAP = 14                         # extra space after every 5 rows
V2_ID_X = 890                               # first ID column center
V2_ID_TOP = 250                             # digit 0 center
V2_ID_COL = 30
V2_VERSION_Y = 470
V2_VERSION_X = 250                          # bubble A center


def v2_question_y(within: int) -> float:
    '''Center y of the row at 0-based position `within` a 30-row column.'''
    return V2_Q_TOP + V2_Q_ROW * within + V2_Q_GROUP_GAP * (within // 5)


def _v2() -> Layout:
    questions = {}
    for i in range(1, 151):
        col, within = divmod(i - 1, 30)
        questions[f'Q{i:03d}'] = _row(LETTERS, V2_Q_COL_X[col], v2_question_y(within),
                                      BUBBLE_PITCH, 0)
    id_digits = {f'ID{c + 1:02d}': _row(DIGITS, V2_ID_X + V2_ID_COL * c, V2_ID_TOP,
                                        0, BUBBLE_PITCH)
                 for c in range(8)}
    version = {'V': _row('ABCD', V2_VERSION_X, V2_VERSION_Y, BUBBLE_PITCH + 8, 0)}
    return Layout('v2', 1, questions, id_digits, version=version)


LAYOUTS = {lay.code: lay for lay in (_classic(), _v2())}
CLASSIC = LAYOUTS[0]
V2 = LAYOUTS[1]


def detect_layout(gray) -> Layout:
    '''
    Read the layout code from an aligned grayscale page (uint8 or float,
    0-255). Unknown codes fall back to classic, since a stray pencil mark is
    the likeliest cause.
    '''
    half = LAYOUT_CODE_SIZE // 2 - 2           # sample inside the square
    inked = []
    for cx, cy in LAYOUT_CODE_CELLS:
        patch = gray[cy - half:cy + half, cx - half:cx + half]
        inked.append(patch.size > 0 and float(patch.mean()) < 110)
    if not inked[0]:
        return CLASSIC
    code = sum(1 << i for i, on in enumerate(inked[1:]) if on)
    return LAYOUTS.get(code, CLASSIC)
