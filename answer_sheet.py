'''
Draw the v2 answer sheet as a PDF, from the bubble positions in
sheet_layout.py so the printed sheet and the scanner always agree.

Written-answer (fill-in-the-blank) questions keep their number in the
bubble grid, with an arrow in place of the bubbles, and get a numbered
writing box in the columns the exam does not use. The box positions are
returned so the exam key can carry them as crop regions, which saves drawing
them by hand at scan time.

A sheet built for an exam with ordering, matching, or dropdown questions
takes its row runs from the exam (sheet_layout.keyed_layout), so each such
question's rows sit together between gaps; the layout code tells the
scanner to take the rows from the key.

    uv run python answer_sheet.py -n 60 --written 14,15 -o sheet.pdf
'''
import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import fitz

import bubbles
import sheet_layout as L

HERE = Path(__file__).resolve().parent
DEFAULT_LOGO = HERE / 'images' / 'longwood_logo.pdf'

PT = 1 / L.PX_PER_PT            # canonical px -> PDF points
BLACK = (0, 0, 0)
RING = (0.45, 0.45, 0.45)       # printed bubble ring: light, so a faint fill stands out
LETTER = (0.55, 0.55, 0.55)
GUIDE = (0.35, 0.35, 0.35)
R = L.BUBBLE_DIAMETER / 2

# Writing boxes, in canonical px
BOX_H = 84
BOX_LABEL = 22                   # space above each box for its number
BOX_GAP = 16
BOX_MIN_W = 400                  # about 2.8 inches; narrower invites cramped writing
BOX_MAX_W = 620
AREA_TOP = L.V2_Q_TOP - 20
AREA_BOTTOM = 1490


class SheetError(ValueError):
    '''A sheet that cannot be drawn as asked; the message is shown to the user.'''


@dataclass
class SheetResult:
    pdf: bytes
    # {question number: (x1, y1, x2, y2)} crop regions in the scanner's frame
    boxes: dict[int, tuple[int, int, int, int]]


def _p(x, y):
    return fitz.Point(x * PT, y * PT)


def _rect(x0, y0, x1, y1):
    return fitz.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT)


def _text(page, x, y, s, size=9, color=BLACK, bold=False, align='left'):
    '''Text with its baseline at canonical (x, y).'''
    font = 'hebo' if bold else 'helv'
    w = fitz.get_text_length(s, fontname=font, fontsize=size)
    if align == 'right':
        x -= w / PT
    elif align == 'center':
        x -= w / PT / 2
    page.insert_text(_p(x, y), s, fontname=font, fontsize=size, color=color)


def _bubble(page, cx, cy, label='', r=R, fill=None):
    page.draw_circle(_p(cx, cy), r * PT, color=RING, fill=fill, width=0.6)
    if label and fill is None:
        _text(page, cx, cy + 4.6, label, size=6.5, color=LETTER, align='center')


def _grid_row(page, row):
    for lab, cx, cy in row:
        _bubble(page, cx, cy, lab)


def _written_row(page, q, row):
    '''
    A question answered in a box: the number stays and the bubbles become an
    arrow. The shaft is broken wherever a bubble would be, so nothing is
    printed inside the disks the reader measures and a row left off the
    ignore list still reads as blank.
    '''
    y = row[0][2]
    clear = bubbles.MEASURE_RADIUS + 2
    xs = [cx for _, cx, _ in row]
    tip = xs[-1] + 28
    stops = [xs[0] - 12] + [x for cx in xs for x in (cx - clear, cx + clear)] + [tip - 8]
    for x0, x1 in zip(stops[::2], stops[1::2]):
        page.draw_line(_p(x0, y), _p(x1, y), color=BLACK, width=1.4)
    page.draw_polyline([_p(tip - 12, y - 6), _p(tip, y), _p(tip - 12, y + 6)],
                       color=BLACK, fill=BLACK, closePath=True)


def _header(page, logo, title):
    if logo and Path(logo).exists():
        src = fitz.open(logo)
        r = src[0].rect
        w = 360                                   # 2.5 in, the brand guide's minimum
        h = w * r.height / r.width
        page.show_pdf_page(_rect(60, 42, 60 + w, 42 + h), src, 0)
    if title:
        _text(page, 60, 132, title, size=10, bold=True)
    _text(page, 470, 58, 'Name (print clearly)', size=8, color=GUIDE)
    page.draw_line(_p(470, 104), _p(1085, 104), color=BLACK, width=0.8)


