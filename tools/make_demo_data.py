'''
Build the invented data the instructional videos are filmed with: question
banks, exams already built, filled-in and scanned stacks, a practical, and a
class roster, one folder per clip under demo/film/.

Every name and ID is invented and every sheet is rendered, so nothing here
needs FERPA handling, and the folder can be shown on screen. Running it again
wipes demo/film/ and rebuilds the same exams and marks, which resets everything a take
changed (keys edited while grading, results, Results-tab edits).

    uv run python tools/make_demo_data.py

Build Exam shuffles, so an exam built on camera will not match the scans made
here. To grade the one you built, fill in a stack for it:

    uv run python tools/make_demo_data.py --refill demo/film/1_bubble_build/Exam_1

Each planted problem (light pencil, an erasure, a wrong version bubble, ...)
is listed by scan number in demo/film/cues.csv.
'''
import argparse
import csv
import io
import math
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import answer_sheet  # noqa: E402
import browser_pdf  # noqa: E402
import keyformat  # noqa: E402
import make_practical_test_stack as stack  # noqa: E402
import practical  # noqa: E402
import practical_build  # noqa: E402
import sheet_layout as L  # noqa: E402
from build_tab import build_folder, save_config, write_answer_sheets  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder, PoolConfig  # noqa: E402
from exam_key_writer import save_key  # noqa: E402
from renderer import ExamRenderer, safe_name  # noqa: E402

SOURCES = ROOT / 'demo' / 'sources'
FILM = ROOT / 'demo' / 'film'
COURSE = 'DEMO 101'
LETTERS = 'ABCDEF'
SCALE = answer_sheet.PRINT_SCALE      # built sheets are drawn shrunk about the center

FIRST = ['Jordan', 'Casey', 'Riley', 'Morgan', 'Avery', 'Quinn', 'Rowan', 'Emerson', 'Harper',
         'Sawyer', 'Finley', 'Reese', 'Dakota', 'Hayden', 'Parker', 'Skyler', 'Blake', 'Drew',
         'Ellis', 'Frankie', 'Greer', 'Indigo', 'Jules', 'Kendall']
LAST = ['Alder', 'Birch', 'Cedar', 'Hawthorn', 'Juniper', 'Linden', 'Maple', 'Oakley', 'Pine',
        'Redwood', 'Spruce', 'Sycamore', 'Tamarack', 'Willow', 'Yew', 'Aspen', 'Beech', 'Cypress',
        'Elm', 'Fir', 'Hazel', 'Larch', 'Poplar', 'Walnut']

# Positions in the class that carry a planted problem on the bubble exam
LIGHT, ERASER, ONE_OFF, STRANGER, BLANK_ROW, DOUBLE, NO_VERSION, WRONG_VERSION = 1, 2, 3, 4, 5, 6, 7, 8
CUES = {
    LIGHT: 'Very light pencil: LIGHT MARKS in ALERT.txt',
    ERASER: 'Three erased answers beside fresh ones: two ignored, one a CHECK MARK in ALERT.txt',
    ONE_OFF: 'ID bubbled one digit off the roster: corrected, ROSTER line in ALERT.txt',
    STRANGER: 'ID not on the roster: a "Who is scan N?" window shows the written name',
    BLANK_ROW: 'One row left blank: named in ALERT.txt',
    DOUBLE: 'Two bubbles on a single-answer question',
    NO_VERSION: 'No version bubble: a window asks which version',
    WRONG_VERSION: 'Took version A, bubbled B: very low score, fixed with Scored as version',
}

# What students write in each written box of the quiz, as (answer, how many of 14)
WRITTEN = {
    'deepest layer': [('stratum basale', 5), ('basal layer', 1), ('stratum basil', 2),
                      ('stratum germinativum', 3), ('stratum corneum', 1),
                      ('stratum basle', 1), ('', 1)],
    'filters blood': [('kidney', 9), ('kidneys', 3), ('nephron', 1), ('kidny', 1)],
    'neurotransmitter': [('acetylcholine', 6), ('ACh', 4), ('acetylcoline', 2),
                         ('dopamine', 1), ('', 1)],
    'breaks down': [('osteoclast', 8), ('osteoclasts', 2), ('osteoblast', 2),
                    ('osteoclasst', 1), ('', 1)],
}


@dataclass
class Taker(stack.Student):
    ability: float = 1.0
    version: str = ''
    bubbled_version: str = ''
    note: str = ''
    marks: dict = field(default_factory=dict)


