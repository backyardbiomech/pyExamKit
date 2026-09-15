"""
renderer.py

Renders ExamVersion objects to PDF and Markdown formats.

The PDF is laid out by PyMuPDF's Story, which flows HTML onto PDF pages.
MuPDF ignores page-break-inside, so each question is laid out as a Story of
its own and placed only where it fits whole; docs/dev/pdf-output-plan.md has
the reasoning and the prototype that settled it.
"""
from __future__ import annotations

import html
import io
import re
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import fitz  # pymupdf
from PIL import Image

from exam_builder import FONT_SIZES
from models import ExamVersion, Question
from parser import _MATH_SPLIT

# US Letter with 0.75 in top and bottom margins, which clear a corner staple
# and hold the footer, and 0.5 in side margins.
PAGE = fitz.paper_rect('letter')
SIDE_MARGIN = 36.0
TOP_MARGIN = 54.0
CONTENT_BOTTOM = PAGE.height - 54.0
CONTENT_WIDTH = PAGE.width - 2 * SIDE_MARGIN
FOOTER_RECT = fitz.Rect(SIDE_MARGIN, PAGE.height - 40, PAGE.width - SIDE_MARGIN, PAGE.height - 22)
FOOTER_PT = 9

# An image prints at its own size at 96 px/in, the scale a browser gave it
# when the exam was HTML, capped at these heights and at the width available.
PT_PER_PX = 0.75
QUESTION_IMAGE_MAX_HEIGHT = 252.0   # 3.5 in
ANSWER_IMAGE_MAX_HEIGHT = 112.0
GROUP_INSET = 16.0                  # the rule and padding beside MD/OR/MT blocks

# A question that will not fit on an empty page has its images shrunk by this
# factor per attempt, but not below MIN_IMAGE_SCALE of their normal size.
IMAGE_SHRINK_STEP = 0.8
MIN_IMAGE_SCALE = 0.2

# Room given to a question when measuring its natural height; far taller than
# any question, so MuPDF never has a reason to shrink anything in it.
_UNLIMITED_HEIGHT = 100_000.0

BLANK = '_' * 10
_BLANK_RE = re.compile(r'<span\s+class="blank"[^>]*></span>')

# Sizes are in em so the whole exam scales with the font size _Layout sets on body.
# MuPDF's own stylesheet gives body a 1em margin; since every question is a
# Story of its own, that margin would pad each one on all four sides, so it is
# reset here and the space between questions comes from _Layout.gap alone.
_CSS = """
body { font-family: serif; line-height: 1.3; margin: 0; }
p { margin: 0; }
h1 { font-size: 1.4em; margin: 0 0 0.1em 0; }
.header { border-bottom: 1.5pt solid black; padding-bottom: 0.4em; }
.name-line { margin-top: 0.6em; }
.points-note { font-style: italic; font-size: 0.92em; margin-top: 0.3em; }
.image { border-top: 0.75pt solid #888; padding-top: 0.5em; margin-bottom: 0.7em; }
.stem { margin-bottom: 0.2em; }
.pts { font-size: 0.9em; }
.note { font-style: italic; font-size: 0.9em; margin-bottom: 0.15em; }
.answer { margin-left: 3em; text-indent: -1.6em; margin-top: 0.15em; }
.selection { font-weight: bold; margin-left: 1em; margin-top: 0.35em; }
.group { border-left: 2pt solid #aaa; padding-left: 0.6em; }
"""


