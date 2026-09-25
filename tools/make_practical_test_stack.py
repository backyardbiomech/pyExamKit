'''
Make a synthetic scanned stack of filled-in lab practical form sheets, for
testing without a printer or scanner.

Each invented student gets a form (dealt in the practical's order), a name
written on every page, an ID written in the boxes and bubbled in pencil, and
a handwritten answer in every box of their form. Answers are drawn from the
key and then varied: most full credit, some misspelled, some partial-credit
answers, some wrong (another question's answer), some blank, and a few
deliberate edge cases (a crossed-out answer, writing that runs past the box,
a note written outside a box, a very light pencil ID, an ID one digit off the
roster). Each page is then printed and scanned in software: rotated, shifted,
scaled, blurred, speckled, and saved as a 200 dpi JPEG inside one PDF, the
way a copier's scan-to-PDF arrives.

Every name and ID is invented. Written to the output folder:

    scans.pdf       the stack, two pages per student, in dealing order
    roster.csv      the class roster (LastName, FirstName, ID)
    students.csv    per student: form, the ID on the roster and as bubbled
    answers.csv     per student and question: what was written, and why

    uv run python tools/make_practical_test_stack.py tests/fixtures/practical/practical_test.md
'''
import argparse
import csv
import io
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import answer_sheet  # noqa: E402
import practical  # noqa: E402
import sheet_layout as L  # noqa: E402

DPI = 200
K = DPI / 144                      # canonical px -> scan px

FONT_DIRS = [Path('/System/Library/Fonts/Supplemental'), Path('/System/Library/Fonts'),
             Path('/Library/Fonts'), Path.home() / 'Library' / 'Fonts']
HANDS = ['Bradley Hand Bold.ttf', 'Noteworthy.ttc', 'Chalkboard.ttc', 'MarkerFelt.ttc',
         'Comic Sans MS.ttf', 'ChalkboardSE.ttc']

FIRST = ['Jordan', 'Casey', 'Riley', 'Morgan', 'Avery', 'Quinn', 'Rowan', 'Emerson',
         'Harper', 'Sawyer', 'Finley', 'Reese', 'Dakota', 'Hayden', 'Parker', 'Skyler']
LAST = ['Alder', 'Birch', 'Cedar', 'Hawthorn', 'Juniper', 'Linden', 'Maple', 'Oakley',
        'Pine', 'Rowan', 'Spruce', 'Sycamore', 'Tamarack', 'Willow', 'Yew', 'Aspen']


@dataclass
class Student:
    first: str
    last: str
    id: str             # on the roster
    bubbled: str        # as filled on the sheet
    form: str
    font: str
    size: int
    pencil: int         # gray level of the writing, 0 black
    id_gray: int        # gray level of the ID bubbles


def load_font(name: str, size: int):
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size=size)


def misspell(rng: random.Random, word: str) -> str:
    '''One slip of the kind students make: a dropped, doubled, or swapped letter.'''
    letters = [i for i, c in enumerate(word) if c.isalpha()]
    if len(letters) < 4:
        return word + word[-1]
    i = rng.choice(letters[1:-1])
    kind = rng.choice(['drop', 'double', 'swap', 'vowel'])
    if kind == 'drop':
        return word[:i] + word[i + 1:]
    if kind == 'double':
        return word[:i] + word[i] + word[i:]
    if kind == 'swap' and i + 1 < len(word):
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    vowels = 'aeiou'
    if word[i] in vowels:
        return word[:i] + rng.choice(vowels.replace(word[i], '')) + word[i + 1:]
    return word[:i] + word[i + 1:]


def choose_answer(rng, q: practical.Question, others: list[str]) -> tuple[str, str]:
    '''(text, why): what a student writes for q.'''
    r = rng.random()
    if r < 0.06:
        return '', 'blank'
    if r < 0.16:
        return rng.choice(others), 'wrong'
    if r < 0.24 and q.partial:
        return rng.choice(q.partial), 'partial'
    if r < 0.36:
        return misspell(rng, rng.choice(q.full)), 'misspelled'
    text = rng.choice(q.full)
    return (text.lower() if rng.random() < 0.8 else text), 'full'


