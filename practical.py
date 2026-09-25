'''
Lab practicals: one markdown source file per practical, which is also its key.

A practical has numbered stations, each with written questions A to D. Each
student answers the same subset of letters (a form, such as AC) at every
station. The source file holds every question and its accepted answers, so
one key grades every form; answers added while grading are written back into
it by sync_answers, leaving the rest of the file as the instructor wrote it.

    ---
    title: BIOL 207 Lab Practical 3
    forms: AB, CD, AC, BD, AD, BC
    points: 1
    ---

    # Station 1: kidney model
    setup: Kidney model, frontal section. Pins A to D.
    image: images/kidney.png

    A. Name the structure at pin A.
    = renal pelvis
    ~ pelvis

The design and its reasoning are in docs/dev/lab-practicals.md.

    uv run python practical.py exam.md          # check a file and summarize it
'''
import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

LETTERS = 'ABCD'
# The order forms are dealt in when none are given: each pair is followed by
# its complement, so neighbors in a stack share no question.
DEFAULT_FORMS = ['AB', 'CD', 'AC', 'BD', 'AD', 'BC']

STATION_RE = re.compile(r'^#{1,6}\s*station\s+(\d+)\b\s*[:.\-]?\s*(.*)$', re.IGNORECASE)
QUESTION_RE = re.compile(r'^([A-D])[.)](?:\s+(.*))?$')
POINTS_RE = re.compile(r'^\(\s*(\d+(?:\.\d+)?)\s*(?:pts?|points?)?\s*\)$', re.IGNORECASE)
FIELD_RE = re.compile(r'^(setup|image)\s*:\s*(.*)$', re.IGNORECASE)
COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


class PracticalError(ValueError):
    '''A source file that cannot be used; the message is shown to the user.'''


@dataclass
class Question:
    station: int
    letter: str
    text: str = ''
    full: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    points: float | None = None
    images: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f'{self.station}{self.letter}'


@dataclass
class Station:
    number: int
    name: str = ''
    setup: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    questions: dict[str, Question] = field(default_factory=dict)


@dataclass
class Practical:
    title: str
    forms: list[str]
    points: float
    stations: list[Station]
    path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def letters(self) -> str:
        '''Every letter some form uses, in order.'''
        return ''.join(c for c in LETTERS if any(c in f for f in self.forms))

    def questions(self) -> list[Question]:
        '''Station by station, A to D within each: the grading order.'''
        return [s.questions[c] for s in self.stations for c in LETTERS if c in s.questions]

    def question(self, key: str) -> Question:
        m = re.fullmatch(r'(?:openQ_)?(\d+)([A-D])', key.strip())
        if not m or not 1 <= int(m.group(1)) <= len(self.stations):
            raise KeyError(key)
        return self.stations[int(m.group(1)) - 1].questions[m.group(2)]

    def keys_for_form(self, form: str) -> list[str]:
        '''The questions a student with this form answers, in grading order.'''
        return [q.key for q in self.questions() if q.letter in form]

    def points_for(self, q: Question) -> float:
        return q.points if q.points is not None else self.points

    def total_points(self, form: str) -> float:
        return sum(self.points_for(q) for q in self.questions() if q.letter in form)


# ── Reading ────────────────────────────────────────────────────────────────

def _blank_comments(text: str) -> str:
    '''Drop <!-- --> comments but keep their newlines, so line numbers hold.'''
    return COMMENT_RE.sub(lambda m: '\n' * m.group(0).count('\n'), text)


def _split_answers(value: str) -> list[str]:
    return [a.strip() for a in value.split('|') if a.strip()]


def _front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    '''
    Parse a leading --- block of key: value lines; return it and the next
    line index. Blank lines before it (where a comment was) are allowed.
    '''
    first = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    if first == len(lines) or lines[first].strip() != '---':
        return {}, 0
    meta = {}
    for i in range(first + 1, len(lines)):
        line = lines[i].strip()
        if line == '---':
            return meta, i + 1
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip().lower()] = v.strip()
    raise PracticalError('The front matter at the top of the file opens with --- but never '
                         'closes; add a --- line after its last setting.')


def _parse_forms(value: str, errors: list[str]) -> list[str]:
    if not value:
        return list(DEFAULT_FORMS)
    forms = []
    for raw in re.split(r'[,\s]+', value.strip()):
        f = raw.strip().upper()
        if not f:
            continue
        if len(f) != 2 or any(c not in LETTERS for c in f) or f[0] == f[1]:
            errors.append(f'forms: "{raw}" is not a pair of different letters from A to D.')
            continue
        f = ''.join(sorted(f))
        if f in forms:
            errors.append(f'forms: {f} is listed twice.')
            continue
        forms.append(f)
    if not forms and not errors:
        errors.append('forms: no forms are listed.')
    return forms


