"""
results_model.py

What the Results tab shows, computed from a scan's outputs folder with its
edits applied: summary statistics before and after the adjustments, the
grade distribution, a row per question and per student. No Tk here, so it
is tested without a display; results_tab.py draws it. The numbers come from
analysis.py, the same definitions the gradebook's formulas use.
docs/dev/results-tab.md has the design.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import analysis
import edits
import outputs


@dataclass
class Results:
    outdir: Path
    graded: list[outputs.Graded]        # with the edits applied
    edits: list[dict]
    problems: list[str]                 # edits that matched nothing
    adjust: dict                        # {version: points added}, '' the class
    items: outputs.ItemTable
    legacy: bool                        # scored before settings were recorded
    title: str = ''
    unexported: bool = False            # edits not yet in the gradebook and Canvas file
    _di: dict = field(default_factory=dict, repr=False)

    @property
    def multi(self) -> bool:
        return len(self.graded) > 1

    def added(self, version: str) -> float:
        return outputs.adjustment(self.adjust, version)


def open_folder(outdir) -> Results:
    """The results in an ExamScanner_outputs folder, edits applied. The
    folder holding it will do too. Raises ValueError, saying what it looked
    for, when it holds no graded students."""
    outdir = Path(outdir)
    if not (outdir / outputs.APP_DATA).is_dir() and (outdir / 'ExamScanner_outputs').is_dir():
        outdir = outdir / 'ExamScanner_outputs'
    graded = [g for g in (outputs.load(p) for p in outputs.listed(outdir)) if g.students]
    if not graded:
        raise ValueError(why_empty(outdir))
    made = edits.load(outdir)
    applied, problems = edits.apply(graded, made)
    return Results(outdir, applied, made, problems, edits.adjustments(made),
                   outputs.item_table(applied), any(not g.settings for g in graded),
                   next((g.title for g in graded if g.title), ''),
                   edits.unexported(outdir))


def why_empty(outdir: Path) -> str:
    """What a folder that opened with nothing is missing. The tab reads a
    scan's results files in app_data/, never the gradebook."""
    looked = ('app_data/results.csv, or one results_versionA.csv, results_versionB.csv… '
              'per version')
    choose = 'Choose the ExamScanner_outputs folder a scan wrote.'
    if not outdir.is_dir():
        return f'{outdir} is not a folder. {choose}'
    data = outdir / outputs.APP_DATA
    if not data.is_dir():
        return f'No results in {outdir}: it has no app_data folder, where a scan keeps {looked}. {choose}'
    try:
        named = json.loads((data / outputs.MANIFEST).read_text(encoding='utf-8'))['results']
    except (OSError, ValueError, KeyError, TypeError):
        named = []
    present = [p.name for p in outputs.listed(outdir)]
    if named and not present:
        msg = (f'No results in {outdir}: app_data/outputs.json names {", ".join(named)}, '
               'but none of them is in app_data. Were they moved or deleted?')
    elif present:
        msg = f'No graded students in {outdir}: {", ".join(present)} hold none.'
    else:
        msg = f'No results in {outdir}: looked for {looked}, and found none.'
    have = [n for n in (outputs.GRADEBOOK, outputs.CANVAS) if (outdir / n).exists()]
    if have:
        msg += (f' {" and ".join(have)} {"is" if len(have) == 1 else "are"} there, but the tab '
                'builds everything from the results files, not from those.')
    return msg


# ── Making edits ─────────────────────────────────────────────────────────────
# Each returns the folder's results opened again with the change saved.

def _same_target(a: dict, b: dict) -> bool:
    fields = ('source', 'version', 'question', 'row')
    return all(a.get(f) == b.get(f) for f in fields)


