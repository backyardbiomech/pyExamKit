"""
renderer.py

Renders ExamVersion objects to HTML and Markdown formats.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from collections import Counter

from models import ExamVersion, Question

_TEMPLATES_DIR = Path(__file__).parent / 'templates'


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape([]),  # We manage escaping ourselves
        keep_trailing_newline=True,
    )
    # Add a 'basename' filter for image path resolution in templates
    env.filters['basename'] = lambda p: Path(p).name
    return env


class ExamRenderer:
    def __init__(self) -> None:
        self._env = _jinja_env()

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def to_html(self, version: ExamVersion, output_folder: Path, total_versions: int = 1, default_points: float = 1.0) -> Path:
        """Render version to HTML, copy images, and save the file.

        Returns the path to the saved HTML file.
        """
        output_folder.mkdir(parents=True, exist_ok=True)
        images_folder = output_folder / 'images'
        images_folder.mkdir(exist_ok=True)

        # Copy images from source_folder into output/images/
        for q in version.questions:
            q_folder = q.source_folder or version.source_folder
            for img_path in q.image_paths:
                src = q_folder / img_path
                if src.exists():
                    shutil.copy2(str(src), str(images_folder / src.name))
            for ans in q.answers:
                if ans.image_path:
                    src = q_folder / ans.image_path
                    if src.exists():
                        shutil.copy2(str(src), str(images_folder / src.name))

        # Compute the most-common effective point value for the header note
        mode_pts = _compute_default_pts(version.questions, default_points)
        default_pts_label = _fmt_pts(mode_pts) if mode_pts is not None else None

        # Build render-ready question dicts (handles MD grouping and numbering)
        questions = _prepare_questions_for_html(version.questions, default_points, mode_pts)

        # Hide version letter when only one version is being produced,
        # or when a version indicator question is already embedded in the exam
        hide_version = total_versions <= 1 or any(
            q.text.startswith('EXAM VERSION') for q in version.questions
        )

        template = self._env.get_template('exam.html')
        html = template.render(
            version=version,
            questions=questions,
            hide_version=hide_version,
            default_pts_label=default_pts_label,
        )  # default_pts_label is None when there is no clear single point value

        out_file = output_folder / f"{_safe_name(version.title)}_v{version.version_letter}.html"
        out_file.write_text(html, encoding='utf-8')
        return out_file

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
            f"# {version.title} \u2014 Version {version.version_letter} "
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


def _prepare_questions_for_html(questions: list[Question], build_default: float, mode_pts: float | None) -> list[dict]:
    """Convert Question objects into render-ready dicts for the Jinja2 template.

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
                    f'<strong>(Question\u00a0{actual_num})</strong>',
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
    text = re.sub(r'<span\s+class="blank"[^>]*></span>', '________', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    return text


def safe_name(name: str) -> str:
    """Convert a title to a filesystem-safe name."""
    return re.sub(r'[^\w\-_.]', '_', name)


# Keep private alias for internal use
_safe_name = safe_name
