'''
Class roster: fill in student names from the ID bubbled on each sheet.

Accepts either a plain CSV (last name, first name, ID) or a Canvas gradebook
export as downloaded. The user-facing description of both is docs/roster.md;
keep the two in step.
'''
import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

ID_DIGITS = 8

# Header names recognized for each role, compared lowercased with spaces,
# underscores, hyphens and periods removed. Earlier entries win, which is
# what puts Canvas's 'SIS User ID' ahead of its internal 'ID' column.
ID_HEADERS = ['sisuserid', 'lnumber', 'longwoodid', 'studentid', 'idnumber',
              'studentnumber', 'sisloginid', 'id']
LAST_HEADERS = ['lastname', 'last', 'surname', 'familyname']
FIRST_HEADERS = ['firstname', 'first', 'givenname']
FULL_HEADERS = ['student', 'studentname', 'name', 'fullname', 'sortablename']


class RosterError(ValueError):
    '''A roster file the app cannot use; the message is shown to the user.'''


@dataclass
class Student:
    last: str
    first: str
    id: str


def normalize_id(raw) -> str | None:
    '''
    Strips a leading 'L' and restores leading zeros a spreadsheet dropped,
    so '123456' becomes '00123456'. Returns None for anything not an ID.
    '''
    s = str(raw or '').strip().upper()
    if not re.fullmatch(r'L?\s*\d{1,%d}' % ID_DIGITS, s):
        return None
    return re.sub(r'\D', '', s).zfill(ID_DIGITS)


def _key(header: str) -> str:
    return re.sub(r'[\s_\-.]', '', header.strip().lower())


def _pick(headers: list[str], wanted: list[str]) -> int | None:
    keys = [_key(h) for h in headers]
    for w in wanted:
        if w in keys:
            return keys.index(w)
    return None


def _split_full(name: str) -> tuple[str, str]:
    '''"Last, First" (Canvas) or "First Last".'''
    name = name.strip()
    if ',' in name:
        last, first = name.split(',', 1)
        return last.strip(), first.strip()
    parts = name.split()
    if len(parts) >= 2:
        return ' '.join(parts[1:]), parts[0]
    return name, ''


def load_roster(path) -> tuple[dict[str, Student], str]:
    '''
    Returns ({id: Student}, description of what was read). The description
    names columns and counts, never students, so it is safe to log.
    '''
    path = Path(path)
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.reader(f))
    except UnicodeDecodeError:
        with open(path, newline='', encoding='latin-1') as f:
            rows = list(csv.reader(f))
    except OSError as exc:
        raise RosterError(f'Could not open the roster file: {exc}') from exc
    if len(rows) < 2:
        raise RosterError('The roster file has no rows below the header.')

    header, body = rows[0], rows[1:]
    id_col = _pick(header, ID_HEADERS)
    if id_col is None:
        # No recognizable header: take the column whose values look like IDs.
        best, best_frac = None, 0.0
        for c in range(len(header)):
            vals = [r[c] for r in body if c < len(r) and r[c].strip()]
            if vals:
                frac = sum(normalize_id(v) is not None for v in vals) / len(vals)
                if frac > best_frac:
                    best, best_frac = c, frac
        if best is None or best_frac < 0.8:
            raise RosterError(
                'Could not find a student ID column. Name it "ID" (or use a Canvas '
                'gradebook export, which has "SIS User ID").')
        id_col = best

    last_col, first_col = _pick(header, LAST_HEADERS), _pick(header, FIRST_HEADERS)
    full_col = None
    if last_col is None or first_col is None:
        full_col = _pick(header, FULL_HEADERS)
        if full_col is None:
            raise RosterError(
                'Could not find the name columns. Use "LastName" and "FirstName", '
                'or a single "Student" column written "Last, First".')

    roster: dict[str, Student] = {}
    skipped = duplicates = 0
    for r in body:
        cell = lambda c: r[c].strip() if c is not None and c < len(r) else ''
        sid = normalize_id(cell(id_col))
        if sid is None:
            skipped += 1        # Canvas's "Points Possible" row, test students, blanks
            continue
        if full_col is not None:
            last, first = _split_full(cell(full_col))
        else:
            last, first = cell(last_col), cell(first_col)
        if sid in roster:
            duplicates += 1
            continue
        roster[sid] = Student(last, first, sid)

    if not roster:
        raise RosterError(f'No usable student IDs in the "{header[id_col]}" column.')
    names = (f'"{header[full_col]}"' if full_col is not None
             else f'"{header[last_col]}" and "{header[first_col]}"')
    desc = (f'{len(roster)} students; IDs from the "{header[id_col]}" column, '
            f'names from {names}')
    if skipped:
        desc += f'; {skipped} row(s) without an ID skipped'
    if duplicates:
        desc += f'; {duplicates} repeated ID(s) ignored'
    return roster, desc