class Pen:
    '''Handwriting on a page image at scan resolution.'''

    def __init__(self, img: Image.Image, rng: random.Random, s: Student):
        self.img, self.rng, self.s = img, rng, s
        self.ink = Image.new('L', img.size, 0)          # coverage, 255 = full
        self.draw = ImageDraw.Draw(self.ink)
        self.font = load_font(s.font, s.size)

    def write(self, x: float, y: float, text: str) -> float:
        '''Write text with its left end at canonical (x, y middle); return end x (canonical).'''
        px, py = x * K, y * K
        drift = self.rng.uniform(-0.04, 0.04)            # a line that climbs or sags
        x0 = px
        for ch in text:
            jitter = self.rng.uniform(-1.5, 1.5)
            self.draw.text((px, py + (px - x0) * drift + jitter), ch, fill=235,
                           font=self.font, anchor='lm')
            px += self.font.getlength(ch) * self.rng.uniform(0.95, 1.08)
        return px / K

    def strike(self, x0: float, x1: float, y: float):
        self.draw.line((x0 * K, y * K, x1 * K, (y - 3) * K), fill=235, width=3)

    def bubble(self, cx: float, cy: float, coverage: int):
        r = 9.5 * K
        pts = []
        for a in np.linspace(0, 2 * np.pi, 18, endpoint=False):
            rr = r * self.rng.uniform(0.85, 1.1)
            pts.append((cx * K + rr * np.cos(a), cy * K + rr * np.sin(a)))
        self.draw.polygon(pts, fill=coverage)

    def finish(self) -> Image.Image:
        '''Lay the pencil down: darken the page toward the pencil gray by coverage.'''
        page = np.asarray(self.img, np.float32)
        cov = np.asarray(self.ink.filter(ImageFilter.GaussianBlur(0.7)), np.float32)[..., None] / 255
        out = page * (1 - cov) + self.s.pencil * cov
        return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def fill_page(page_img, n, s, p, boxes, rng, answers):
    pen = Pen(page_img, rng, s)
    name = f'{s.first} {s.last}'
    if n == 1:
        pen.write(480, 88, name)
        top = L.V2_ID_TOP
        for c, (want, bub) in enumerate(zip(s.id, s.bubbled)):
            cx = L.V2_ID_X + L.V2_ID_COL * c
            pen.write(cx - 8, top - 50, want)            # the boxes show what they meant
            for lab, bx, by in L.V2.id_digits[f'ID{c + 1:02d}']:
                if lab == bub:
                    pen.bubble(bx, by, 255 if s.id_gray < 150 else 170)
    else:
        pen.write(70, 82, name)
    for (station, slot), (page, (x0, y0, x1, y1)) in boxes.items():
        if page != n:
            continue
        key = f'{station}{s.form[slot]}'
        text, why = answers[key]
        if not text:
            continue
        y = (y0 + y1) / 2 + rng.uniform(-6, 6)
        x = x0 + rng.uniform(8, 30)
        if why == 'crossed out':
            first, final = text.split(' -> ')
            end = pen.write(x, y, first)
            pen.strike(x - 2, end + 2, y)
            pen.write(end + 14, y, final)
        elif why == 'note outside box':
            pen.write(x, y, text)
            pen.write(x1 + 4 if slot == 0 else x0 - 8, y1 + 8, '?')
        else:
            pen.write(x, y, text)
    return pen.finish()


def scan(img: Image.Image, rng: random.Random) -> Image.Image:
    '''Feed a filled page through a copier: skew, offset, scale, blur, speckle, tone.'''
    w, h = img.size
    angle = rng.uniform(-1.2, 1.2)
    scale = rng.uniform(0.985, 1.015)
    dx, dy = rng.uniform(-18, 18), rng.uniform(-18, 18)
    paper = rng.randint(238, 250)
    out = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(paper,) * 3)
    out = out.resize((int(w * scale), int(h * scale)), Image.BICUBIC)
    canvas = Image.new('RGB', (w, h), (paper,) * 3)
    canvas.paste(out, (int(dx - (out.width - w) / 2), int(dy - (out.height - h) / 2)))
    arr = np.asarray(canvas.filter(ImageFilter.GaussianBlur(0.6)), np.float32)
    arr = arr * (paper / 255) + np.random.default_rng(rng.randint(0, 2**31)).normal(0, 4, arr.shape)
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def make_students(rng, p, n) -> list[Student]:
    firsts, lasts = rng.sample(FIRST, n), rng.sample(LAST, n)
    students = []
    for i in range(n):
        sid = f'0099{rng.randint(0, 9999):04d}'
        students.append(Student(firsts[i], lasts[i], sid, sid, p.forms[i % len(p.forms)],
                                HANDS[i % len(HANDS)], rng.randint(34, 42),
                                rng.randint(40, 95), 70))
    # Edge cases: one very light pencil, one ID bubbled a digit off the roster
    if n > 1:
        students[1].pencil, students[1].id_gray = 150, 185
    if n > 4:
        b = list(students[4].bubbled)
        b[6] = str((int(b[6]) + 1) % 10)
        students[4].bubbled = ''.join(b)
    return students