def make_class(rng: random.Random) -> list[Taker]:
    ids = rng.sample(range(10000), len(FIRST))
    takers = []
    for i, (first, last, n) in enumerate(zip(FIRST, LAST, ids)):
        sid = f'0099{n:04d}'
        takers.append(Taker(first, last, sid, sid, '', stack.HANDS[i % len(stack.HANDS)],
                            rng.randint(34, 42), rng.randint(40, 95), 70,
                            ability=rng.gauss(1.5, 0.9)))
    return takers


def write_roster(takers: list[Taker], path: Path):
    '''A class roster in the shape of a Canvas gradebook export.'''
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section', 'Assignment 1'])
        w.writerow(['    Points Possible', '', '', '', '', '100'])
        for n, t in enumerate(sorted(takers, key=lambda t: t.last)):
            w.writerow([f'{t.last}, {t.first}', 90000 + n, f'L{t.id}',
                        f'{t.first[0].lower()}{t.last.lower()}', COURSE, ''])
        w.writerow(['Student, Test', '99999', '', '', COURSE, ''])


def key_rows(path: Path) -> list[dict]:
    '''The graded bubble rows of a key, each with what its sheet printed.'''
    data = keyformat.load_key_file(str(path))
    rows = []
    for q, ans in data['bubble_answers'].items():
        if ans == 'ignore':
            continue
        rows.append({'q': q, 'answer': ans, 'choices': data['choices'].get(q) or 'ABCD',
                     'source': (data['sources'].get(q) or q).split('.')[0],
                     'text': data['texts'].get(q) or '',
                     'options': data['options'].get(q) or []})
    return rows


def letter_of(row: dict, option: str) -> str:
    '''The sheet letter a bank option was printed under.'''
    bank = LETTERS[row['options'].index(option)]
    return LETTERS[row['choices'].index(bank)]


def choose_marks(row: dict, t: Taker, rng: random.Random, hardness: dict) -> str:
    '''The letters a student bubbles on one row, from ability and how hard it is.'''
    n = len(row['choices'])
    key = row['answer']
    hard = hardness.setdefault(row['source'], rng.uniform(-1.8, 0.7))
    p = 1 / (1 + math.exp(-(t.ability - hard) * 1.6))
    others = [c for c in LETTERS[:n] if c not in key]

    if row['text'].startswith('The arrector pili'):    # miskeyed: the strong know better
        truth = letter_of(row, 'smooth muscle')
        if rng.random() < 1 / (1 + math.exp(-(t.ability - 1.5) * 2.5)):
            return truth
        return key if rng.random() < 0.8 else rng.choice([c for c in others if c != truth] or [key])
    if row['text'].startswith('What is the main function of eccrine') and t.ability > 1.3:
        if rng.random() < 0.45:                        # defensible: strong students take it
            return letter_of(row, 'excreting wastes')

    if len(key) > 1 or key == 'none':                  # select all that apply
        chosen = [c for c in LETTERS[:n] if (rng.random() < p if c in key else rng.random() > p + 0.2)]
        return ''.join(chosen) or key[0]
    if rng.random() < p or not others:
        return key
    weights = [3 if i == hash_pick(row['source'], len(others)) else 1 for i in range(len(others))]
    return rng.choices(others, weights)[0]


def hash_pick(text: str, n: int) -> int:
    '''A fixed choice of the distractor that fools people, the same on every version.'''
    return sum(map(ord, text)) % n


def render_blank(pdf_path: Path) -> list[Image.Image]:
    pages = []
    for page in fitz.open(pdf_path):
        pix = page.get_pixmap(matrix=fitz.Matrix(stack.DPI / 72, stack.DPI / 72),
                              colorspace=fitz.csRGB)
        pages.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
    return pages