def add(res: Results, edit: dict) -> Results:
    """Save a new edit. It replaces any earlier edit it makes moot: a key or
    adjustment for the same target, an override of the same cell, a point
    value for the same question. Earlier edits that still count (also
    accept, full credit, drop) stay."""
    def moot(old: dict) -> bool:
        if old['type'] != edit['type'] or not _same_target(old, edit):
            return False
        if edit['type'] == 'key':
            return not edit.get('also')
        if edit['type'] == 'credit':
            return old.get('action') == edit.get('action')
        return True
    made = [e for e in res.edits if not moot(e)]
    if not (edit['type'] == 'adjust' and not edit.get('points')):
        made.append(edit)               # an adjustment of 0 only clears the earlier one
    edits.save(res.outdir, made)
    return open_folder(res.outdir)


def delete(res: Results, edit_ids) -> Results:
    ids = {edit_ids} if isinstance(edit_ids, str) else set(edit_ids)
    edits.save(res.outdir, [e for e in res.edits if e['id'] not in ids])
    return open_folder(res.outdir)


def set_note(res: Results, edit_id: str, note: str) -> Results:
    edits.save(res.outdir, [{**e, 'note': note} if e['id'] == edit_id else e
                            for e in res.edits])
    return open_folder(res.outdir)


def set_adjustments(res: Results, points: dict, note: str = '') -> Results:
    """{version: points added}, '' the class; only the changed ones are saved."""
    for version, pts in points.items():
        if float(pts) != res.adjust.get(version, 0):
            res = add(res, edits.make('adjust', note, version=version, points=float(pts)))
    return res


def parse_keys(text: str) -> list[str]:
    """Keys typed in the tab: 'C', or alternatives 'C, D' (also 'C or D').
    A select-all key is its letters together, 'AC'. Raises ValueError."""
    keys = []
    for part in re.split(r',|\bor\b', text, flags=re.IGNORECASE):
        part = re.sub(r'\s+', '', part).upper()
        if not part:
            continue
        if not re.fullmatch(r'[A-Z]+', part):
            raise ValueError(f'"{part}" is not a key: use letters, like C, or AC for '
                             'a select-all answer.')
        keys.append(''.join(sorted(set(part))))
    if not keys:
        raise ValueError('Type the key: a letter, like C.')
    return list(dict.fromkeys(keys))


def target(res: Results, q: Question) -> dict:
    """The fields that point an edit at a question: its bank question when
    the versions were matched by one, so it reaches every version."""
    if res.items.by_source:
        return {'source': q.label}
    version, col = q.cols[0]
    return {'version': version, 'question': col}


def key_edit(res: Results, q: Question, keys: list[str], also: bool, note: str = '') -> dict:
    """Keys in the bank's letters, as the Questions view shows them."""
    if q.written:
        raise ValueError('A written question is graded on the Re-grade tab.')
    where = target(res, q)
    if 'version' in where:
        g = _version(res, where['version'])
        keys = [g.sheet_letters(where['question'], k) for k in keys]
    return edits.make('key', note, **where, keys=keys, also=also)


def credit_edit(res: Results, q: Question, action: str, points: float | None = None,
                note: str = '') -> dict:
    assert action in ('full', 'drop', 'points'), action
    extra = {}
    if action == 'points':
        if points is None or points < 0:
            raise ValueError('Points must be a number, 0 or more.')
        extra['points'] = float(points)
    return edits.make('credit', note, **target(res, q), action=action, **extra)


def override_edit(res: Results, version: str, row: str, question: str, points: float,
                  note: str = '') -> dict:
    if points < 0:
        raise ValueError('Points must be 0 or more.')
    g = _version(res, version)
    return edits.make('override', note, version=version, row=row,
                      student_id=_cell(g, row, 'studentID'), question=question,
                      points=float(points))


def overrides_on(res: Results, q: Question) -> list[dict]:
    """The overrides on a question, which a key change leaves standing."""
    cols = set(q.cols)
    return [e for e in res.edits if e['type'] == 'override'
            and (e.get('version'), e.get('question')) in cols]


def _version(res: Results, version: str) -> outputs.Graded:
    return next(g for g in res.graded if g.version == version)


