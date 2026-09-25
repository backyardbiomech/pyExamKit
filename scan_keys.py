'''
The key files for one scan, as Scan Exams presents them.

Build Exam writes one key per version, `<Title>_vA_key.csv` and so on,
side by side. Choosing any one of them finds the rest, so a multi-version
stack is graded against every version's key without picking each by hand.
A key says which version it belongs to in its metadata; keys written
before that was recorded fall back to the letter in the file name.
'''
import re
from dataclasses import dataclass, field
from pathlib import Path

from keyformat import load_key_file

_VERSION_NAME = re.compile(r'^(?P<stem>.*)_v(?P<letter>[A-F])_key\.(?P<ext>csv|json)$', re.I)


class KeySetError(ValueError):
    '''Keys that cannot be graded together; the message is shown to the user.'''


@dataclass
class KeySet:
    paths: dict[str, str]              # version letter -> key path; '' for an unlettered key
    num_questions: int
    skip: list[int]                    # rows every key skips (written answers)
    has_points: bool                   # every graded row has its points in the key
    written: int                       # written-answer questions in the largest key
    pages: int                         # pages per student the written answers need
    grouped: bool                      # a sheet printed with rows grouped by question
    notes: list[str] = field(default_factory=list)

    @property
    def multi(self) -> bool:
        return len(self.paths) > 1

    def summary(self) -> str:
        parts = [f'{len(self.paths)} versions ({", ".join(sorted(self.paths))})'
                 if self.multi else 'one version']
        parts.append(f'{self.num_questions} questions'
                     + (f', {self.written} written' if self.written else ''))
        parts.append('points from the key' if self.has_points
                     else 'no points in the key; using the defaults below')
        if self.grouped:
            parts.append('rows grouped by question')
        return ' · '.join(parts)


def _letter(path: Path, data: dict) -> str:
    letter = str(data.get('metadata', {}).get('version', '')).strip().upper()
    if letter:
        return letter
    m = _VERSION_NAME.match(path.name)
    return m['letter'].upper() if m else ''


def _siblings(path: Path) -> list[Path]:
    '''The other versions' keys written beside this one by the same build.'''
    m = _VERSION_NAME.match(path.name)
    if not m:
        return [path]
    found = [p for p in sorted(path.parent.iterdir())
             if (n := _VERSION_NAME.match(p.name))
             and n['stem'] == m['stem'] and n['ext'].lower() == m['ext'].lower()]
    return found or [path]


def load_keys(chosen: list[str]) -> KeySet:
    '''
    Load the chosen key files. One chosen file named like a Build Exam key
    brings in its sibling versions; several chosen files are used as given.
    '''
    if not chosen:
        raise KeySetError('Choose a key file.')
    files = _siblings(Path(chosen[0])) if len(chosen) == 1 else [Path(c) for c in chosen]
    keys: dict[str, tuple[str, dict]] = {}
    for f in files:
        data = load_key_file(str(f))
        if not data:
            raise KeySetError(f'Could not read the key file {f.name}.')
        letter = _letter(f, data)
        if letter in keys:
            raise KeySetError(f'{keys[letter][0]} and {f.name} are both keys for '
                              f'version {letter or "(unlettered)"}; choose one.')
        keys[letter] = (f.name, data | {'_path': str(f)})
    if len(keys) > 1 and '' in keys:
        raise KeySetError(f'{keys[""][0]} does not say which version it is for. Choose it on '
                          'its own, or rename it to end in _vA_key.csv and so on.')

    metas = [d.get('metadata', {}) for _, d in keys.values()]
    counts = [int(m.get('num_questions') or len(d.get('bubble_answers', {})))
              for m, (_, d) in zip(metas, keys.values())]
    skips = [set(int(n) for n in str(m.get('questions_to_skip', '')).split(',') if n.strip())
             for m in metas]
    common_skip = sorted(set.intersection(*skips)) if skips else []

    def points_complete(d):
        pv = d.get('point_values', {})
        graded = [k for k, v in d.get('bubble_answers', {}).items() if v != 'ignore']
        return bool(graded) and all(k in pv for k in graded)

    written = max(len(d.get('open_questions', {})) for _, d in keys.values())
    pages = max((int(q.get('page', 1) or 1)
                 for _, d in keys.values() for q in d.get('open_questions', {}).values()),
                default=1)
    ks = KeySet(
        paths={v: d['_path'] for v, (_, d) in keys.items()},
        num_questions=max(counts),
        skip=common_skip,
        has_points=all(points_complete(d) for _, d in keys.values()),
        written=written,
        pages=pages,
        grouped=any(m.get('sheet_rows') for m in metas),
    )
    if len(set(counts)) > 1:
        ks.notes.append('The versions have different numbers of questions, so each version '
                        'has its own answer sheet; check that every student used the right one.')
    return ks