class ExamRenderer:

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def to_pdf(self, version: ExamVersion, output_folder: Path, total_versions: int = 1,
               default_points: float = 1.0, font_size: str = 'medium') -> tuple[Path, list[str]]:
        """Lay out version as a print-ready PDF and save it.

        Returns the saved path and warnings for the log: images that could
        not be read, $…$ math printed as typed, and questions too tall to fit
        on one page.
        """
        if font_size not in FONT_SIZES:
            raise ValueError(f"Unknown font size {font_size!r}; expected one of "
                             f"{', '.join(FONT_SIZES)}.")
        output_folder.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []

        # Compute the most-common effective point value for the header note
        mode_pts = _compute_default_pts(version.questions, default_points)
        default_pts_label = _fmt_pts(mode_pts) if mode_pts is not None else None

        # Build render-ready question dicts (handles MD grouping and numbering)
        questions = _prepare_questions(version.questions, default_points, mode_pts)

        # Hide version letter when only one version is being produced,
        # or when a version indicator question is already embedded in the exam
        hide_version = total_versions <= 1 or any(
            q.text.startswith('EXAM VERSION') for q in version.questions
        )

        layout = _Layout(FONT_SIZES[font_size])
        layout.place_flowing(layout.story(_header_markup(version, hide_version, default_pts_label)))

        archives: dict[Path, fitz.Archive] = {}
        for question, qd in zip(version.questions, questions):
            folder = question.source_folder or version.source_folder
            label = _number_label(qd)
            images, unreadable = _image_sizes(_image_paths(question), folder)
            for path in unreadable:
                warnings.append(f"Question {label}: image '{path}' could not be read from "
                                f"{folder}, so the question prints without it.")
            if any(_MATH_SPLIT.search(text) for text in _question_texts(qd)):
                warnings.append(f"Question {label} contains $…$ math, which prints exactly "
                                f"as typed; the PDF cannot typeset equations.")
            if folder not in archives:
                archives[folder] = fitz.Archive(str(folder))

            scale = 1.0
            while True:
                story = layout.story(_question_markup(qd, images, scale), archives[folder])
                if layout.place_whole(story):
                    break
                if not layout.at_page_top:
                    layout.new_page()
                elif images and scale * IMAGE_SHRINK_STEP >= MIN_IMAGE_SCALE:
                    scale *= IMAGE_SHRINK_STEP
                else:
                    shrunk = ' even with its images shrunk' if images else ''
                    warnings.append(f"Question {label} is taller than a page{shrunk}, "
                                    f"so it runs onto the next page.")
                    layout.place_flowing(
                        layout.story(_question_markup(qd, images, scale), archives[folder]))
                    break

        # The page count is only known once layout is done, so footers go on last.
        doc = fitz.open('pdf', layout.finish())
        for page in doc:
            footer = f'Page {page.number + 1} of {doc.page_count}'
            if not hide_version:
                footer = f'Version {version.version_letter} · {footer}'
            page.insert_htmlbox(FOOTER_RECT, f'<p style="text-align: center">{footer}</p>',
                                css=f'* {{ font-family: serif; font-size: {FOOTER_PT}pt; }}')

        # A reprint at another size sits beside the medium original instead of replacing it.
        size_suffix = '' if font_size == 'medium' else f'_{font_size}'
        out_file = output_folder / f"{_safe_name(version.title)}_v{version.version_letter}{size_suffix}.pdf"
        doc.save(str(out_file), garbage=3, deflate=True)
        doc.close()
        return out_file, warnings

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def to_markdown(self, version: ExamVersion, output_folder: Path) -> Path:
        """Render version to importable markdown and save the file.

        MD questions are written as MD blocks (not expanded).
        Returns the path to the saved markdown file.
        """
        output_folder.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append(
            f"# {version.title} — Version {version.version_letter} "
            f"(auto-generated {datetime.now().strftime('%Y-%m-%d %H:%M')})"
        )
        lines.append('')

        q_num = 1
        for q in version.questions:
            if q.q_type == 'MD':
                lines.append(_md_block_for_md(q, q_num))
            elif q.q_type == 'SA':
                lines.append(_md_block_for_sa(q, q_num))
            elif q.q_type == 'OR':
                lines.append(_md_block_for_or(q, q_num))
            elif q.q_type == 'MT':
                lines.append(_md_block_for_mt(q, q_num))
            else:
                lines.append(_md_block_for_question(q, q_num))
            lines.append('')
            q_num += 1

        md_text = '\n'.join(lines)
        out_file = output_folder / f"{_safe_name(version.title)}_v{version.version_letter}.md"
        out_file.write_text(md_text, encoding='utf-8')
        return out_file


# ---------------------------------------------------------------------------
# PDF layout
# ---------------------------------------------------------------------------