def describe(res: Results, e: dict) -> str:
    """One edit, as the Edits view lists it."""
    def where():
        if e.get('source'):
            return e['source']
        q = e.get('question', '')
        return f'Version {e["version"]} {q}' if e.get('version') else q
    if e['type'] == 'key':
        keys = ' or '.join(e.get('keys', []))
        return f'{where()}: also accept {keys}' if e.get('also') else f'{where()}: key changed to {keys}'
    if e['type'] == 'credit':
        return {'full': f'{where()}: full credit to everyone',
                'drop': f'{where()}: dropped',
                'points': f'{where()}: worth {_points(e.get("points", 0))}'
                }.get(e.get('action'), f'{where()}: {e.get("action")}')
    if e['type'] == 'override':
        g = next((g for g in res.graded if g.version == e.get('version', '')), None)
        row = str(e.get('row'))
        who = row
        if g is not None and row in g.df.index:
            last, first = _cell(g, row, 'LastName'), _cell(g, row, 'FirstName')
            who = f'{last}, {first}' if first else last
        return f'{who}, {where()}: {_points(e.get("points", 0))}'
    pts = float(e.get('points') or 0)
    whom = 'Everyone' if not e.get('version') else f'Version {e["version"]}'
    return f'{whom}: {"+" if pts >= 0 else "−"}{_points(abs(pts))}'


def _num(x) -> str:
    x = round(float(x), 2)
    return f'{int(x)}' if x.is_integer() else f'{x:g}'


def _points(x) -> str:
    return f'{_num(x)} point{"" if float(x) == 1 else "s"}'


# ── Summary ──────────────────────────────────────────────────────────────────

@dataclass
class Column:
    label: str                  # 'All students' or 'Version A'
    possible: float | None      # None when the versions' totals differ
    before: dict                # analysis.summary of the totals
    after: dict                 # and of the adjusted totals
    alpha: float | None


def _version_alpha(g: outputs.Graded) -> float | None:
    cols = [c for c, p in g.possible.items() if p > 0]
    items = [[g.earned(r, c) if g.asked(r, c) else None for r in g.students] for c in cols]
    return analysis.cronbach_alpha(items, [g.total(r) for r in g.students])


def _class_alpha(res: Results) -> float | None:
    """The whole class's alpha needs every version's questions matched,
    so it comes from the bank-question table, as the gradebook's does."""
    if not res.multi:
        return _version_alpha(res.graded[0])
    if not res.items.by_source:
        return None
    uids = [(g.version, r) for g in res.graded for r in g.students]
    items = []
    for it in res.items.items:
        got = {uid: earned for uid, _, earned, _ in it.responses}
        items.append([got.get(u) for u in uids])
    return analysis.cronbach_alpha(items, [res.items.totals[u] for u in uids])


def columns(res: Results) -> list[Column]:
    """The class, then each version when there are several."""
    def column(label, gs, alpha):
        totals = [g.total(r) for g in gs for r in g.students]
        adjusted = [g.total(r) + res.added(g.version) for g in gs for r in g.students]
        possibles = {g.points_possible() for g in gs}
        return Column(label, possibles.pop() if len(possibles) == 1 else None,
                      analysis.summary(totals), analysis.summary(adjusted), alpha)
    out = [column('All students', res.graded, _class_alpha(res))]
    if res.multi:
        out += [column(f'Version {g.version}', [g], _version_alpha(g)) for g in res.graded]
    return out


def grade_counts(res: Results) -> tuple[dict, dict]:
    """Students per band, unadjusted and adjusted, each student against
    their own version's points possible."""
    before, after = [], []
    for g in res.graded:
        for r in g.students:
            before.append((g.total(r), g.points_possible()))
            after.append((g.total(r) + res.added(g.version), g.points_possible()))
    return analysis.band_counts(before), analysis.band_counts(after)


# ── Questions ────────────────────────────────────────────────────────────────

@dataclass
class Question:
    label: str                  # the bank question, or the sheet's number
    where: str                  # where it sat on each version: 'A3, B17'
    text: str
    key: str
    points: float
    written: bool
    n: int
    mean: float | None          # fraction of its points earned on average
    r: float | None             # corrected item-total correlation
    di: float | None            # Canvas's discrimination index
    counts: dict                # {choice: students}, in the bank's letters
    flagged: bool
    cols: list = field(default_factory=list)     # [(version, column)] it sat at