def fill_sheet(blank: Image.Image, layout: L.Layout, t: Taker, marks: dict, written: dict,
               rng: random.Random, version: str = '', erasures: dict | None = None) -> Image.Image:
    '''One student's completed page. marks: {Qnnn: letters}; written: {(x0,y0,x1,y1): text}.'''
    pen = stack.Pen(blank.copy(), rng, t, SCALE)
    strength = 255 if t.id_gray < 150 else 170
    pen.write(480, 88, f'{t.first} {t.last}' if t.first != 'KEY' else 'KEY')

    if t.bubbled:
        rows = L.v2_id_rows(len(t.bubbled))
        for c, (want, bub) in enumerate(zip(t.id, t.bubbled)):
            pen.write(L.v2_id_x(len(t.bubbled)) + L.V2_ID_COL * c - 8, L.V2_ID_TOP - 50, want)
            for lab, bx, by in rows[f'ID{c + 1:02d}']:
                if lab == bub:
                    pen.bubble(bx, by, strength)
    if version:
        for lab, bx, by in layout.version['V']:
            if lab == version:
                pen.bubble(bx, by, strength)
    for q, letters in marks.items():
        for lab, bx, by in layout.questions[q]:
            if lab in letters:
                pen.bubble(bx, by, strength)
            elif erasures and erasures.get(q, ('', 0))[0] == lab:
                pen.bubble(bx, by, erasures[q][1])
    for (x0, y0, x1, y1), text in written.items():
        if text:
            pen.write(x0 + rng.uniform(10, 30), (y0 + y1) / 2 + rng.uniform(-5, 5), text)
    return stack.scan(pen.finish(), rng)


def save_stack(pages: list[Image.Image], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open()
    for img in pages:
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=80)
        pdf.new_page(width=612, height=792).insert_image(fitz.Rect(0, 0, 612, 792),
                                                         stream=buf.getvalue())
    pdf.save(path, garbage=4, deflate=True)


def layout_for(key: Path) -> L.Layout:
    meta = keyformat.load_key_file(str(key))['metadata']
    return L.keyed_layout(L.parse_columns(meta['sheet_rows'])) if meta.get('sheet_rows') else L.V2


def build_exam(config: BuildConfig, parent: Path, require=()):
    '''Build as the Build Exam tab does; redraw the sample until `require` stems are in it.'''
    folder = build_folder(str(parent), config.title)
    folder.mkdir(parents=True, exist_ok=True)
    for seed in range(500):
        random.seed(seed)
        versions, warnings = ExamBuilder().build(config)
        stems = ' '.join(q.text for q in versions[0].questions)
        if all(r in stems for r in require):
            break
    else:
        raise SystemExit(f'No sample of {config.title} held {require}')
    if warnings:
        print('  build warnings:', warnings)
    crops, _ = write_answer_sheets(versions, folder, f'{config.course} {config.title}')
    renderer, html = ExamRenderer(), []
    stem = safe_name(config.title)
    keys = {}
    for v in versions:
        path, _ = renderer.to_html(v, folder, len(versions), config.default_points, config.font_size)
        html.append(path)
        renderer.to_markdown(v, folder)
        keys[v.version_letter] = folder / f'{stem}_v{v.version_letter}_key.csv'
        save_key(v, keys[v.version_letter], config.default_points,
                 open_coords=crops.get(v.version_letter))
    browser_pdf.print_all(html)
    save_config(config, parent, folder / f'{stem}.exam.json', versions)
    return folder, keys


def sheet_for(folder: Path, stem: str, letter: str) -> Path:
    own = folder / f'{stem}_v{letter}_answer_sheet.pdf'
    return own if own.exists() else folder / f'{stem}_answer_sheet.pdf'


