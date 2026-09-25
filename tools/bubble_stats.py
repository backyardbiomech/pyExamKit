'''
Measure how dark every question bubble is on a stack of real scans, so the
reader's cutoffs can be set from data (docs/dev/answer-sheet-redesign.md).

Writes one row per question bubble: scan number, question, letter, raw
darkness, fill score after subtracting the printed ink, the sheet's fill
level, and how the current reader decided it. It writes nothing from the ID
or name grids, since their pattern of dark bubbles spells out the ID or
name, and it writes no images, so the output can be shared.

    uv run python tools/bubble_stats.py scans.pdf --questions 50 -o stats.csv

Sheets printed with rows grouped by question need the exam's key file
(--key), which says where their rows are.
'''
import argparse
import csv
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bubbles  # noqa: E402
import init_functions  # noqa: E402
import sheet_layout  # noqa: E402
from keyformat import load_key_file  # noqa: E402
from image import Image  # noqa: E402
from settings import Settings  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('scans', help='PDF of scanned sheets, or the first JPG in a folder of them')
    ap.add_argument('--questions', type=int, required=True, help='number of questions on the exam')
    ap.add_argument('--ignore', default='', help='comma-separated question numbers to skip')
    ap.add_argument('--key', help="the exam's key file, for sheets with grouped rows")
    ap.add_argument('-o', '--out', default='bubble_stats.csv')
    args = ap.parse_args()
    ignores = [int(x) for x in args.ignore.split(',') if x.strip()]
    keyed = {}
    runs = ((load_key_file(args.key) or {}).get('metadata', {}).get('sheet_rows')
            if args.key else None)
    if runs:
        keyed[''] = sheet_layout.keyed_layout(sheet_layout.parse_columns(runs))

    with tempfile.TemporaryDirectory() as tmp:
        pages = init_functions.filenames(args.scans, scan_jpgs_dir=Path(tmp))
        rows, levels = [], []
        for n, path in enumerate(pages, 1):
            try:
                aligned = Image(path, Settings()).aligned
            except ValueError as exc:
                print(f'scan {n}: skipped ({exc})')
                continue
            r = bubbles.read_sheet(aligned, args.questions, ignores, keyed=keyed)
            gray = bubbles.to_gray(aligned)
            paper = max(float(np.percentile(gray, 95)), 1.0)
            q_rows = r.layout.question_rows(args.questions)
            dark = bubbles.darkness(gray, q_rows, paper)
            ignored = {k for k in q_rows if int(k[1:]) in ignores}
            fill = bubbles.fill_scores(dark, exclude=ignored)
            flagged = {(f.field, f.label) for f in r.flags}
            levels.append(r.fill_level)
            for k, row in q_rows.items():
                if k in ignored:
                    continue
                for j, (lab, _, _) in enumerate(row):
                    rows.append([n, k, lab, round(dark[k][j], 4), round(fill[k][j], 4),
                                 round(r.fill_level, 4), round(r.cut, 4),
                                 'filled' if lab in r.answers[k] else 'empty',
                                 int((k, lab) in flagged)])
            print(f'scan {n}: fill level {r.fill_level:.2f}, {len(r.flags)} flag(s)')

    with open(args.out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['scan', 'question', 'letter', 'darkness', 'fill', 'sheet_fill_level',
                    'cut', 'read_as', 'flagged'])
        w.writerows(rows)
    if levels:
        q = np.percentile(levels, [0, 10, 50, 90, 100])
        print(f'\n{len(levels)} sheets. Fill level min {q[0]:.2f}, 10% {q[1]:.2f}, '
              f'median {q[2]:.2f}, 90% {q[3]:.2f}, max {q[4]:.2f}')
    print(f'Wrote {len(rows)} bubbles to {args.out}')


if __name__ == '__main__':
    main()