def _guide(page, top=170):
    '''How to fill a bubble: one right way, six wrong ones.'''
    _text(page, 60, top, 'How to mark your answers', size=11, bold=True)
    _text(page, 60, top + 26, 'Fill the bubble completely and darkly.', size=9)
    _text(page, 60, top + 46, 'To change an answer, erase the old mark completely.', size=9)
    r = 13                                      # small enough not to look like a registration mark
    y = top + 112
    x = 90
    label_y = y - 30
    _text(page, x, label_y, 'RIGHT', size=9, bold=True, align='center')
    _bubble(page, x, y, r=r, fill=BLACK)
    page.draw_line(_p(x + 50, y - 44), _p(x + 50, y + 38), color=GUIDE, width=0.5)

    wrong = ['Check', 'X', 'Dot', 'Half', 'Too light', 'Circled']
    first, last = x + 110, x + 110 + (len(wrong) - 1) * 92
    # One label and a bracket over the whole group, so no single example
    # reads as the exception
    _text(page, (first + last) / 2, label_y, 'WRONG: ALL SIX OF THESE', size=9, bold=True,
          align='center')
    by = label_y + 8
    page.draw_line(_p(first - 30, by), _p(last + 30, by), color=BLACK, width=0.8)
    for bx in (first - 30, last + 30):
        page.draw_line(_p(bx, by), _p(bx, by + 8), color=BLACK, width=0.8)
    for i, name in enumerate(wrong):
        cx = first + i * 92
        if name == 'Too light':
            _bubble(page, cx, y, r=r, fill=(0.82, 0.82, 0.82))
        else:
            _bubble(page, cx, y, 'B', r=r)
        if name == 'Check':
            page.draw_polyline([_p(cx - 8, y), _p(cx - 2, y + 7), _p(cx + 10, y - 9)],
                               color=BLACK, width=1.6)
        elif name == 'X':
            page.draw_line(_p(cx - 8, y - 8), _p(cx + 8, y + 8), color=BLACK, width=1.6)
            page.draw_line(_p(cx - 8, y + 8), _p(cx + 8, y - 8), color=BLACK, width=1.6)
        elif name == 'Dot':
            page.draw_circle(_p(cx, y), 3 * PT, color=BLACK, fill=BLACK)
        elif name == 'Half':
            shape = page.new_shape()
            shape.draw_sector(_p(cx, y), _p(cx - r, y), 180)
            shape.finish(color=BLACK, fill=BLACK, width=0)
            shape.commit()
        elif name == 'Circled':
            page.draw_circle(_p(cx, y), (r + 5) * PT, color=BLACK, width=1.2)
        _text(page, cx, y + 34, name, size=8, align='center')
    _text(page, (first + last) / 2, y + 56,
          'Each of these may be read as blank or as the wrong answer.', size=8,
          align='center')


def _id_block(page):
    top = L.V2_ID_TOP
    x0 = L.V2_ID_X
    xs = [x0 + L.V2_ID_COL * c for c in range(8)]
    _text(page, xs[0] - 32, top - 122, 'Longwood ID number', size=10, bold=True)
    _text(page, xs[0] - 32, top - 104, 'Write it in the boxes, then fill',
          size=7, color=GUIDE)
    _text(page, xs[0] - 32, top - 90, 'one bubble under each digit.', size=7, color=GUIDE)
    _text(page, xs[0] - 22, top - 42, 'L', size=14, bold=True, align='center')
    for x in xs:
        page.draw_rect(_rect(x - 13, top - 70, x + 13, top - 30), color=BLACK, width=0.8)
    for row in sheet_layout_rows(L.V2.id_digits):
        _grid_row(page, row)


def sheet_layout_rows(rows: dict):
    return [rows[k] for k in sorted(rows)]


def _version(page, version_letter):
    row = L.V2.version['V']
    _text(page, 60, L.V2_VERSION_Y + 4, 'Exam version', size=10, bold=True)
    _text(page, 60, L.V2_VERSION_Y + 20, 'see the end of your exam', size=6.5,
          color=GUIDE)
    for lab, cx, cy in row:
        _bubble(page, cx, cy, lab)
    if version_letter:
        # Small print in the bottom margin, for whoever hands the sheets out;
        # nowhere a neighbor would read it at a glance.
        _text(page, 300, 1537, f'Form {version_letter}', size=7, color=GUIDE)