def fill_bubble_exam(folder: Path, takers: list[Taker], out: Path, seed: int = 101) -> list:
    '''A mixed stack for a built exam. Returns cue rows: (scan, student, note).'''
    rng = random.Random(seed)
    keys = {p.name.split('_v')[-1][0]: p for p in sorted(folder.glob('*_v?_key.csv'))}
    stem = next(iter(keys.values())).name.split('_v')[0]
    letters = sorted(keys)
    rows = {v: key_rows(p) for v, p in keys.items()}
    layouts = {v: layout_for(p) for v, p in keys.items()}
    blanks = {v: render_blank(sheet_for(folder, stem, v))[0] for v in keys}
    hardness: dict = {}
    pages, cues = [], []
    for scan_no, t in enumerate(takers, 1):
        took = letters[(scan_no - 1) % len(letters)]
        bubbled = took if len(letters) > 1 else ''
        erasures, marks = {}, {r['q']: choose_marks(r, t, rng, hardness) for r in rows[took]}
        i = scan_no - 1
        if i == LIGHT:
            t.pencil, t.id_gray = 150, 185
        if i == ERASER:
            singles = [r for r in rows[took] if len(r['answer']) == 1]
            for r, cover in zip(rng.sample(singles, 3), (60, 60, 125)):     # the 125 is ambiguous
                erasures[r['q']] = (rng.choice([c for c in LETTERS[:len(r['choices'])]
                                                if c not in marks[r['q']]]), cover)
        if i == ONE_OFF:
            b = list(t.bubbled)
            b[6] = str((int(b[6]) + 1) % 10)
            t.bubbled = ''.join(b)
        if i == STRANGER:
            t.bubbled = '55' + t.id[2:]                # far from every roster ID
        if i == BLANK_ROW:
            marks[rows[took][4]['q']] = ''
        if i == DOUBLE:
            r = next(r for r in rows[took] if len(r['answer']) == 1 and len(r['choices']) >= 4)
            marks[r['q']] = r['answer'] + next(c for c in 'ABCD' if c != r['answer'])
        if len(letters) > 1 and i == NO_VERSION:
            bubbled = ''
        if len(letters) > 1 and i == WRONG_VERSION:
            took, bubbled, t.ability = 'A', 'B', 3.0     # strong, so the fix is obvious
            marks = {r['q']: choose_marks(r, t, rng, hardness) for r in rows['A']}
        pages.append(fill_sheet(blanks[took], layouts[took], t, marks, {}, rng, bubbled, erasures))
        cues.append((scan_no, f'{t.last}, {t.first}', f'version {took}', CUES.get(i, '')))
    save_stack(pages, out)
    return cues


def fill_written_quiz(folder: Path, takers: list[Taker], out: Path, seed: int = 202) -> list:
    rng = random.Random(seed)
    key = next(folder.glob('*_vA_key.csv'))
    rows, layout = key_rows(key), layout_for(key)
    data = keyformat.load_key_file(str(key))
    stem = key.name.split('_v')[0]
    blank = render_blank(sheet_for(folder, stem, 'A'))[0]
    hardness: dict = {}
    answers = {}
    for phrase, spread in WRITTEN.items():
        pool = [a for a, n in spread for _ in range(n)]
        rng.shuffle(pool)
        answers[phrase] = pool
    boxes = {}
    for oq, v in data['open_questions'].items():
        phrase = next(p for p in WRITTEN if p in data['texts'].get(oq, '') or p in v.get('text', ''))
        boxes[tuple(v['coords'])] = phrase
    pages, cues = [], []
    for i, t in enumerate(takers):
        marks = {r['q']: choose_marks(r, t, rng, hardness) for r in rows}
        written = {c: answers[p][i] for c, p in boxes.items()}
        pages.append(fill_sheet(blank, layout, t, marks, written, rng))
        cues.append((i + 1, f'{t.last}, {t.first}', '; '.join(w or '(blank)' for w in written.values()), ''))
    save_stack(pages, out)
    return cues


def make_standard_sheet(folder: Path, takers: list[Taker], seed: int = 303) -> list:
    '''An exam "made somewhere else": a blank sheet, a filled key, and a stack.'''
    rng = random.Random(seed)
    folder.mkdir(parents=True)
    res = answer_sheet.build_sheet(20, title=f'{COURSE} Quiz from elsewhere')
    sheet = folder / 'blank_answer_sheet.pdf'
    sheet.write_bytes(res.pdf)
    blank = render_blank(sheet)[0]
    n_opts = {i: rng.choice([2, 4, 4, 5]) for i in range(1, 21)}
    rows = [{'q': f'Q{i:03d}', 'answer': rng.choice(LETTERS[:n_opts[i]]),
             'choices': LETTERS[:n_opts[i]], 'source': f'q{i}', 'text': '', 'options': []}
            for i in range(1, 21)]
    keysheet = Taker('KEY', '', '', '', '', 'Bradley Hand Bold.ttf', 38, 40, 70)
    key_page = fill_sheet(blank, L.V2, keysheet, {r['q']: r['answer'] for r in rows}, {}, rng)
    hardness: dict = {}
    stacks = [fill_sheet(blank, L.V2, t, {r['q']: choose_marks(r, t, rng, hardness) for r in rows},
                         {}, rng) for t in takers]
    save_stack([key_page], folder / 'key_scan' / 'filled_key_sheet.pdf')
    save_stack([key_page] + stacks, folder / 'key_first' / 'stack_with_key_first.pdf')
    save_stack(stacks, folder / 'with_key_file' / 'students_only.pdf')
    return [(i + 1, f'{t.last}, {t.first}', '', '') for i, t in enumerate(takers)]


