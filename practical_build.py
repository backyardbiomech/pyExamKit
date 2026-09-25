'''
Build the printed materials for a lab practical from its source file.

From one practical .md this writes, into one folder:

- a form sheet per form, and one combined PDF that deals the forms out in the
  source file's order, so a stack handed down a row gives neighbors different
  forms;
- placards, one page per station: the station number, every question, and the
  station's images, with no station name or setup lines, since those can give
  answers away;
- the setup guide, for whoever sets up the room: each station's name, setup
  lines, images, and every question with its accepted answers, with a box to
  tick for each;
- the instructor key: every question and its answers, compactly.

Everything is drawn straight to PDF with PyMuPDF rather than printed from a
browser: none of it needs equations, and a direct PDF keeps one station per
page and full-size images without depending on anyone's print settings
(docs/dev/lab-practicals.md).

    uv run python practical_build.py exam.md -o out/ --students 48
'''
import argparse
import html
import io
from pathlib import Path

import fitz

import answer_sheet
import practical
from renderer import safe_name

PAGE = fitz.paper_rect('letter')
MARGIN = 36                          # half an inch
FOOTER = 20                          # room kept at the bottom for the footer line
GRAY = (0.4, 0.4, 0.4)

# Placards are read standing at a table, from arm's length
PLACARD_CSS = '''
body { font-family: sans-serif; font-size: 20pt; margin: 0; }
p { margin: 0; }
'''
STATION_SIZE = 60                    # points, for "Station 12"
QUESTION_GAP = 14                    # points between questions
IMAGE_GAP = 8                        # points between a question and its images
MIN_IMAGE_H = 180                    # 2.5 in; below this, station images move to a second page

DOC_CSS = '''
body { font-family: sans-serif; font-size: 10pt; margin: 0; }
h1 { font-size: 16pt; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; margin: 8pt 0 2pt 0; }
p { margin: 0 0 2pt 0; }
.meta { color: #555; }
.setup { font-size: 11pt; }
.head { font-weight: bold; }
.tick { font-size: 13pt; text-align: center; }
.q { font-weight: bold; text-align: center; }
.missing { color: #b00; }
'''
KEY_CSS = DOC_CSS.replace('font-size: 10pt;', 'font-size: 9pt;', 1)
CELL_PAD = 3
RULE = (0.6, 0.6, 0.6)
HEAD_FILL = (0.93, 0.93, 0.93)

# Column widths as fractions of the text width. MuPDF's HTML tables size
# columns by their content, so a long answer would squeeze the question
# column; the guide and key draw their own rows to keep columns fixed.
GUIDE_COLS = [('', 0.04, 'tick'), ('Q', 0.04, 'q'), ('Question', 0.44, ''),
              ('Full credit', 0.28, ''), ('Partial credit', 0.20, '')]
KEY_COLS = [('Q', 0.04, 'q'), ('Question', 0.42, ''), ('Full credit', 0.28, ''),
            ('Partial credit', 0.20, ''), ('Pts', 0.06, '')]


