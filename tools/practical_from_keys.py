'''
Fold a past lab practical's per-form CSV keys into one practical source file.

Before practicals were built here, each form (AB, AC, ...) had its own key
CSV, and an answer accepted on one form's key had to be copied into the
others by hand. This reads any number of those keys and writes one source
file holding every station's questions and the union of their accepted
answers. The question text is not in the old keys, so each question line is
left for the instructor to fill in.

Question labels in the old keys already carry the letter (openQ_1A,
openQ_1C), so a key's form does not need to be known. An answer that is full
credit on one key and partial on another is kept as full credit and listed
in the report.

    uv run python tools/practical_from_keys.py Practical_3_key_*.csv -o practical3.md
'''
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyformat  # noqa: E402
import practical  # noqa: E402

LABEL_RE = re.compile(r'openQ_(\d+)([A-D])$')


def merge(paths: list[Path]) -> tuple[dict, set[str], list[str]]:
    '''{(station, letter): {'full': [...], 'partial': [...]}}, the forms seen, notes.'''
    questions: dict[tuple[int, str], dict] = {}
    forms, notes = set(), []
    for path in paths:
        data = keyformat.load_key_csv(str(path))
        if data is None:
            raise SystemExit(f'Could not read {path}.')
        letters = set()
        for label, q in data.get('open_questions', {}).items():
            m = LABEL_RE.match(label)
            if not m:
                notes.append(f'{path.name}: skipped {label}, which has no station letter.')
                continue
            key = (int(m.group(1)), m.group(2))
            letters.add(key[1])
            merged = questions.setdefault(key, {'full': [], 'partial': []})
            for kind in ('full', 'partial'):
                for a in q.get(kind, []):
                    if a.lower() not in (x.lower() for x in merged[kind]):
                        merged[kind].append(a)
        if len(letters) == 2:
            forms.add(''.join(sorted(letters)))
    for key, q in questions.items():
        both = [a for a in q['partial'] if a.lower() in (x.lower() for x in q['full'])]
        if both:
            notes.append(f'{key[0]}{key[1]}: kept as full credit, listed as partial on '
                         f'another key: {", ".join(both)}')
            q['partial'] = [a for a in q['partial'] if a not in both]
    return questions, forms, notes


def render(title: str, questions: dict, forms: set[str]) -> str:
    order = [f for f in practical.DEFAULT_FORMS if f in forms] or practical.DEFAULT_FORMS
    lines = ['---', f'title: {title}', f'forms: {", ".join(order)}', 'points: 1', '---', '']
    stations = max((s for s, _ in questions), default=0)
    for s in range(1, stations + 1):
        lines += [f'# Station {s}', 'setup: ', '']
        for letter in practical.LETTERS:
            q = questions.get((s, letter), {'full': [], 'partial': []})
            lines.append(f'{letter}. ')
            if q['full']:
                lines.append('= ' + ' | '.join(q['full']))
            if q['partial']:
                lines.append('~ ' + ' | '.join(q['partial']))
            lines.append('')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('keys', nargs='+', type=Path, help='the per-form key CSVs')
    ap.add_argument('-o', '--output', type=Path, required=True, help='the .md file to write')
    ap.add_argument('--title', help='the practical title (default: the output name)')
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit(f'{args.output} already exists; choose another name.')

    questions, forms, notes = merge(args.keys)
    if not questions:
        raise SystemExit('No written questions with station letters were found in those keys.')
    args.output.write_text(render(args.title or args.output.stem, questions, forms),
                           encoding='utf-8')
    stations = max(s for s, _ in questions)
    blank = sum(1 for q in questions.values() if not q['full'])
    print(f'Wrote {args.output}: {stations} stations, {len(questions)} questions, '
          f'forms {", ".join(sorted(forms)) or "unknown"}.')
    if blank:
        print(f'{blank} questions have no full-credit answer yet.')
    for n in notes:
        print(f'  {n}')
    print('Fill in each question line and setup line before building from it.')


if __name__ == '__main__':
    main()