def draw_figure(path: Path):
    '''A labeled schematic for the bank's image question.'''
    img = Image.new('RGB', (640, 340), 'white')
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=24)
    bands = [(30, 70, '#e8c9a8', 'A'), (70, 190, '#f2b8a8', 'B'), (190, 270, '#f7e39c', 'C'),
             (270, 320, '#c97a70', 'D')]
    for y0, y1, color, label in bands:
        d.rectangle((60, y0, 480, y1), fill=color, outline='black', width=2)
        y = (y0 + y1) / 2
        d.line((480, y, 540, y), fill='black', width=2)
        d.text((550, y), label, fill='black', font=font, anchor='lm')
    d.text((60, 6), 'Schematic of skin in section (not to scale)', fill='black', font=font)
    img.save(path)


def write_cues(all_cues: dict):
    with open(FILM / 'cues.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['clip', 'scan', 'student', 'detail', 'planted problem'])
        for clip, cues in all_cues.items():
            for row in cues:
                w.writerow([clip, *row])


def build_all():
    shutil.rmtree(FILM, ignore_errors=True)
    FILM.mkdir(parents=True)
    rng = random.Random(2026)
    takers = make_class(rng)
    write_roster([t for i, t in enumerate(takers) if i != STRANGER], FILM / 'class_roster.csv')
    cues = {}

    print('Bubble exam: sources and build...')
    src = FILM / '1_bubble_build'
    shutil.copytree(SOURCES / 'bubble', src)
    draw_figure(src / 'skin_layers.png')
    shutil.copy(ROOT / 'tests/fixtures/qti_import/all_types_export.zip', src / 'canvas_quiz_export.zip')

    grade = FILM / '2_bubble_grade'
    grade.mkdir()
    config = BuildConfig(title='Exam 1', course=COURSE, num_versions=2, shuffle_questions=True,
                         shuffle_answers=True, same_questions=True,
                         pools=[PoolConfig(src / 'skin.md', 12), PoolConfig(src / 'skeleton.md', 8)])
    folder, _ = build_exam(config, grade, require=('arrector pili', 'eccrine'))
    cues['2_bubble_grade'] = fill_bubble_exam(folder, takers, grade / 'scans' / 'Exam_1_scans.pdf')

    print('Written quiz...')
    written = FILM / '3_written'
    written.mkdir()
    shutil.copy(SOURCES / 'written' / 'quiz.md', written / 'quiz.md')
    config = BuildConfig(title='Quiz 2', course=COURSE, num_versions=1, shuffle_questions=False,
                         shuffle_answers=False, exact_file=written / 'quiz.md', default_points=1.0)
    folder, _ = build_exam(config, written)
    cues['3_written'] = fill_written_quiz(folder, takers[10:], written / 'scans' / 'Quiz_2_scans.pdf')

    print('Lab practical...')
    prac = FILM / '4_practical'
    (prac / 'images').mkdir(parents=True)
    shutil.copy(SOURCES / 'practical' / 'Demo_Practical.md', prac)
    shutil.copy(ROOT / 'tests/fixtures/practical/images/station1.png', prac / 'images')
    source = prac / 'Demo_Practical.md'
    built = practical.load(source)
    practical_build.build(built, practical_build.default_outdir(built), students=10)
    scans = prac / 'scans'
    stack.make_stack(source, scans, n_students=10, seed=207, print_scale=SCALE)
    shutil.move(scans / 'roster.csv', prac / 'practical_roster.csv')
    (prac / 'truth').mkdir()
    for name in ('students.csv', 'answers.csv'):
        shutil.move(scans / name, prac / 'truth' / name)

    print('Standard sheet...')
    cues['5_standard_sheet'] = make_standard_sheet(FILM / '5_standard_sheet', takers[12:])
    write_cues(cues)
    print(f'Done: {FILM}')


def refill(folder: Path):
    '''A stack for an exam built on camera, using the same invented class.'''
    takers = make_class(random.Random(2026))
    out = folder.parent / f'{folder.name}_scans' / f'{safe_name(folder.name)}_scans.pdf'
    cues = fill_bubble_exam(folder, takers, out)
    print(f'Wrote {len(cues)} sheets to {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--refill', type=Path, help='a build folder to fill in a stack for')
    args = ap.parse_args()
    if args.refill:
        refill(args.refill)
    else:
        build_all()


if __name__ == '__main__':
    main()