class _Layout:
    """Stacks blocks of markup down US Letter pages, written to memory."""

    def __init__(self, font_pt: float) -> None:
        self.css = f'body {{ font-size: {font_pt}pt; }}\n{_CSS}'
        self.gap = 1.5 * font_pt
        self._buffer = io.BytesIO()
        self._writer = fitz.DocumentWriter(self._buffer)
        self._device = None
        self._pages = 0
        self._y = 0.0
        self.new_page()

    def story(self, markup: str, archive: fitz.Archive | None = None) -> fitz.Story:
        return fitz.Story(html=markup, user_css=self.css, archive=archive)

    @property
    def at_page_top(self) -> bool:
        return self._y <= TOP_MARGIN

    def new_page(self) -> None:
        if self._device is not None:
            self._writer.end_page()
        self._device = self._writer.begin_page(PAGE)
        self._pages += 1
        self._y = TOP_MARGIN

    def place_whole(self, story: fitz.Story) -> bool:
        """Draw story in the space left on this page if all of it fits there.

        Returns False, having drawn nothing, if it does not. The fit is judged
        from the story's height laid out with unlimited room. Story.place into
        the space left cannot be trusted for this on its own: given too little
        room below the top of an image, MuPDF can shrink the image to a
        thumbnail, report that everything fit, and draw the rest of the
        question past the bottom of the page.
        """
        if self._y >= CONTENT_BOTTOM:
            return False
        space = self._space_left()
        _, natural = story.place(fitz.Rect(space.x0, 0, space.x1, _UNLIMITED_HEIGHT))
        if fitz.Rect(natural).height > space.height:
            return False
        story.reset()
        more, filled = story.place(space)
        if more or fitz.Rect(filled).y1 > space.y1 + 0.5:
            return False
        self._draw(story, filled)
        return True

    def place_flowing(self, story: fitz.Story) -> None:
        """Draw story from here on, continuing onto new pages as needed."""
        if self._y >= CONTENT_BOTTOM:
            self.new_page()
        while True:
            more, filled = story.place(self._space_left())
            self._draw(story, filled)
            # An empty page that takes nothing would loop forever; stop instead.
            if not more or fitz.Rect(filled).is_empty:
                return
            self.new_page()

    def finish(self) -> bytes:
        self._writer.end_page()
        self._writer.close()
        return self._buffer.getvalue()

    def _space_left(self) -> fitz.Rect:
        return fitz.Rect(SIDE_MARGIN, self._y, PAGE.width - SIDE_MARGIN, CONTENT_BOTTOM)

    def _draw(self, story: fitz.Story, filled) -> None:
        story.draw(self._device)
        self._y = fitz.Rect(filled).y1 + self.gap


def _header_markup(version: ExamVersion, hide_version: bool, default_pts_label: str | None) -> str:
    meta = html.escape(version.course)
    if not hide_version:
        meta += f'&nbsp;&nbsp;&nbsp;Version {version.version_letter}'
    parts = [f'<h1>{html.escape(version.title)}</h1>']
    if meta:
        parts.append(f'<p>{meta}</p>')
    parts.append('<p class="name-line">Name:&nbsp;___________________________'
                 '&nbsp;&nbsp;&nbsp;&nbsp;Date:&nbsp;___________</p>')
    if default_pts_label:
        parts.append(f'<p class="points-note">Each question is worth {default_pts_label} pts '
                     f'unless otherwise noted.</p>')
    return f'<div class="header">{"".join(parts)}</div>'