def make_answers(rng, p, s: Student, idx: int) -> dict[str, tuple[str, str]]:
    all_full = [q.full[0] for q in p.questions() if q.full]
    answers = {}
    for q in p.questions():
        if q.letter not in s.form:
            continue
        others = [a for a in all_full if a.lower() not in (f.lower() for f in q.full)]
        answers[q.key] = choose_answer(rng, q, others)
    keys = list(answers)
    # A few fixed edge cases, spread across students
    if idx == 0:
        k = keys[2]
        wrong = rng.choice([a for a in all_full if a not in p.question(k).full])
        answers[k] = (f'{wrong} -> {p.question(k).full[0].lower()}', 'crossed out')
    if idx == 2:
        k = keys[5]
        answers[k] = (f'{p.question(k).full[0].lower()} which is the one near the top',
                      'runs past box')
    if idx == 3:
        k = keys[7]
        answers[k] = (p.question(k).full[0].lower(), 'note outside box')
    return answers


def make_stack(source: Path, outdir: Path, n_students: int = 12, seed: int = 207) -> Path:
    '''Write the stack and its truth files to outdir; return the scans PDF path.'''
    rng = random.Random(seed)
    p = practical.load(source)
    outdir.mkdir(parents=True, exist_ok=True)
    boxes = L.practical_boxes(len(p.stations))
    sheets = {f: fitz.open(stream=answer_sheet.build_practical_sheet(len(p.stations), f, p.title),
                           filetype='pdf') for f in p.forms}
    students = make_students(rng, p, n_students)

    pdf = fitz.open()
    answer_rows = []
    for idx, s in enumerate(students):
        answers = make_answers(rng, p, s, idx)
        for key, (text, why) in answers.items():
            answer_rows.append([idx + 1, s.form, key, text, why])
        for n, page in enumerate(sheets[s.form], 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), colorspace=fitz.csRGB)
            img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            img = scan(fill_page(img, n, s, p, boxes, rng, answers), rng)
            buf = io.BytesIO()
            img.save(buf, 'JPEG', quality=80)
            out = pdf.new_page(width=612, height=792)
            out.insert_image(out.rect, stream=buf.getvalue())
    pdf.save(outdir / 'scans.pdf', garbage=4, deflate=True)

    with open(outdir / 'roster.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['LastName', 'FirstName', 'ID'])
        for s in sorted(students, key=lambda s: s.last):
            w.writerow([s.last, s.first, f'L{s.id}'])
    with open(outdir / 'students.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['student', 'form', 'first', 'last', 'roster_id', 'bubbled_id', 'font',
                    'pencil_gray', 'id_gray'])
        for i, s in enumerate(students, 1):
            w.writerow([i, s.form, s.first, s.last, s.id, s.bubbled, s.font, s.pencil,
                        s.id_gray])
    with open(outdir / 'answers.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['student', 'form', 'question', 'written', 'why'])
        w.writerows(answer_rows)
    return outdir / 'scans.pdf'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('source', type=Path, help='the practical .md file')
    ap.add_argument('-o', '--outdir', type=Path,
                    help='output folder (default: generated/ beside the source)')
    ap.add_argument('-n', '--students', type=int, default=12)
    ap.add_argument('--seed', type=int, default=207)
    args = ap.parse_args()
    outdir = args.outdir or args.source.parent / 'generated'
    scans = make_stack(args.source, outdir, args.students, args.seed)
    print(f'Wrote {args.students} students to {scans}, with roster.csv, students.csv, '
          f'and answers.csv beside it.')


if __name__ == '__main__':
    main()