def questions(res: Results) -> list[Question]:
    uids = list(res.items.totals)
    totals = [res.items.totals[u] for u in uids]
    out = []
    for it in res.items.items:
        st = outputs.item_stats(it, res.items.totals)
        got = {uid: earned for uid, _, earned, _ in it.responses}
        di = analysis.discrimination_index([got.get(u) for u in uids], totals, it.points)
        out.append(Question(it.label, ', '.join(it.where), it.text, it.key, it.points,
                            it.written, st['n'], st['mean'], st['r'], di,
                            _ordered(st['counts']),
                            st['r'] is not None and st['r'] < outputs.FLAG_BELOW,
                            list(it.cols)))
    return out


def _ordered(counts: dict) -> dict:
    """Choices A, B, C… in order, then Blank, then anything else."""
    letters = sorted(k for k in counts if re.fullmatch(r'[A-Z]', k))
    rest = sorted(k for k in counts if k not in letters and k != 'Blank')
    return {k: counts[k] for k in letters + rest + (['Blank'] if 'Blank' in counts else [])}


# ── Students ─────────────────────────────────────────────────────────────────

@dataclass
class Student:
    version: str
    row: str                    # the results row
    name: str                   # 'Last, First'
    student_id: str
    total: float
    adjusted: float
    possible: float


def _cell(g: outputs.Graded, r: str, c: str) -> str:
    if c not in g.df.columns or pd.isna(g.df.loc[r, c]):
        return ''
    return str(g.df.loc[r, c]).rstrip('-') if c in ('LastName', 'FirstName') else str(g.df.loc[r, c])


def students(res: Results) -> list[Student]:
    """Every student, sorted by name as in the Canvas file."""
    out = []
    for g in res.graded:
        for r in g.students:
            last, first = _cell(g, r, 'LastName'), _cell(g, r, 'FirstName')
            out.append(Student(g.version, r, f'{last}, {first}' if first else last,
                               _cell(g, r, 'studentID'), g.total(r),
                               g.total(r) + res.added(g.version), g.points_possible()))
    out.sort(key=lambda s: (s.name.lower(), s.student_id))
    return out


@dataclass
class Answer:
    question: str               # the column on the student's sheet
    answer: str
    key: str
    earned: float | None        # None for a question not on their form
    possible: float | None      # None for an ungraded or dropped question
    overridden: bool = False    # its points set by hand


def answers(res: Results, version: str, row: str) -> list[Answer]:
    g = _version(res, version)
    set_by_hand = {e.get('question') for e in res.edits if e['type'] == 'override'
                   and e.get('version') == version and str(e.get('row')) == row}
    out = []
    for c in g.q_cols:
        if not _graded(g, c):
            continue
        asked = g.asked(row, c)
        key = 'written' if str(g.df.loc['0', c]) == 'CC' else g.key_label(c)
        out.append(Answer(c, _cell(g, row, c), key, g.earned(row, c) if asked else None,
                          g.possible.get(c), c in set_by_hand and c not in g.dropped))
    return out


def _graded(g: outputs.Graded, col: str) -> bool:
    """A question the key grades, or one an edit dropped."""
    return col in g.possible or col in g.dropped


def marked_pages(res: Results, version: str, row: str) -> list[Path]:
    """The student's marked sheet pages. Their names end in the sheet's
    place in the stack, which a version's results do not record, so this
    matches on name and ID and can find two students' pages when both
    their names and IDs went unread."""
    g = next(g for g in res.graded if g.version == version)
    # As markSheets names them, an unread name included ('nan')
    base = '_'.join(re.sub(r'[^\w\-]', '_', str(g.df.loc[row, c] if c in g.df.columns else ''))
                    for c in ('LastName', 'FirstName', 'studentID'))
    return sorted((res.outdir / 'marked').glob(f'{base}_[0-9][0-9][0-9]*.jpg'))