def _question_markup(qd: dict, images: dict[str, tuple[float, float]], scale: float) -> str:
    """One question as Story markup, its images drawn at `scale` of normal size.

    Image paths absent from `images` could not be read and are left out.
    """
    q_type = qd['q_type']
    grouped = q_type in ('MD', 'OR', 'MT')
    width = CONTENT_WIDTH - GROUP_INSET if grouped else CONTENT_WIDTH
    parts: list[str] = []

    figures = [_image_tag(path, images[path], width, QUESTION_IMAGE_MAX_HEIGHT, scale)
               for path in qd['image_paths'] if path in images]
    if figures:
        parts.append(f'<p class="image">{"<br>".join(figures)}</p>')

    pts = qd['show_pts']
    if grouped:
        start, end = qd['start_num'], qd['end_num']
        number = f'{start}.' if start == end else f'Questions {start}&ndash;{end}.'
        each = 'each' if q_type == 'MD' else 'total'
        pts_label = f' <span class="pts">({pts} pts {each})</span>' if pts else ''
    else:
        number = f"{qd['q_num']}."
        pts_label = f' <span class="pts">({pts} pts)</span>' if pts else ''
    parts.append(f'<p class="stem"><b>{number}</b>{pts_label} {_inline(qd["text"])}</p>')

    if q_type == 'MD':
        for sel in qd['selections']:
            parts.append(f'<p class="selection">Question {sel["q_num"]}:</p>')
            parts.extend(_answer_line(_LETTERS[i], _inline(ans.text))
                         for i, ans in enumerate(sel['answers']))
    elif q_type == 'OR':
        parts.extend(_answer_line(item['letter'], _inline(item['text']))
                     for item in qd['display_items'])
        for slot in qd['slots']:
            label = f'&nbsp;&nbsp;{_inline(slot["label"])}' if slot['label'] else ''
            parts.append(f'<p class="selection">(Question {slot["q_num"]}){label}:&nbsp;{BLANK}</p>')
    elif q_type == 'MT':
        parts.extend(_answer_line(right['letter'], _inline(right['text']))
                     for right in qd['display_rights'])
        for slot in qd['slots']:
            parts.append(f'<p class="selection">(Question {slot["q_num"]})&nbsp;&nbsp;'
                         f'{_inline(slot["text"])}:&nbsp;{BLANK}</p>')
    elif q_type == 'SA':
        parts.append('<p class="note">(Write your answer on the answer sheet.)</p>')
    else:
        if q_type == 'MA':
            parts.append('<p class="note">(Select all that apply.)</p>')
        for i, ans in enumerate(qd['answers']):
            if ans.image_path in images:
                body = _image_tag(ans.image_path, images[ans.image_path], width / 2,
                                  ANSWER_IMAGE_MAX_HEIGHT, scale)
            else:
                body = _inline(ans.text)
            parts.append(_answer_line(_LETTERS[i], body))

    css_class = ' class="group"' if grouped else ''
    return f'<div{css_class}>{"".join(parts)}</div>'


def _answer_line(letter: str, body: str) -> str:
    return f'<p class="answer"><b>{letter}.</b>&nbsp;&nbsp;{body}</p>'


def _inline(text: str) -> str:
    """Parsed question text as Story markup.

    Blanks become underscores. $…$ math, which the parser leaves unescaped
    for MathJax, is escaped so it prints as typed instead of reading as tags.
    """
    segments = _MATH_SPLIT.split(text)
    for i, segment in enumerate(segments):
        segments[i] = html.escape(segment, quote=False) if i % 2 else _BLANK_RE.sub(BLANK, segment)
    return ''.join(segments)


def _image_tag(path: str, size: tuple[float, float], max_width: float, max_height: float,
               scale: float) -> str:
    width, height = size
    fit = min(1.0, max_width / width, max_height / height) * scale
    return (f'<img src="{html.escape(path)}" '
            f'style="width: {width * fit:.1f}pt; height: {height * fit:.1f}pt">')


def _image_paths(q: Question) -> list[str]:
    return q.image_paths + [ans.image_path for ans in q.answers if ans.image_path]


def _image_sizes(paths: list[str], folder: Path) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """Normal printed size, in points, of each readable image, plus the unreadable paths."""
    sizes: dict[str, tuple[float, float]] = {}
    unreadable: list[str] = []
    for path in paths:
        try:
            with Image.open(folder / path) as im:
                sizes[path] = (im.width * PT_PER_PX, im.height * PT_PER_PX)
        except (OSError, ValueError):
            unreadable.append(path)
    return sizes, unreadable


def _question_texts(qd: dict) -> Iterator[str]:
    """Every piece of question text that prints, for the math check."""
    yield qd['text']
    for ans in qd.get('answers', []):
        yield ans.text
    for sel in qd.get('selections', []):
        for ans in sel['answers']:
            yield ans.text
    for item in qd.get('display_items', []) + qd.get('display_rights', []):
        yield item['text']
    for slot in qd.get('slots', []):
        yield slot.get('text') or slot.get('label') or ''


def _number_label(qd: dict) -> str:
    """The question's number as the log names it: '7', or '4–6' for a group."""
    if 'q_num' in qd:
        return str(qd['q_num'])
    start, end = qd['start_num'], qd['end_num']
    return str(start) if start == end else f'{start}–{end}'


# ---------------------------------------------------------------------------
# Question preparation
# ---------------------------------------------------------------------------

_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _fmt_pts(pts: float) -> str:
    """Format a point value without an unnecessary trailing .0."""
    return str(int(pts)) if pts == int(pts) else str(pts)


