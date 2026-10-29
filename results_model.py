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
    _di: dict = field(default_factory=dict, repr=False)

    @property
    def multi(self) -> bool:
        return len(self.graded) > 1

    def added(self, version: str) -> float:
        return outputs.adjustment(self.adjust, version)


def open_folder(outdir) -> Results:
    """The results in an ExamScanner_outputs folder, edits applied. Raises
    ValueError when it holds no graded students."""
    outdir = Path(outdir)
    graded = [g for g in (outputs.load(p) for p in outputs.listed(outdir)) if g.students]
    if not graded:
        raise ValueError(f'No graded results in {outdir}. Choose the ExamScanner_outputs '
                         'folder a scan wrote.')
    made = edits.load(outdir)
    applied, problems = edits.apply(graded, made)
    return Results(outdir, applied, made, problems, edits.adjustments(made),
                   outputs.item_table(applied), any(not g.settings for g in graded),
                   next((g.title for g in graded if g.title), ''))


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
                            st['r'] is not None and st['r'] < outputs.FLAG_BELOW))
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


def answers(res: Results, version: str, row: str) -> list[Answer]:
    g = next(g for g in res.graded if g.version == version)
    out = []
    for c in g.q_cols:
        if not _graded(g, c):
            continue
        asked = g.asked(row, c)
        key = 'written' if str(g.df.loc['0', c]) == 'CC' else g.key_label(c)
        out.append(Answer(c, _cell(g, row, c), key, g.earned(row, c) if asked else None,
                          g.possible.get(c)))
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