def parse(text: str, path: Path | None = None) -> Practical:
    '''Read a practical from its source text. Raises PracticalError listing every problem.'''
    lines = _blank_comments(text.replace('\r\n', '\n')).split('\n')
    meta, start = _front_matter(lines)
    errors: list[str] = []
    warnings: list[str] = []

    title = meta.get('title') or (path.stem if path else 'Lab practical')
    forms = _parse_forms(meta.get('forms', ''), errors)
    try:
        points = float(meta.get('points') or 1)
    except ValueError:
        errors.append(f'points: "{meta["points"]}" is not a number.')
        points = 1.0

    stations: list[Station] = []
    station: Station | None = None
    question: Question | None = None
    for i in range(start, len(lines)):
        n = i + 1
        line = lines[i].strip()
        if not line:
            continue
        if m := STATION_RE.match(line):
            station = Station(int(m.group(1)), m.group(2).strip())
            stations.append(station)
            question = None
            continue
        if line.startswith('#'):
            continue                      # any other heading is the author's own
        if station is None:
            continue                      # text before the first station is ignored
        if m := QUESTION_RE.match(line):
            letter = m.group(1)
            if letter in station.questions:
                errors.append(f'Line {n}: station {station.number} has two questions {letter}.')
            question = Question(station.number, letter, (m.group(2) or '').strip())
            station.questions[letter] = question
            continue
        if line[0] in '=~':
            if question is None:
                errors.append(f'Line {n}: an answer line comes before any question at '
                              f'station {station.number}.')
                continue
            target = question.full if line[0] == '=' else question.partial
            for a in _split_answers(line[1:]):
                if a.lower() not in (x.lower() for x in target):
                    target.append(a)
            continue
        if m := FIELD_RE.match(line):
            name, value = m.group(1).lower(), m.group(2).strip()
            if not value:
                continue                  # an empty placeholder, as the key import writes
            if name == 'setup':
                if question is not None:
                    errors.append(f'Line {n}: setup lines belong under the station heading, '
                                  f'before question A.')
                else:
                    station.setup.append(value)
            elif question is not None:
                question.images.append(value)
            else:
                station.images.append(value)
            continue
        if m := POINTS_RE.match(line):
            if question is None:
                errors.append(f'Line {n}: a points line comes before any question at '
                              f'station {station.number}.')
            else:
                question.points = float(m.group(1))
            continue
        if question is not None:
            question.text = f'{question.text} {line}'.strip()
        else:
            errors.append(f'Line {n}: "{line[:40]}" sits between the station {station.number} '
                          f'heading and question A. Start it with "setup:" if it is a note '
                          f'for whoever sets up the station.')

    if not stations:
        raise PracticalError('No stations found. Each station starts with a heading line '
                             'such as "# Station 1".')

    numbers = [s.number for s in stations]
    if numbers != list(range(1, len(stations) + 1)):
        errors.append(f'Stations must be numbered 1 to {len(stations)} in order; '
                      f'the file has {", ".join(map(str, numbers))}.')

    used = ''.join(c for c in LETTERS if any(c in f for f in forms))
    for s in stations:
        missing = [c for c in used if c not in s.questions]
        if missing:
            errors.append(f'Station {s.number} has no question {", ".join(missing)}, '
                          f'which the forms use.')
        for q in s.questions.values():
            if not q.text and not q.images:
                warnings.append(f'{q.key} has no question text.')
            if not q.full:
                warnings.append(f'{q.key} has no full-credit answer.')

    if errors:
        raise PracticalError('\n'.join(errors))
    return Practical(title, forms, points, stations, path, warnings)


def load(path) -> Practical:
    path = Path(path)
    return parse(path.read_text(encoding='utf-8-sig'), path)


def is_practical(path) -> bool:
    '''True for a markdown file with at least one "# Station N" heading.'''
    path = Path(path)
    if path.suffix.lower() not in ('.md', '.txt'):
        return False
    try:
        text = path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError):
        return False
    return any(STATION_RE.match(line.strip()) for line in text.splitlines())


# ── The practical as a key ─────────────────────────────────────────────────