def _layout_code(page, code):
    cells = L.LAYOUT_CODE_CELLS
    bits = [1] + [(code >> i) & 1 for i in range(len(cells) - 1)]
    h = L.LAYOUT_CODE_SIZE / 2
    for (cx, cy), on in zip(cells, bits):
        if on:
            page.draw_rect(_rect(cx - h, cy - h, cx + h, cy + h), color=None, fill=BLACK)


def _registration(page):
    for x, y in L.REG_POINTS:
        page.draw_circle(_p(x, y), L.REG_DIAMETER / 2 * PT, color=None, fill=BLACK)


def _place_boxes(written: list[int], first_free_col: int) -> dict[int, tuple]:
    '''Stack writing boxes in the unused question columns, top to bottom.'''
    if not written:
        return {}
    if first_free_col >= len(L.V2_Q_COL_X):
        raise SheetError('No room for written-answer boxes: every question column is in use. '
                         'Written questions need an exam of 120 or fewer answer rows.')
    x0 = L.V2_Q_COL_X[first_free_col] - 50
    x1 = 1150
    free_w = x1 - x0
    if free_w < BOX_MIN_W:
        raise SheetError('No room for written-answer boxes: only one question column is free. '
                         'Written questions need an exam of 90 or fewer answer rows.')
    ncols = 2 if free_w >= 2 * BOX_MIN_W + 30 else 1
    w = min(BOX_MAX_W, (free_w - 30 * (ncols - 1)) / ncols)
    pitch = BOX_LABEL + BOX_H + BOX_GAP
    per_col = int((AREA_BOTTOM - AREA_TOP) // pitch)
    if len(written) > ncols * per_col:
        raise SheetError(f'{len(written)} written questions do not fit; this sheet has room '
                         f'for {ncols * per_col}.')
    boxes = {}
    for i, q in enumerate(written):
        c, r = divmod(i, per_col)
        bx = x0 + c * (w + 30)
        by = AREA_TOP + r * pitch + BOX_LABEL
        boxes[q] = (int(bx), int(by), int(bx + w), int(by + BOX_H))
    return boxes


def build_sheet(questions: int = 150, written=(), title: str = '', version_letter: str = '',
                logo=DEFAULT_LOGO, columns: list[list[int]] | None = None) -> SheetResult:
    '''
    Draw a sheet with `questions` answer rows. Question numbers in `written`
    get writing boxes instead of bubbles. `columns` gives the row runs of a
    sheet grouped by question (sheet_layout.keyed_layout); without it the
    rows fall in the standard groups of five. Returns the PDF and the box
    crops.
    '''
    if columns:
        layout = L.keyed_layout(columns)
        if layout.max_questions != questions:
            raise SheetError(f'The row runs hold {layout.max_questions} rows, '
                             f'not {questions}.')
        used_cols = len(columns)
    else:
        layout = L.V2
        used_cols = math.ceil(questions / 30)
    if not 1 <= questions <= L.V2.max_questions:
        raise SheetError(f'An answer sheet holds 1 to {L.V2.max_questions} questions.')
    written = sorted(set(int(q) for q in written))
    bad = [q for q in written if not 1 <= q <= questions]
    if bad:
        raise SheetError(f'Written question numbers outside 1-{questions}: '
                         + ', '.join(map(str, bad)))

    doc = fitz.open()
    page = doc.new_page(width=L.PAGE_W * PT, height=L.PAGE_H * PT)
    _registration(page)
    _layout_code(page, layout.code)
    _header(page, logo, title)
    _guide(page)
    _id_block(page)
    _version(page, version_letter)

    _text(page, 60, L.V2_Q_TOP - 42, 'Answers', size=11, bold=True)
    if written:
        _text(page, 170, L.V2_Q_TOP - 42,
              'Rows with an arrow are answered in writing, in the numbered box.',
              size=8, color=GUIDE)

    for k, row in layout.question_rows(questions).items():
        q = int(k[1:])
        _, ax, ay = row[0]
        _text(page, ax - 17, ay + 4, str(q), size=9, bold=True, align='right')
        if q in written:
            _written_row(page, q, row)
        else:
            _grid_row(page, row)

    boxes = _place_boxes(written, used_cols)
    for q, (x0, y0, x1, y1) in boxes.items():
        _text(page, x0, y0 - 6, f'{q}.', size=10, bold=True)
        page.draw_rect(_rect(x0, y0, x1, y1), color=GUIDE, width=0.8)
    if not written and used_cols < len(L.V2_Q_COL_X):
        # A plain sheet: the unused columns become one open box, as on the
        # classic sheets, for pasting in a question or for scratch work.
        x0 = L.V2_Q_COL_X[used_cols] - 50
        page.draw_rect(_rect(x0, AREA_TOP, 1150, AREA_BOTTOM), color=BLACK, width=1.2)

    # Crops sit just inside each box, so the printed border is not transcribed.
    crops = {q: (x0 + 4, y0 + 4, x1 - 4, y1 - 4) for q, (x0, y0, x1, y1) in boxes.items()}
    return SheetResult(doc.tobytes(garbage=4, deflate=True), crops)


# ── Lab practical form sheets ──────────────────────────────────────────────

PRACTICAL_NOTE = [
    'Answer only the letters printed on this sheet, at every station.',
    'Only what is written inside each box will be graded,',
    'and everything written inside a box will be graded.',
]


def _form_code(page, form):
    h = L.LAYOUT_CODE_SIZE / 2
    for (cx, cy), letter in zip(L.FORM_CELLS, L.FORM_LETTERS):
        if letter in form:
            page.draw_rect(_rect(cx - h, cy - h, cx + h, cy + h), color=None, fill=BLACK)


def build_practical_sheet(stations: int, form: str, title: str = '',
                          logo=DEFAULT_LOGO) -> bytes:
    '''
    A lab practical form sheet: two writing boxes per station, labeled with
    the form's two letters, on as many pages as the stations need. The form
    is printed as squares on every page, so the scanner never relies on
    anything the student wrote to know which questions a box answers.
    '''
    form = ''.join(sorted(form.upper()))
    if len(form) != 2 or any(c not in L.FORM_LETTERS for c in form) or form[0] == form[1]:
        raise SheetError(f'A form is two different letters from A to D, not "{form}".')
    try:
        pages = L.practical_pages(stations)
        boxes = L.practical_boxes(stations)
    except L.RunsError as exc:
        raise SheetError(str(exc)) from None

    doc = fitz.open()
    for n in range(1, pages + 1):
        page = doc.new_page(width=L.PAGE_W * PT, height=L.PAGE_H * PT)
        _registration(page)
        _layout_code(page, L.PRACTICAL_CODES[n])
        _form_code(page, form)
        # Small print for whoever hands the sheets out and staples them
        _text(page, 440, 1537, f'Form {form}, page {n} of {pages}', size=7, color=GUIDE)
        if n == 1:
            _header(page, logo, title)
            _id_block(page)
            y = 190
            for i, line in enumerate(PRACTICAL_NOTE):
                _text(page, 60, y, line, size=11, bold=i > 0)
                y += 26 if i else 40
        else:
            _text(page, 60, 54, 'Name', size=8, color=GUIDE)
            page.draw_line(_p(60, 96), _p(600, 96), color=BLACK, width=0.8)
        top = L.P_FIRST_TOP[n]
        _text(page, 60, top - 16, 'Station', size=10, bold=True)
        for (station, slot), (bp, (x0, y0, x1, y1)) in boxes.items():
            if bp != n:
                continue
            mid = (y0 + y1) / 2 + 6
            if slot == 0:
                _text(page, 76, mid, str(station), size=13, bold=True, align='right')
            _text(page, x0 - 16, mid, form[slot], size=13, bold=True, align='center')
            page.draw_rect(_rect(x0, y0, x1, y1), color=BLACK, width=0.9)
    return doc.tobytes(garbage=4, deflate=True)


def main():
    ap = argparse.ArgumentParser(description='Draw a pyExamKit answer sheet.')
    ap.add_argument('-n', '--questions', type=int, default=150)
    ap.add_argument('--written', default='', help='comma-separated written-answer question numbers')
    ap.add_argument('--title', default='', help='printed under the logo, e.g. "BIOL 206 Exam 2"')
    ap.add_argument('--no-logo', action='store_true')
    ap.add_argument('-o', '--out', default='answer_sheet.pdf')
    args = ap.parse_args()
    written = [int(x) for x in args.written.split(',') if x.strip()]
    res = build_sheet(args.questions, written, args.title,
                      logo=None if args.no_logo else DEFAULT_LOGO)
    Path(args.out).write_bytes(res.pdf)
    print(f'Wrote {args.out}')
    for q, c in res.boxes.items():
        print(f'  box {q}: crop {c}')


if __name__ == '__main__':
    main()