def _compute_default_pts(questions: list[Question], build_default: float) -> float | None:
    """Return the most common effective point value if there is a unique plurality, else None.

    Untagged questions (q.points is None) count as worth build_default.
    Questions with unparseable pts tags are skipped.
    """
    vals: list[float] = []
    for q in questions:
        if q.points is None:
            vals.append(build_default)
        else:
            try:
                vals.append(float(q.points))
            except (ValueError, TypeError):
                pass  # unparseable pts tag; skip this question
    if not vals:
        return None
    counts = Counter(vals)
    most_common = counts.most_common(2)
    if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
        return most_common[0][0]
    return None


def _pts_label(pts_str: str | None, build_default: float, mode_pts: float | None) -> str | None:
    """Return formatted pts string to show for a question, or None if it matches the mode.

    Untagged questions (pts_str is None) are treated as worth build_default.
    """
    if pts_str is None:
        effective = build_default
    else:
        try:
            effective = float(pts_str)
        except (ValueError, TypeError):
            return pts_str  # unparseable; show as-is
    if mode_pts is not None and effective == mode_pts:
        return None  # covered by the header note
    return _fmt_pts(effective)


def _prepare_questions(questions: list[Question], build_default: float, mode_pts: float | None) -> list[dict]:
    """Convert Question objects into render-ready dicts, one per question, in order.

    Tracks sequential question numbers (each MD dropdown occupies one slot).
    For MD questions, replaces [dropname] markers in the stem with
    bold (Selection N) labels and packages each dropdown's answers as a
    'selections' list.
    """
    result: list[dict] = []
    q_num = 1

    for q in questions:
        if q.q_type == 'MD':
            n = len(q.dropdowns)
            start = q_num
            end = q_num + n - 1

            # Replace [dropname] with <strong>(Question N)</strong> in the stem
            stem = q.text
            for i, dropdown in enumerate(q.dropdowns):
                actual_num = q_num + i
                stem = stem.replace(
                    f'[{dropdown.name}]',
                    f'<strong>(Question {actual_num})</strong>',
                    1,
                )

            selections = [
                {'q_num': q_num + i, 'answers': list(dropdown.answers)}
                for i, dropdown in enumerate(q.dropdowns)
            ]

            result.append({
                'q_type': 'MD',
                'text': stem,
                'image_paths': q.image_paths,
                'show_pts': _pts_label(q.points, build_default, mode_pts),
                'start_num': start,
                'end_num': end,
                'selections': selections,
            })
            q_num += n
        elif q.q_type == 'OR':
            n = len(q.order_items)
            start = q_num
            end = q_num + n - 1

            # q.order_items is already in builder-shuffled display order;
            # letter by position, same convention as every other answer list.
            display_items = [
                {'letter': _LETTERS[i], 'text': item.text}
                for i, item in enumerate(q.order_items)
            ]
            slots = [
                {
                    'q_num': start + i,
                    'label': q.order_top_label if i == 0 else (
                        q.order_bottom_label if i == n - 1 else ''
                    ),
                }
                for i in range(n)
            ]

            result.append({
                'q_type': 'OR',
                'text': q.text,
                'image_paths': q.image_paths,
                'show_pts': _pts_label(q.points, build_default, mode_pts),
                'start_num': start,
                'end_num': end,
                'display_items': display_items,
                'slots': slots,
            })
            q_num += n
        elif q.q_type == 'MT':
            n = len(q.match_lefts)
            start = q_num
            end = q_num + n - 1

            # q.match_rights is already in builder-shuffled display order.
            display_rights = [
                {'letter': _LETTERS[i], 'text': r.text}
                for i, r in enumerate(q.match_rights)
            ]
            slots = [
                {'q_num': start + i, 'text': left.text}
                for i, left in enumerate(q.match_lefts)
            ]

            result.append({
                'q_type': 'MT',
                'text': q.text,
                'image_paths': q.image_paths,
                'show_pts': _pts_label(q.points, build_default, mode_pts),
                'start_num': start,
                'end_num': end,
                'display_rights': display_rights,
                'slots': slots,
            })
            q_num += n
        elif q.q_type == 'SA':
            result.append({
                'q_type': 'SA',
                'text': q.text,
                'image_paths': q.image_paths,
                'show_pts': _pts_label(q.points, build_default, mode_pts),
                'q_num': q_num,
            })
            q_num += 1
        else:
            result.append({
                'q_type': q.q_type,
                'text': q.text,
                'image_paths': q.image_paths,
                'show_pts': _pts_label(q.points, build_default, mode_pts),
                'q_num': q_num,
                'answers': q.answers,
            })
            q_num += 1

    return result


