'''
Build the printed materials for a lab practical from its source file.

So far this writes the form sheets: one PDF per form, and one combined PDF
that deals the forms out in the source file's order, so a stack handed down
a row gives neighbors different forms. Placards, the setup guide, and the
instructor key follow (docs/dev/lab-practicals.md, step 3).

    uv run python practical_build.py exam.md -o out/ --students 48
'''
import argparse
from pathlib import Path

import fitz

import answer_sheet
import practical
from renderer import safe_name


def write_form_sheets(p: practical.Practical, outdir: Path, students: int = 0,
                      logo=answer_sheet.DEFAULT_LOGO) -> list[Path]:
    '''
    One PDF per form, named after the practical, plus a combined PDF of
    `students` sheets in dealing order when `students` is given. Returns the
    paths written.
    '''
    outdir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(p.title)
    sheets = {f: answer_sheet.build_practical_sheet(len(p.stations), f, p.title, logo)
              for f in p.forms}
    written = []
    for f, pdf in sheets.items():
        path = outdir / f'{stem}_form_{f}.pdf'
        path.write_bytes(pdf)
        written.append(path)
    if students > 0:
        combined = fitz.open()
        docs = {f: fitz.open(stream=pdf, filetype='pdf') for f, pdf in sheets.items()}
        for i in range(students):
            combined.insert_pdf(docs[p.forms[i % len(p.forms)]])
        path = outdir / f'{stem}_all_forms_{students}_students.pdf'
        combined.save(path, garbage=4, deflate=True)
        written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser(description='Build a lab practical\'s printed materials.')
    ap.add_argument('source', type=Path, help='the practical .md file')
    ap.add_argument('-o', '--outdir', type=Path, help='output folder (default: beside the source)')
    ap.add_argument('--students', type=int, default=0,
                    help='also write one combined PDF with this many sheets, forms dealt in order')
    ap.add_argument('--no-logo', action='store_true')
    args = ap.parse_args()
    try:
        p = practical.load(args.source)
    except practical.PracticalError as exc:
        raise SystemExit(f'Cannot use {args.source}:\n{exc}')
    for w in p.warnings:
        print(f'warning: {w}')
    outdir = args.outdir or args.source.parent / f'{safe_name(p.title)}_practical'
    for path in write_form_sheets(p, outdir, args.students,
                                  logo=None if args.no_logo else answer_sheet.DEFAULT_LOGO):
        print(f'Wrote {path}')


if __name__ == '__main__':
    main()