def to_key_data(p: Practical) -> dict:
    '''
    The dict keyformat.load_key_file returns, so the scanner and grading
    window can treat a practical like any key. Crop boxes are absent: they
    depend on each student's form and come from the sheet layout.
    '''
    open_qs, points = {}, {}
    for q in p.questions():
        qk = f'openQ_{q.key}'
        open_qs[qk] = {'full': list(q.full), 'partial': list(q.partial),
                       'coords': None, 'page': 1}
        points[qk] = p.points_for(q)
    return {
        'bubble_answers': {},
        'open_questions': open_qs,
        'point_values': points,
        'metadata': {'practical': 'yes', 'stations': str(len(p.stations)),
                     'forms': ','.join(p.forms), 'title': p.title},
    }


# ── Writing answers back ───────────────────────────────────────────────────

def _question_spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    '''
    {'1A': (first, end)}: the line range of each question block, from its
    question line to just before the next question or station heading.
    '''
    clean = _blank_comments('\n'.join(lines)).split('\n')
    _, start = _front_matter(clean)
    spans, station, current = {}, None, None
    for i in range(start, len(clean)):
        line = clean[i].strip()
        if m := STATION_RE.match(line):
            station, current = int(m.group(1)), None
        elif station is not None and (m := QUESTION_RE.match(line)):
            current = f'{station}{m.group(1)}'
            spans[current] = [i, i + 1]
            continue
        elif line.startswith('#'):
            current = None
        if current and line:
            spans[current][1] = i + 1
    return {k: (a, b) for k, (a, b) in spans.items()}


def sync_answers(path, answers: dict[str, dict]) -> int:
    '''
    Make the file's answers match `answers` ({'openQ_1A': {'full': [...],
    'partial': [...]}}), editing only answer lines: an answer no longer
    wanted is removed from its line (the line goes when it empties), and a
    new one is added on its own line after the question's last answer of
    that kind. Returns the number of answers added or removed.
    '''
    path = Path(path)
    raw = path.read_bytes().decode('utf-8-sig')    # bytes, so \r\n survives to be seen
    newline = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.replace('\r\n', '\n').split('\n')
    clean = _blank_comments('\n'.join(lines)).split('\n')
    changes = 0

    # Work from the bottom up so earlier spans keep their line numbers.
    spans = _question_spans(lines)
    for key in sorted(spans, key=lambda k: spans[k][0], reverse=True):
        want = answers.get(f'openQ_{key}') or answers.get(key)
        if want is None:
            continue
        first, end = spans[key]
        wanted = {'=': [a.strip() for a in want.get('full', []) if a.strip()],
                  '~': [a.strip() for a in want.get('partial', []) if a.strip()]}
        present = {'=': [], '~': []}
        last = {'=': None, '~': None}
        for i in range(first + 1, end):
            s = clean[i].strip()
            if not s or s[0] not in '=~':
                continue
            kind = s[0]
            had = _split_answers(s[1:])
            keep = [a for a in had
                    if a.lower() in (w.lower() for w in wanted[kind])
                    and a.lower() not in (p.lower() for p in present[kind])]
            present[kind] += keep
            if len(keep) == len(had):
                last[kind] = i
            elif keep:
                changes += len(had) - len(keep)
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines[i] = f'{indent}{kind} {" | ".join(keep)}'
                last[kind] = i
            else:
                changes += len(had)
                lines[i] = None           # removed below, after indices are used
        inserts = []
        for kind in '=~':
            new = [a for a in wanted[kind] if a.lower() not in (p.lower() for p in present[kind])]
            if not new:
                continue
            changes += len(new)
            after = last[kind]
            if after is None and kind == '~':
                after = last['=']
            if after is None:
                after = max((i for i in range(first, end) if lines[i] is not None
                             and lines[i].strip()), default=first)
            inserts.append((after, [f'{kind} {a}' for a in new]))
        for after, new_lines in sorted(inserts, reverse=True):
            lines[after + 1:after + 1] = new_lines
    if changes:
        text = newline.join(line for line in lines if line is not None)
        path.write_bytes(text.encode('utf-8'))
    return changes


# ── Command line ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Check a lab practical source file.')
    ap.add_argument('source', help='the practical .md file')
    args = ap.parse_args()
    try:
        p = load(args.source)
    except PracticalError as exc:
        raise SystemExit(f'Cannot use {args.source}:\n{exc}')
    print(f'{p.title}: {len(p.stations)} stations, forms {", ".join(p.forms)}')
    for f in p.forms:
        print(f'  {f}: {len(p.keys_for_form(f))} questions, {p.total_points(f):g} points')
    for w in p.warnings:
        print(f'  warning: {w}')


if __name__ == '__main__':
    main()
