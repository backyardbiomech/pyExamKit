"""
edits.py

The instructor's decisions after grading, kept apart from what the scanner
read: app_data/edits.json, an ordered list the Results tab adds to and
deletes from. apply() turns graded results into results with every edit
in, and outputs.write() builds the gradebook and Canvas file from those, so
deleting an edit undoes it. docs/dev/results-tab.md has the design.

Each edit is a dict with an id, a type, an optional note, and the time it
was made. The types, applied in this order:

  key       version and question, keys [str] in the sheet's letters; or
            source (a bank question, on every version that printed it),
            keys in the bank's letters. also (bool): grade the question
            against keys, or against its own key and keys when also is set
  credit    source (a bank question, on every version that printed it) or
            version and question; action 'full' (everyone given it earns its
            points), 'drop' (out of the points possible), or 'points' with
            points (a new value, partial credit scaled with it)
  override  version, row (the results row), student_id (checked against
            that row), question, points: one student's points on one question
  adjust    version ('' for the whole class), points: added to every total;
            the latest for a version replaces any before it

The file also records which edits the gradebook and Canvas file were last
written with, so the tab can say when they are out of date.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

import grade_functions
import outputs

EDITS = 'edits.json'
TYPES = ('key', 'credit', 'override', 'adjust')

# Scoring for results graded before the grading record kept its settings:
# the Scan tab's defaults (docs/dev/results-tab.md, default 4)
DEFAULT_SETTINGS = {'partial': False, 'strictness': 0.5,
                    'bubble_points': 1, 'written_points': 2}


def path(outdir) -> Path:
    return outputs.app_data(outdir) / EDITS


def load(outdir) -> list[dict]:
    try:
        data = json.loads(path(outdir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [e for e in data.get('edits', []) if e.get('type') in TYPES]


def _read(outdir) -> dict:
    try:
        data = json.loads(path(outdir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(outdir, edits: list[dict]) -> None:
    data = {**_read(outdir), 'edits': edits}
    path(outdir).write_text(json.dumps(data, indent=2), encoding='utf-8')


def _digest(edits: list[dict]) -> str:
    """What the edits do, so a changed note is not a change to export."""
    bare = [{k: v for k, v in e.items() if k != 'note'} for e in edits]
    return hashlib.sha1(json.dumps(bare, sort_keys=True).encode()).hexdigest()


def mark_exported(outdir, edits: list[dict]) -> None:
    """Record that the gradebook and Canvas file now carry these edits."""
    data = _read(outdir)
    if not data and not edits:
        return                      # nothing to record, and no file to make
    data.setdefault('edits', [])
    data['exported'] = _digest(edits)
    path(outdir).write_text(json.dumps(data, indent=2), encoding='utf-8')


def unexported(outdir) -> bool:
    """True when the edits differ from those last written to the gradebook
    and Canvas file. A folder whose files were never written with edits
    counts as exported only while it has none."""
    data = _read(outdir)
    return _digest(load(outdir)) != data.get('exported', _digest([]))


def make(type_: str, note: str = '', **fields) -> dict:
    """A new edit, with its id and time filled in."""
    assert type_ in TYPES, type_
    return {'id': uuid.uuid4().hex[:12], 'type': type_, **fields, 'note': note,
            'time': datetime.now().isoformat(timespec='seconds')}


def set_aside(outdir) -> Path | None:
    """Move a folder's edits out of the way, for a new scan into it: they
    were made against sheets that are no longer its results."""
    p = path(outdir)
    if not p.exists():
        return None
    dest = p.with_name(f'edits_replaced_{time.strftime("%Y%m%d-%H%M%S")}.json')
    p.rename(dest)
    return dest


def adjustments(edits: list[dict]) -> dict:
    """{version: points added}, '' for the whole class; the latest wins."""
    out = {}
    for e in edits:
        if e['type'] == 'adjust':
            out[e.get('version', '')] = float(e.get('points') or 0)
    return {v: p for v, p in out.items() if p}


def apply(graded: list[outputs.Graded], edits: list[dict]
          ) -> tuple[list[outputs.Graded], list[str]]:
    """Copies of graded with the key, credit, and override edits in, and a
    note for every edit that matched nothing. The inputs are left alone."""
    out = [copy.deepcopy(g) for g in graded]
    by_version = {g.version: g for g in out}
    problems = []
    for kind in ('key', 'credit', 'override'):
        for e in (e for e in edits if e['type'] == kind):
            ok = {'key': _key, 'credit': _credit, 'override': _override}[kind](e, out, by_version)
            if not ok:
                problems.append(f'{kind} edit {e["id"]} matched nothing: {_describe(e)}')
    return out, problems


def _describe(e: dict) -> str:
    return ', '.join(f'{k}={v}' for k, v in e.items() if k not in ('id', 'type', 'time', 'note'))


def _settings(g: outputs.Graded) -> dict:
    return {**DEFAULT_SETTINGS, **(g.settings or {})}


def _rescore(g: outputs.Graded, col: str) -> None:
    """Score every student given col again, against its accepted keys."""
    s = _settings(g)
    keys = g.accepted.get(col) or [g.df.loc['0', col]]
    pts = g.possible.get(col)
    if pts is None:
        pts = s['written_points'] if keys[0] == 'CC' else s['bubble_points']
    for r in g.students:
        if g.asked(r, col):
            g.pts.loc[r, col] = grade_functions.score_answer(
                g.df.loc[r, col], keys, pts, s['partial'], s['strictness'])[0]


def _key(e, out, by_version) -> bool:
    keys = [k for k in e.get('keys', []) if k]
    if e.get('source'):
        # Keys in the bank's letters, put into each sheet's own
        targets = [(g, c, [g.sheet_letters(c, k) for k in keys]) for g in out
                   for c, src in g.sources.items() if src == e['source'] and c in g.df.columns]
    else:
        g, col = by_version.get(e.get('version', '')), e.get('question')
        targets = [(g, col, keys)] if g is not None and col in g.df.columns else []
    if not keys:
        return False
    done = False
    for g, col, sheet_keys in targets:
        if g.df.loc['0', col] == 'CC':
            continue                # written answers are re-graded on Re-grade
        original = g.accepted.get(col) or [g.df.loc['0', col]]
        if not grade_functions.graded_key(original[0]):
            original = []
        g.accepted[col] = list(dict.fromkeys((original if e.get('also') else []) + sheet_keys))
        g.df.loc['0', col] = g.accepted[col][0]
        if col not in g.possible:
            g.possible[col] = float(_settings(g)['bubble_points'])
        _rescore(g, col)
        done = True
    return done


def _credit(e, out, by_version) -> bool:
    if e.get('source'):
        targets = [(g, c) for g in out for c, src in g.sources.items()
                   if src == e['source'] and c in g.df.columns]
    else:
        g = by_version.get(e.get('version', ''))
        targets = [(g, e.get('question'))] if g is not None and e.get('question') in g.df.columns else []
    targets = [(g, c) for g, c in targets if c in g.possible]
    action = e.get('action')
    for g, col in targets:
        if action == 'full':
            for r in g.students:
                if g.asked(r, col):
                    g.pts.loc[r, col] = g.possible[col]
        elif action == 'drop':
            # Out of the totals and the points possible alike; the points
            # column is zeroed so the gradebook's SUM agrees
            for r in g.students:
                if g.asked(r, col):
                    g.pts.loc[r, col] = 0.0
            del g.possible[col]
            g.dropped.add(col)
        elif action == 'points':
            new, old = float(e.get('points', 0)), g.possible[col]
            for r in g.students:
                if g.asked(r, col):
                    g.pts.loc[r, col] = g.earned(r, col) * new / old if old else 0.0
            g.possible[col] = new
        else:
            return False
    return bool(targets)


def _override(e, out, by_version) -> bool:
    g, col, row = by_version.get(e.get('version', '')), e.get('question'), str(e.get('row'))
    if (g is None or col not in g.df.columns or col in g.dropped
            or row not in g.students or not g.asked(row, col)):
        return False
    sid = g.df.loc[row, 'studentID'] if 'studentID' in g.df.columns else None
    if e.get('student_id') and str(e['student_id']) != ('' if pd.isna(sid) else str(sid)):
        return False
    g.pts.loc[row, col] = float(e.get('points', 0))
    return True
