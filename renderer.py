"""
renderer.py

Renders ExamVersion objects to HTML and Markdown formats.

The exam is HTML, printed from a browser, because equations need MathJax.
docs/dev/pdf-output-plan.md records the direct-PDF renderer that briefly
replaced it and why that was withdrawn.
"""
from __future__ import annotations

import dataclasses
import filecmp
import html
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from exam_builder import FONT_SIZES
from models import ExamVersion, Question
from parser import _MATH_SPLIT

_TEMPLATES_DIR = Path(__file__).parent / 'templates'
_BLANK_RE = re.compile(r'<span\s+class="blank"[^>]*></span>')


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape([]),  # We manage escaping ourselves
        keep_trailing_newline=True,
    )
    # Add a 'basename' filter for image path resolution in templates
    env.filters['basename'] = lambda p: Path(p).name
    env.filters['math_safe'] = _escape_math
    return env


class ExamRenderer:
    def __init__(self) -> None:
        self._env = _jinja_env()

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def to_html(self, version: ExamVersion, output_folder: Path, total_versions: int = 1,
                default_points: float = 1.0, font_size: str = 'medium') -> tuple[Path, list[str]]:
        """Render version to HTML, copy its images beside it, and save the file.

        Returns the saved path and warnings for the log naming any image that
        could not be found.
        """
        if font_size not in FONT_SIZES:
            raise ValueError(f"Unknown font size {font_size!r}; expected one of "
                             f"{', '.join(FONT_SIZES)}.")
        output_folder.mkdir(parents=True, exist_ok=True)
        images_folder = output_folder / 'images'
        images_folder.mkdir(exist_ok=True)
        warnings: list[str] = []

        # Compute the most-common effective point value for the header note
        mode_pts = _compute_default_pts(version.questions, default_points)
        default_pts_label = _fmt_pts(mode_pts) if mode_pts is not None else None

        # Build render-ready question dicts (handles MD grouping and numbering)
        questions = _prepare_questions(version.questions, default_points, mode_pts)

        # Copy images from source_folder into output/images/, pointing the
        # question at whatever name the copy landed under.
        for q, qd in zip(version.questions, questions):
            q_folder = q.source_folder or version.source_folder

            def place(img_path: str) -> str:
                src = q_folder / img_path
                if src.exists():
                    return _place_image(src, images_folder)
                warnings.append(f"Question {_number_label(qd)}: image '{img_path}' was not "
                                f"found in {q_folder}, so the question prints without it.")
                return img_path

            qd['image_paths'] = [place(p) for p in q.image_paths]
            if 'answers' in qd:
                qd['answers'] = [dataclasses.replace(ans, image_path=place(ans.image_path))
                                 if ans.image_path else ans for ans in qd['answers']]

        # Hide version letter when only one version is being produced,
        # or when a version indicator question is already embedded in the exam
        hide_version = total_versions <= 1 or any(
            q.text.startswith('EXAM VERSION') for q in version.questions
        )

        template = self._env.get_template('exam.html')
        html_text = template.render(
            version=version,
            questions=questions,
            hide_version=hide_version,
            default_pts_label=default_pts_label,  # None when there is no clear single point value
            font_pt=FONT_SIZES[font_size],
            footer_version=None if hide_version else version.version_letter,
        )

        # A reprint at another size sits beside the medium original instead of replacing it.
        size_suffix = '' if font_size == 'medium' else f'_{font_size}'
        out_file = output_folder / f"{_safe_name(version.title)}_v{version.version_letter}{size_suffix}.html"
        out_file.write_text(html_text, encoding='utf-8')
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


def _escape_math(text: str) -> str:
    """Escape <, >, and & inside $…$ math, which the parser leaves raw for MathJax.

    Unescaped, `$a<b$` would open a tag before MathJax ever saw it. Escaped,
    the browser hands MathJax the characters exactly as typed.
    """
    segments = _MATH_SPLIT.split(text)
    for i in range(1, len(segments), 2):
        segments[i] = html.escape(segments[i], quote=False)
    return ''.join(segments)


def _place_image(src: Path, images_folder: Path) -> str:
    """Copy src into images_folder and return the file name it is found under there.

    An existing file is never overwritten. When the name is taken by a
    different image (two banks each with their own cartilage.jpg), the copy
    gets a numbered name, cartilage_2.jpg. The name is chosen by content, so
    every version of a build, each rendered separately, lands on the same one.
    """
    for n in range(1, 10_000):
        name = src.name if n == 1 else f'{src.stem}_{n}{src.suffix}'
        dst = images_folder / name
        if not dst.exists():
            shutil.copy2(src, dst)
            return name
        # The same file happens when the output folder is the bank's own folder.
        if dst.samefile(src) or filecmp.cmp(src, dst, shallow=False):
            return name
    raise RuntimeError(f"Too many different images named {src.name} in {images_folder}.")


def _number_label(qd: dict) -> str:
    """The question's number as the log names it: '7', or '4–6' for a group."""
    if 'q_num' in qd:
        return str(qd['q_num'])
    start, end = qd['start_num'], qd['end_num']
    return str(start) if start == end else f'{start}–{end}'


# ---------------------------------------------------------------------------
# HTML preparation
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