def match_id(scanned: str, roster: dict[str, Student]) -> tuple[Student | None, str]:
    '''
    Match a bubbled ID (unread digits are '-') to the roster. An exact match
    returns an empty note; a unique roster ID one digit away (a misbubbled or
    blank column) is accepted with a note; anything else returns None.
    '''
    if scanned in roster:
        return roster[scanned], ''
    if len(scanned) != ID_DIGITS or scanned.count('-') > 1:
        return None, 'not on the roster'
    near = [s for sid, s in roster.items()
            if sum(a != b for a, b in zip(scanned, sid)) == 1]
    if len(near) == 1:
        return near[0], f'one digit off; matched to roster ID {near[0].id}'
    if len(near) > 1:
        return None, 'one digit off from more than one roster ID'
    return None, 'not on the roster'


# A suggestion is shown from SUGGEST_AT; a name typed but not picked is taken
# as the best match only from ACCEPT_AT, and only when it clearly beats the next
SUGGEST_AT = 0.6
ACCEPT_AT = 0.8


def _word_score(word: str, s: Student) -> float:
    '''How well one typed word fits a student: 1 when it starts their last
    or first name, otherwise how close its spelling is to either.'''
    names = [n for n in (s.last.lower(), s.first.lower()) if n]
    if any(n.startswith(word) for n in names):
        return 1.0
    return max((SequenceMatcher(None, word, n).ratio() for n in names), default=0.0)


def suggest(typed: str, roster: dict[str, Student], limit: int = 6) -> list[tuple[Student, float]]:
    '''
    Roster students that fit a typed name or partial ID, best first, with a
    score from 0 to 1. Every word starting a name scores 1; misspellings
    score by how close they are, so "jonson" still finds Johnson.
    '''
    typed = typed.strip()
    digits = re.sub(r'\D', '', typed)
    if re.fullmatch(r'[Ll]?\s*\d+', typed):
        return [(st, 1.0) for st in roster.values() if digits in st.id][:limit]
    words = [w for w in re.split(r'[\s,]+', typed.lower()) if w]
    if not words:
        return []
    scored = [(st, sum(_word_score(w, st) for w in words) / len(words))
              for st in roster.values()]
    scored = [(st, sc) for st, sc in scored if sc >= SUGGEST_AT]
    scored.sort(key=lambda p: (-p[1], p[0].last, p[0].first))
    return scored[:limit]


def match_typed(typed: str, roster: dict[str, Student] | None) -> tuple[Student, str]:
    '''
    Who a sheet belongs to, from an L number or name typed by hand when the
    bubbled ID named no one. A name matches a roster student when every word
    typed starts their last or first name. Without a unique roster match the
    typed name or ID is used as given, with a note saying why; '-' stands for
    a part that was not typed.
    '''
    sid = normalize_id(typed)
    if sid:
        if roster is None:
            return Student('-', '-', sid), ''
        if sid in roster:
            return roster[sid], ''
        return Student('-', '-', sid), 'not on the roster'
    last, first = _split_full(typed)
    given = Student(last or '-', first or '-', '')
    if roster is None:
        return given, ''
    ranked = suggest(typed, roster, limit=len(roster))
    exact = [st for st, sc in ranked if sc == 1.0]
    if len(exact) == 1:
        return exact[0], ''
    if exact:
        return given, f'matches {len(exact)} roster students; check the name'
    if ranked and ranked[0][1] >= ACCEPT_AT and (
            len(ranked) == 1 or ranked[1][1] < ranked[0][1] - 0.1):
        best = ranked[0][0]
        return best, f'no exact match; taken as {best.last}, {best.first} by spelling'
    return given, 'not on the roster'