# ---------------------------------------------------------------------------
# Markdown building helpers
# ---------------------------------------------------------------------------


def _md_block_for_question(q: Question, num: int) -> str:
    """Render a single MC or MA Question as a markdown block."""
    parts: list[str] = []
    parts.append(q.q_type)
    for img in q.image_paths:
        parts.append(f"image: {img}")
    if q.points:
        parts.append(f"({q.points} pts)")
    parts.append(f"{num}. {_strip_html(q.text)}")
    for i, ans in enumerate(q.answers):
        letter = chr(ord('A') + i)
        prefix = '*' if ans.is_correct else ''
        parts.append(f"{prefix}{letter}. {_strip_html(ans.text)}")
    return '\n'.join(parts)


def _md_block_for_md(q: Question, num: int) -> str:
    """Render an MD Question back to importable markdown format."""
    parts: list[str] = []
    parts.append('MD')
    for img in q.image_paths:
        parts.append(f"image: {img}")
    if q.points:
        parts.append(f"({q.points} pts)")
    # q.text has HTML formatting; strip it to restore plain markdown
    parts.append(f"{num}. {_strip_html(q.text)}")
    for dropdown in q.dropdowns:
        for ans in dropdown.answers:
            prefix = '*' if ans.is_correct else ''
            parts.append(f"{prefix}{dropdown.name}: {_strip_html(ans.text)}")
    return '\n'.join(parts)


def _md_block_for_or(q: Question, num: int) -> str:
    """Render an OR Question back to importable markdown format.

    Items are written in true rank order, not display (shuffled) order --
    the source format's numeric prefixes encode the correct sequence, and
    writing them out of order would make the regenerated file misleading
    to a human re-editing it.
    """
    parts: list[str] = ['OR']
    for img in q.image_paths:
        parts.append(f"image: {img}")
    if q.points:
        parts.append(f"({q.points} pts)")
    parts.append(f"{num}. {_strip_html(q.text)}")
    if q.order_top_label:
        parts.append(f"toplabel: {_strip_html(q.order_top_label)}")
    for item in sorted(q.order_items, key=lambda it: it.rank):
        parts.append(f"{item.rank}: {_strip_html(item.text)}")
    if q.order_bottom_label:
        parts.append(f"bottomlabel: {_strip_html(q.order_bottom_label)}")
    return '\n'.join(parts)


def _md_block_for_mt(q: Question, num: int) -> str:
    """Render an MT Question back to importable markdown format.

    The original left-side name tokens (left1, left2...) aren't stored on
    MatchLeft, so they're resynthesized sequentially here; only the right
    labels are read back from parsing, so those are preserved exactly,
    including one label shared as the correct answer for multiple lefts.
    """
    parts: list[str] = ['MT']
    for img in q.image_paths:
        parts.append(f"image: {img}")
    if q.points:
        parts.append(f"({q.points} pts)")
    parts.append(f"{num}. {_strip_html(q.text)}")
    for i, left in enumerate(q.match_lefts, start=1):
        parts.append(f"[{left.correct_label}]left{i}: {_strip_html(left.text)}")
    for right in q.match_rights:
        parts.append(f"{right.label}: {_strip_html(right.text)}")
    return '\n'.join(parts)


def _md_block_for_sa(q: Question, num: int) -> str:
    """Render an SA Question as importable markdown (SA block format).

    Starred answers (is_correct=True) are written with * prefix (full credit).
    Unstarred answers (is_correct=False) have no prefix (partial credit).
    """
    parts: list[str] = ['SA']
    for img in q.image_paths:
        parts.append(f"image: {img}")
    if q.points:
        parts.append(f"({q.points} pts)")
    parts.append(f"{num}. {_strip_html(q.text)}")
    letter = ord('A')
    for ans in q.answers:
        prefix = '*' if ans.is_correct else ''
        parts.append(f"{prefix}{chr(letter)}. {_strip_html(ans.text)}")
        letter += 1
    return '\n'.join(parts)


def _strip_html(text: str) -> str:
    """Remove simple HTML tags and unescape HTML entities for markdown output."""
    # Restore blank spans to underscores before stripping all tags
    text = _BLANK_RE.sub('________', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    return text


def safe_name(name: str) -> str:
    """Convert a title to a filesystem-safe name."""
    return re.sub(r'[^\w\-_.]', '_', name)


# Keep private alias for internal use
_safe_name = safe_name
