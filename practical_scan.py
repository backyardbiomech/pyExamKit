'''
Scanning a lab practical: one mixed stack of every form, graded against the
practical's one key.

Pages are grouped into students by what is printed on them rather than by
position: a page 1 starts a student, and the pages after it join that
student while their page number and form agree. A missing page, a page from
another form, or a sheet that is not a practical page is reported rather than
shifting every student after it. Which box holds which question follows from
the student's form (sheet_layout.practical_boxes), so the grader is handed a
locate function instead of fixed coordinates.

The Scanner drives this (Scanner._run_practical); nothing here needs Tk.
'''
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image as PILImage, ImageDraw

import practical
import sheet_layout as L

# The handwritten name on page 1: the v2 header's name line and the space
# above it (answer_sheet._header), in the canonical frame.
NAME_BOX = (460, 60, 1100, 114)


@dataclass
class PageRead:
    scan: int              # 1-based position in the stack
    page: int              # practical page number, 0 when not a practical page
    form: str
    path: str | None       # aligned image


@dataclass
class Sheet:
    '''One student's pages, as found in the stack.'''
    form: str
    pages: list[PageRead | None]
    notes: list[str] = field(default_factory=list)

    @property
    def first_scan(self) -> int:
        return next(p.scan for p in self.pages if p is not None)


def group_pages(reads: list[PageRead], n_pages: int) -> tuple[list[Sheet], list[str]]:
    '''Students' sheets in stack order, and alerts for pages that did not fit.'''
    sheets: list[Sheet] = []
    alerts: list[str] = []
    current: Sheet | None = None
    for r in reads:
        if r.page == 0:
            alerts.append(f'PRACTICAL: scan {r.scan} is not a page of a practical form sheet '
                          f'(or could not be aligned); it was skipped.')
            continue
        if r.page > n_pages:
            alerts.append(f'PRACTICAL: scan {r.scan} is page {r.page}, but this practical\'s '
                          f'sheets have {n_pages}; it was skipped.')
            continue
        if r.page == 1:
            current = Sheet(r.form, [r] + [None] * (n_pages - 1))
            sheets.append(current)
            continue
        if current is None or current.pages[r.page - 1] is not None:
            alerts.append(f'PRACTICAL: scan {r.scan} is page {r.page} of form {r.form or "?"} '
                          f'with no page 1 before it; it was skipped.')
            continue
        if r.form != current.form:
            alerts.append(f'PRACTICAL: scan {r.scan} is page {r.page} of form {r.form or "?"}, '
                          f'but follows page 1 of form {current.form} (scan '
                          f'{current.first_scan}); it was skipped. Check the stapling.')
            continue
        current.pages[r.page - 1] = r
    for s in sheets:
        missing = [str(i + 1) for i, p in enumerate(s.pages) if p is None]
        if missing:
            s.notes.append(f'page {", ".join(missing)} missing; its answers are left blank')
    return sheets, alerts


def form_problem(form: str, p: practical.Practical) -> str:
    '''Why a form read from the squares cannot be graded, or ''.'''
    if len(form) != 2:
        return (f'the form squares read as "{form or "none"}", not two letters; '
                f'this sheet cannot be graded')
    if form not in p.forms:
        return f'form {form} is not one of this practical\'s forms ({", ".join(p.forms)})'
    return ''


def make_locate(sheets: list[Sheet], n_stations: int):
    '''locate(question_key, student_index) for OpenQs; see OpenQs.__init__.'''
    boxes = L.practical_boxes(n_stations)

    def locate(qk: str, s_idx: int):
        label = qk[len('openQ_'):] if qk.startswith('openQ_') else qk
        station, letter = int(label[:-1]), label[-1]
        sheet = sheets[s_idx]
        if len(sheet.form) != 2 or letter not in sheet.form:
            return None
        page, box = boxes[(station, sheet.form.index(letter))]
        read = sheet.pages[page - 1]
        if read is None or read.path is None:
            return None
        return read.path, L.practical_crop(box)
    return locate


def make_student_info(sheets: list[Sheet], labels: list[str]):
    '''student_info(student_index) for OpenQs: a label and the handwritten name.'''
    cache: dict[int, np.ndarray | None] = {}

    def info(s_idx: int):
        if s_idx not in cache:
            first = sheets[s_idx].pages[0]
            crop = None
            if first is not None and first.path and Path(first.path).exists():
                x0, y0, x1, y1 = NAME_BOX
                with PILImage.open(first.path) as im:
                    crop = np.array(im.convert('RGB'))[y0:y1, x0:x1]
            cache[s_idx] = crop
        return labels[s_idx], cache[s_idx]
    return info


GRADE_MARK = {'CC': ('C', (0, 170, 0)), 'CX': ('P', (230, 140, 0)), 'XX': ('X', (220, 0, 0))}


def mark_sheets(results, sheets: list[Sheet], p: practical.Practical,
                markeddir: Path, font, small_font) -> None:
    '''
    Write each student's pages with every graded box marked C, P, or X just
    right of the box, and the score and form on page 1. results is the
    graded results frame, indexed '1'.. in sheet order.
    '''
    boxes = L.practical_boxes(len(p.stations))
    for i, sheet in enumerate(sheets, 1):
        row = results.loc[str(i)]
        pages = [PILImage.open(r.path).convert('RGB') if r and r.path else None
                 for r in sheet.pages]
        draws = [ImageDraw.Draw(im) if im else None for im in pages]
        if len(sheet.form) == 2:
            for q in p.questions():
                if q.letter not in sheet.form:
                    continue
                page, (x0, y0, x1, y1) = boxes[(q.station, sheet.form.index(q.letter))]
                d = draws[page - 1]
                cell = str(row.get(f'openQ_{q.key}', ''))
                if d is None or cell[:2] not in GRADE_MARK:
                    continue
                mark, color = GRADE_MARK[cell[:2]]
                # Just outside the box's right edge, clear of the writing
                # and of the next box's printed letter
                d.text((x1 + 5, (y0 + y1) / 2), mark, fill=color, font=font, anchor='lm')
        if draws[0] is not None:
            score = float(row.get('partialscore', 0) or 0)
            possible = p.total_points(sheet.form) if len(sheet.form) == 2 else 0
            draws[0].text((470, 118), f'Form {sheet.form}   Score {score:g} / {possible:g}',
                          fill=(220, 0, 0), font=small_font)
        base = '_'.join(_safe(row.get(c, '')) for c in ('LastName', 'FirstName', 'studentID'))
        for n, im in enumerate(pages, 1):
            if im is not None:
                im.save(str(markeddir / f'{base}_p{n}.jpg'), quality=90)


def _safe(s) -> str:
    return re.sub(r'[^\w\-]', '_', str(s))