class Builder:
    '''
    Draws one practical's materials. Image paths in the source file are
    relative to it; any that cannot be found are listed in `warnings` and
    printed as a note in place of the image, so a missing file is caught on
    paper rather than left out silently.
    '''

    def __init__(self, p: practical.Practical):
        self.p = p
        self.base = p.path.parent if p.path else Path.cwd()
        self.archive = fitz.Archive(str(self.base))
        self.warnings: list[str] = []
        for s in p.stations:
            for img in s.images:
                self._check_image(img, f'station {s.number}')
            for q in s.questions.values():
                for img in q.images:
                    self._check_image(img, q.key)

    def _check_image(self, rel: str, where: str):
        if not (self.base / rel).is_file():
            self.warnings.append(f'Image {rel} ({where}) was not found beside the source file.')

    def _found(self, rel: str) -> bool:
        return (self.base / rel).is_file()

    # ── Placards ───────────────────────────────────────────────────────────

    def placards(self) -> bytes:
        '''One page per station; a station whose images do not fit under its
        questions gets them on a second page, and a warning.'''
        doc = fitz.open()
        for s in self.p.stations:
            self._placard(doc, s)
        return doc.tobytes(garbage=4, deflate=True)

    def _placard(self, doc, s: practical.Station):
        '''
        Each question prints full width with its own images under it, and the
        station's images come last. Whatever height the text leaves is shared
        among the image blocks, none taking more than it needs to fill the
        page width. If the station's images would get less than MIN_IMAGE_H,
        they move to a second page.
        '''
        page = doc.new_page(width=PAGE.width, height=PAGE.height)
        left, right = MARGIN, PAGE.width - MARGIN
        bottom = PAGE.height - MARGIN - FOOTER
        self._placard_footer(page)
        page.insert_text((left, MARGIN + STATION_SIZE * 0.8), f'Station {s.number}',
                         fontname='hebo', fontsize=STATION_SIZE)
        top = MARGIN + STATION_SIZE + 10
        page.draw_line((left, top), (right, top), color=(0, 0, 0), width=1.5)
        top += 16

        # Only the letters some form uses
        qs = [s.questions[c] for c in self.p.letters if c in s.questions]
        bodies = [f'<p><b>{q.letter}.</b> {html.escape(q.text)}</p>' for q in qs]
        heights = [_html_height(b, right - left, PLACARD_CSS) for b in bodies]
        text_h = sum(heights) + QUESTION_GAP * len(qs) + IMAGE_GAP * sum(bool(q.images)
                                                                          for q in qs)
        blocks = [q.images for q in qs if q.images]
        station_here = bool(s.images)
        shares = self._shares(bottom - top - text_h, blocks + [s.images] * station_here,
                              right - left)
        if station_here and shares[-1] < MIN_IMAGE_H:
            self.warnings.append(f'Station {s.number}: its images did not fit under the '
                                 f'questions, so they print on a second page.')
            station_here = False
            shares = self._shares(bottom - top - text_h, blocks, right - left)
        if bottom - top - text_h < 0 or any(h < MIN_IMAGE_H / 2 for h in shares):
            self.warnings.append(f'Station {s.number}: the questions and their images are '
                                 f'crowded; shorten the questions or use fewer images.')

        y = top
        share = iter(shares)
        for q, body, h in zip(qs, bodies, heights):
            page.insert_htmlbox(fitz.Rect(left, y, right, y + h + 4), body, css=PLACARD_CSS)
            y += h
            if q.images:
                img_h = next(share)
                self._images(page, q.images, fitz.Rect(left, y + IMAGE_GAP, right,
                                                       y + IMAGE_GAP + img_h))
                y += IMAGE_GAP + img_h
            y += QUESTION_GAP
        if station_here:
            self._images(page, s.images, fitz.Rect(left, y, right, y + next(share)))
        elif s.images:
            page = self._continuation(doc, s)
            self._images(page, s.images, fitz.Rect(left, MARGIN + 40, right, bottom))

    def _shares(self, space: float, blocks: list[list[str]], width: float) -> list[float]:
        '''Split `space` among the image blocks: equal shares, except that a
        block needing less than its share at full width gets only what it
        needs, and the rest goes to the others.'''
        need = [self._natural_height(b, width) for b in blocks]
        shares = [0.0] * len(blocks)
        open_ = set(range(len(blocks)))
        space = max(space, 0)
        while open_:
            each = space / len(open_)
            small = {i for i in open_ if need[i] <= each}
            if not small:
                for i in open_:
                    shares[i] = each
                break
            for i in small:
                shares[i] = need[i]
                space -= need[i]
            open_ -= small
        return shares

    def _natural_height(self, images: list[str], width: float) -> float:
        '''How tall the images print at full width, laid out as _images lays them.'''
        cols = 1 if len(images) == 1 else 2
        w = (width - 10 * (cols - 1)) / cols
        heights = [w * self._aspect(rel) for rel in images]
        rows = [max(heights[i:i + cols]) for i in range(0, len(heights), cols)]
        return sum(rows) + 10 * (len(rows) - 1)

    def _aspect(self, rel: str) -> float:
        '''Height over width; a missing image is drawn as a 3:2 box.'''
        if not self._found(rel):
            return 2 / 3
        pix = fitz.Pixmap(str(self.base / rel))
        return pix.height / pix.width

    def _continuation(self, doc, s):
        page = doc.new_page(width=PAGE.width, height=PAGE.height)
        self._placard_footer(page)
        page.insert_text((MARGIN, MARGIN + 22), f'Station {s.number} (continued)',
                         fontname='hebo', fontsize=24)
        return page

    def _placard_footer(self, page):
        page.insert_text((MARGIN, PAGE.height - MARGIN), self.p.title,
                         fontname='helv', fontsize=9, color=GRAY)

    def _images(self, page, images: list[str], area: fitz.Rect):
        '''Fill `area` with the images: one takes it all, more share it in
        two columns. Each keeps its proportions, centered in its cell.'''
        cols = 1 if len(images) == 1 else 2
        rows = -(-len(images) // cols)
        gap = 10
        w = (area.width - gap * (cols - 1)) / cols
        h = (area.height - gap * (rows - 1)) / rows
        for i, rel in enumerate(images):
            r, c = divmod(i, cols)
            cell = fitz.Rect(area.x0 + c * (w + gap), area.y0 + r * (h + gap),
                             area.x0 + c * (w + gap) + w, area.y0 + r * (h + gap) + h)
            if self._found(rel):
                page.insert_image(cell, filename=str(self.base / rel), keep_proportion=True)
            else:
                page.draw_rect(cell, color=(0.7, 0, 0), width=1, dashes='[4] 0')
                page.insert_htmlbox(cell + (8, 8, -8, -8),
                                    f'<p>Missing image:<br/>{html.escape(rel)}</p>',
                                    css='body{font-family:sans-serif;font-size:12pt;color:#b00}')

    # ── Setup guide and instructor key ─────────────────────────────────────

    def _thumb(self, rel: str, width_in: float) -> str:
        if not self._found(rel):
            return f'<p class="missing">Missing: {html.escape(rel)}</p>'
        return (f'<img src="{html.escape(rel)}" width="{int(width_in * 72)}"/>'
                f'<p class="meta">{html.escape(rel)}</p>')

    def _answers(self, answers: list[str]) -> str:
        return '<br/>'.join(html.escape(a) for a in answers) or '<i>none</i>'

    def _partial(self, q: practical.Question) -> str:
        return '<br/>'.join(html.escape(a) for a in q.partial)

    def _intro(self, what: str, note: str) -> str:
        p = self.p
        return (f'<h1>{html.escape(p.title)}: {what}</h1>'
                f'<p class="meta">{len(p.stations)} stations. Forms {", ".join(p.forms)}. '
                f'{html.escape(note)}</p>')

    def setup_guide(self) -> bytes:
        doc = _Flow(DOC_CSS, self.archive, GUIDE_COLS)
        doc.keep([doc.html(self._intro(
            'setup guide',
            'Set up each station, check every pin or pointer against its full-credit '
            'answer, and tick the box.'))])
        for s in self.p.stations:
            name = f': {html.escape(s.name)}' if s.name else ''
            items = [doc.html(f'<h2>☐ Station {s.number}{name}</h2>' +
                              ''.join(f'<p class="setup">{html.escape(line)}</p>'
                                      for line in s.setup))]
            items += [doc.html(self._thumb(img, 2.4)) for img in s.images]
            items.append(doc.header())
            for q in self._questions(s):
                text = f'<p>{html.escape(q.text)}</p>' + ''.join(self._thumb(i, 1.4)
                                                                 for i in q.images)
                items.append(doc.row(['☐', q.letter, text, self._answers(q.full),
                                      self._partial(q)]))
            doc.keep(items)
        return doc.finish(f'{self.p.title}: setup guide')

    def instructor_key(self) -> bytes:
        p = self.p
        doc = _Flow(KEY_CSS, self.archive, KEY_COLS)
        doc.keep([doc.html(self._intro('instructor key',
                                       f'Questions are worth {_pts(p.points)} unless marked.'))])
        for s in p.stations:
            name = f': {html.escape(s.name)}' if s.name else ''
            items = [doc.html(f'<h2>Station {s.number}{name}</h2>'), doc.header()]
            for q in self._questions(s):
                pts = _pts(q.points) if q.points is not None else ''
                items.append(doc.row([q.letter, html.escape(q.text), self._answers(q.full),
                                      self._partial(q), pts]))
            doc.keep(items)
        return doc.finish(f'{p.title}: instructor key')

    @staticmethod
    def _questions(s: practical.Station) -> list[practical.Question]:
        return [s.questions[c] for c in practical.LETTERS if c in s.questions]


def _pts(x: float) -> str:
    return f'{x:g} pt' if x == 1 else f'{x:g} pts'


def _html_height(body: str, width: float, css: str, archive=None) -> float:
    '''How tall `body` sets at `width`, by the same engine that draws it.'''
    story = fitz.Story(body, user_css=css, archive=archive)
    _, filled = story.place(fitz.Rect(0, 0, width, 100000))
    return fitz.Rect(filled).height


class _Flow:
    '''
    A document of HTML blocks and fixed-column table rows, set down the pages.
    Each group passed to keep() starts on a fresh page when it does not fit
    the rest of the current one but would fit a page; otherwise it breaks
    between items. Items never split. Every page gets a numbered footer.

    Text is drawn as Stories on a DocumentWriter, which is some fifty times
    faster than Page.insert_htmlbox; cell rules and fills are added after,
    on the finished pages, since a writer's device cannot draw shapes.
    '''

    def __init__(self, css: str, archive, cols):
        self.css, self.archive = css, archive
        self.frame = fitz.Rect(MARGIN, MARGIN, PAGE.width - MARGIN,
                               PAGE.height - MARGIN - FOOTER)
        self.cols = cols
        self.widths = [self.frame.width * w for _, w, _ in cols]
        self.out = io.BytesIO()
        self.writer = fitz.DocumentWriter(self.out)
        self.dev = None
        self.page_no = -1
        self.cells: list[tuple[int, fitz.Rect, tuple | None]] = []
        self.y = self.frame.y0

    def _draw(self, body: str, rect: fitz.Rect):
        story = fitz.Story(body, user_css=self.css, archive=self.archive)
        story.place(rect)
        story.draw(self.dev)

    # Items are (height, draw function taking the top y)
    def html(self, body: str):
        h = _html_height(body, self.frame.width, self.css, self.archive)
        return h, lambda y: self._draw(body, fitz.Rect(self.frame.x0, y, self.frame.x1,
                                                       y + h + 2))

    def header(self):
        return self.row([f'<span class="head">{title}</span>' for title, _, _ in self.cols],
                        fill=HEAD_FILL)

    def row(self, cells: list[str], fill=None):
        bodies = [f'<div class="{cls}">{c}</div>' if cls else c
                  for c, (_, _, cls) in zip(cells, self.cols)]
        h = max(_html_height(b, w - 2 * CELL_PAD, self.css, self.archive)
                for b, w in zip(bodies, self.widths)) + 2 * CELL_PAD

        def draw(y):
            x = self.frame.x0
            for b, w in zip(bodies, self.widths):
                cell = fitz.Rect(x, y, x + w, y + h)
                self.cells.append((self.page_no, cell, fill))
                self._draw(b, cell + (CELL_PAD, CELL_PAD, -CELL_PAD, 2))
                x += w
        return h, draw

    def keep(self, items):
        total = sum(h for h, _ in items)
        if (self.dev is None or
                (self.y + total > self.frame.y1 and total <= self.frame.height)):
            self._new_page()
        for h, draw in items:
            if self.y + h > self.frame.y1 and self.y > self.frame.y0:
                self._new_page()
            draw(self.y)
            self.y += h

    def _new_page(self):
        if self.dev is not None:
            self.writer.end_page()
        self.dev = self.writer.begin_page(PAGE)
        self.page_no += 1
        self.y = self.frame.y0

    def finish(self, footer: str) -> bytes:
        if self.dev is not None:
            self.writer.end_page()
        self.writer.close()
        doc = fitz.open('pdf', self.out.getvalue())
        for n, cell, fill in self.cells:
            if fill:
                doc[n].draw_rect(cell, color=None, fill=fill, overlay=False)
            doc[n].draw_rect(cell, color=RULE, width=0.6)
        for i, page in enumerate(doc, 1):
            label = f'{footer} · page {i} of {len(doc)}'
            w = fitz.get_text_length(label, fontname='helv', fontsize=8)
            page.insert_text(((PAGE.width - w) / 2, PAGE.height - MARGIN), label,
                             fontname='helv', fontsize=8, color=GRAY)
        return doc.tobytes(garbage=4, deflate=True)


# ── Writing the folder ─────────────────────────────────────────────────────

def write_form_sheets(p: practical.Practical, outdir: Path, students: int = 0,
                      logo=answer_sheet.DEFAULT_LOGO) -> list[Path]:
    '''
    One PDF per form, named after the practical, plus a combined PDF of
    `students` sheets in dealing order when `students` is given. Returns the
    paths written.
    '''
    outdir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(p.title)
    # Printed double-sided, so a sheet with an odd number of pages gets a
    # blank back and no student's page 1 lands on another's last page
    sheets = {f: answer_sheet.build_practical_sheet(len(p.stations), f, p.title, logo,
                                                    double_sided=True)
              for f in p.forms}
    written = []
    for f, pdf in sheets.items():
        path = outdir / f'{stem}_form_{f}.pdf'
        path.write_bytes(pdf)
        written.append(path)
    if students > 0:
        combined = fitz.open()
        docs = {f: fitz.open(stream=pdf, filetype='pdf') for f, pdf in sheets.items()}
        for i in range(students):
            combined.insert_pdf(docs[p.forms[i % len(p.forms)]])
        path = outdir / f'{stem}_all_forms_{students}_students.pdf'
        combined.save(path, garbage=4, deflate=True)
        written.append(path)
    return written


def build(p: practical.Practical, outdir: Path, students: int = 0,
          logo=answer_sheet.DEFAULT_LOGO) -> tuple[list[Path], list[str]]:
    '''Write every printed material into `outdir`. Returns the paths written
    and any warnings about the build (missing images, crowded placards).'''
    written = write_form_sheets(p, outdir, students, logo)
    b = Builder(p)
    stem = safe_name(p.title)
    for name, pdf in (('placards', b.placards()),
                      ('setup_guide', b.setup_guide()),
                      ('instructor_key', b.instructor_key())):
        path = outdir / f'{stem}_{name}.pdf'
        path.write_bytes(pdf)
        written.append(path)
    return written, b.warnings


def default_outdir(p: practical.Practical) -> Path:
    base = p.path.parent if p.path else Path.cwd()
    return base / f'{safe_name(p.title)}_practical'


def main():
    ap = argparse.ArgumentParser(description='Build a lab practical\'s printed materials.')
    ap.add_argument('source', type=Path, help='the practical .md file')
    ap.add_argument('-o', '--outdir', type=Path, help='output folder (default: beside the source)')
    ap.add_argument('--students', type=int, default=0,
                    help='also write one combined PDF with this many sheets, forms dealt in order')
    ap.add_argument('--no-logo', action='store_true')
    args = ap.parse_args()
    try:
        p = practical.load(args.source)
    except practical.PracticalError as exc:
        raise SystemExit(f'Cannot use {args.source}:\n{exc}')
    for w in p.warnings:
        print(f'warning: {w}')
    written, warnings = build(p, args.outdir or default_outdir(p), args.students,
                              logo=None if args.no_logo else answer_sheet.DEFAULT_LOGO)
    for w in warnings:
        print(f'warning: {w}')
    for path in written:
        print(f'Wrote {path}')


if __name__ == '__main__':
    main()
