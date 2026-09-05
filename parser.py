"""
parser.py

Parse the markdown/text question bank files used by qtiConverter into Question objects.
Supports: MC (multiple choice), MA (multiple answer), MD (multiple dropdown), TF (true/false),
          SA (short answer), OR (ordering), MT (matching).
All other question types (ES, MB, CT, HS) are skipped with a warning.
"""
from __future__ import annotations

import re
from pathlib import Path

from models import Answer, Dropdown, MatchLeft, MatchRight, OrderItem, Question

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_MATH_SPLIT = re.compile(r'(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)')


def _process_formatting(text: str) -> str:
    """Convert markdown-style formatting to HTML tags.

    Handles bold, italic, superscript, subscript.
    Preserves $$...$$ math blocks unchanged so MathJax can render them.
    Escapes HTML special characters only outside math blocks.
    """
    segments = _MATH_SPLIT.split(text)
    result = []
    for i, seg in enumerate(segments):
        if i % 2 == 1:
            # Odd index → inside a $$...$$ math block; leave untouched
            result.append(seg)
        else:
            # Even index → plain text; apply formatting
            seg = re.sub(r'\*{2}([\W\w\s]+?)\*{2}', r'<strong>\1</strong>', seg)
            seg = re.sub(r'\*{1}([\W\w\s]+?)\*{1}', r'<em>\1</em>', seg)
            seg = re.sub(r'\^{1}([\W\w\s]+?)\^{1}', r'<sup>\1</sup>', seg)
            seg = re.sub(r'~{1}([\W\w\s]+?)~{1}', r'<sub>\1</sub>', seg)
            # Escape HTML special chars outside math blocks
            seg = seg.replace('&', '&amp;')
            seg = seg.replace('<', '&lt;').replace('>', '&gt;')
            # Restore HTML tags we just inserted (bold/italic/sup/sub)
            seg = re.sub(r'&lt;(/?(?:strong|em|sup|sub|br))&gt;', r'<\1>', seg)
            # Convert 3+ underscores to a styled blank span (SA fill-in-the-blank)
            seg = re.sub(r'_{3,}', '<span class="blank"></span>', seg)
            result.append(seg)
    return ''.join(result)


# ---------------------------------------------------------------------------
# Block pre-processing  (same logic as qtiConverterApp.loadBank)
# ---------------------------------------------------------------------------

def _preprocess(raw: str) -> list[str]:
    """Clean raw file text and split into question blocks."""
    data = raw.strip()
    # Remove trailing spaces/tabs from lines
    data = re.sub(r'[ \t]+\n', '\n', data, flags=re.MULTILINE)
    # Remove lines that begin with # (comments)
    data = re.sub(r'^#.*$', '', data, flags=re.MULTILINE)
    # Remove leading spaces/tabs from lines
    data = re.sub(r'^[ \t]+', '', data, flags=re.MULTILINE)
    # Collapse 3+ blank lines to 2
    data = re.sub(r'\n{3,}', '\n\n', data, flags=re.MULTILINE)
    return data.split('\n\n')


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_TYPE_LIST = {'MC', 'MA', 'MD', 'TF', 'SA', 'OR', 'MT'}
_ALL_TYPES = {'MC', 'MA', 'MT', 'SA', 'MD', 'MB', 'ES', 'NU', 'OR', 'TF', 'CT', 'HS'}


def _parse_header(lines: list[str]) -> tuple[str, list[str], str | None, list[str]]:
    """Extract question type, image paths, and point value from the optional header.

    Returns (q_type, image_paths, points, remaining_lines).
    Consumes up to 3 header lines before the question stem.
    """
    q_type = ''
    image_paths: list[str] = []
    points: str | None = None
    remaining = list(lines)

    # Up to 3 passes for the three optional header fields
    for _ in range(3):
        if not remaining:
            break
        line = remaining[0].strip()

        # Question type code
        if not q_type:
            m = re.match(r'^([A-Z]{2})$', line)
            if m and m.group(1) in _ALL_TYPES:
                q_type = m.group(1)
                remaining.pop(0)
                continue

        # Image line
        if not image_paths:
            m = re.match(r'^image:\s*(.+)$', line, re.IGNORECASE)
            if m:
                image_paths = [p.strip() for p in m.group(1).split(',') if p.strip()]
                remaining.pop(0)
                continue

        # Point value
        if points is None:
            m = re.match(r'^\(([\d.]+)[\s\w]*\)$', line)
            if m:
                points = m.group(1)
                remaining.pop(0)
                continue

    if not q_type:
        q_type = 'MC'

    return q_type, image_paths, points, remaining


# ---------------------------------------------------------------------------
# MC / MA parser
# ---------------------------------------------------------------------------

def _parse_mc(lines: list[str], q_type: str, image_paths: list[str],
              points: str | None, raw_block: str) -> Question | None:
    """Parse a multiple-choice or multiple-answer question block."""
    full_text = '\n'.join(lines)

    # Extract question stem: everything from 'N. ' or 'N) ' up to the first answer letter
    qreg = re.compile(r'^\d+[.)]\s{0,4}([\S\s]+?)(^(\*)?[A-Za-z][.)]\s)', re.MULTILINE)
    qmatch = qreg.search(full_text)
    if not qmatch:
        return None

    quest = qmatch.group(1).strip()
    # Remove common "select all that apply" prefixes authors add manually
    quest = re.sub(
        r'^select\s+all\s+that\s+apply[\s:–—-]*',
        '',
        quest,
        flags=re.IGNORECASE,
    ).strip()
    qend = qmatch.span(1)[1]
    atext = full_text[qend:]

    # Extract answers
    areg = re.compile(r'^(\*)?([A-Za-z])[.)]\s{0,4}([\S\s]+?)(?=^(\*)?[A-Za-z][.)]|\Z)',
                      re.MULTILINE)
    answers: list[Answer] = []
    for mat in areg.finditer(atext):
        is_correct = mat.group(1) is not None
        ans_text = mat.group(3).strip()
        img_match = re.match(r'^image:\s*(.+)$', ans_text, re.IGNORECASE)
        if img_match:
            answers.append(Answer(
                text='',
                is_correct=is_correct,
                image_path=img_match.group(1).strip(),
            ))
        else:
            answers.append(Answer(text=_process_formatting(ans_text), is_correct=is_correct))

    if not answers:
        return None

    # Auto-promote MC→MA if multiple correct answers found
    correct_count = sum(1 for a in answers if a.is_correct)
    if q_type == 'MC' and correct_count > 1:
        q_type = 'MA'

    return Question(
        q_type=q_type,
        text=_process_formatting(quest),
        answers=answers,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    )


# ---------------------------------------------------------------------------
# TF parser
# ---------------------------------------------------------------------------

def _parse_tf(lines: list[str], image_paths: list[str],
              points: str | None, raw_block: str) -> Question | None:
    """Parse a true/false question block.

    Expected format:
        1. Question stem text
        A: True   (or False — case-insensitive; no * needed)

    Rendered as a two-answer MC question with the stated value marked correct.
    """
    if not lines:
        return None

    # Extract stem
    m = re.match(r'^\d+[.)]\s{0,4}([\S\s]+?)$', lines[0])
    quest = m.group(1).strip() if m else lines[0].strip()

    # Find the answer line: A: True / A: False
    correct_value: str | None = None
    for line in lines[1:]:
        m = re.match(r'^\*?[Aa][.):]\s*(.+)$', line)
        if m:
            correct_value = m.group(1).strip().capitalize()  # 'True' or 'False'
            break

    if correct_value not in ('True', 'False'):
        return None

    answers = [
        Answer(text='True', is_correct=(correct_value == 'True')),
        Answer(text='False', is_correct=(correct_value == 'False')),
    ]

    return Question(
        q_type='MC',
        text=_process_formatting(quest),
        answers=answers,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    )


# ---------------------------------------------------------------------------
# SA parser
# ---------------------------------------------------------------------------

def _parse_sa(lines: list[str], image_paths: list[str],
              points: str | None, raw_block: str) -> Question | None:
    """Parse a short-answer question block.

    Answer lines (A., B., etc.) list acceptable answers.
    Starred (*A.) = full credit; unstarred = partial credit.
    If no answers are starred, all are treated as full credit.
    """
    if not lines:
        return None

    full_text = '\n'.join(lines)

    # Extract stem: everything from 'N. ' up to the first answer letter (or end)
    qreg = re.compile(r'^\d+[.)]\s{0,4}([\S\s]+?)(?=^(\*)?[A-Za-z][.)]\s|\Z)', re.MULTILINE)
    qmatch = qreg.search(full_text)
    if qmatch:
        quest = qmatch.group(1).strip()
        qend = qmatch.span(1)[1]
        atext = full_text[qend:]
    else:
        m = re.match(r'^\d+[.)]\s{0,4}([\S\s]+?)$', lines[0])
        quest = m.group(1).strip() if m else lines[0].strip()
        atext = ''

    if not quest:
        return None

    answers: list[Answer] = []
    if atext:
        areg = re.compile(
            r'^(\*)?([A-Za-z])[.)]\s{0,4}([\S\s]+?)(?=^(\*)?[A-Za-z][.)]|\Z)',
            re.MULTILINE
        )
        raw_answers = [(bool(m.group(1)), m.group(3).strip()) for m in areg.finditer(atext)]
        any_starred = any(starred for starred, _ in raw_answers)
        for starred, text in raw_answers:
            # None starred → all full credit; some starred → starred=full, unstarred=partial
            is_correct = True if not any_starred else starred
            # Store answer text as-is (no HTML processing): SA answers are plain-text
            # comparison values used by pyExamKit; HTML-escaping them corrupts the match.
            answers.append(Answer(text=text, is_correct=is_correct))

    return Question(
        q_type='SA',
        text=_process_formatting(quest),
        answers=answers,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    )


# ---------------------------------------------------------------------------
# MD parser
# ---------------------------------------------------------------------------

def _parse_md(lines: list[str], image_paths: list[str],
              points: str | None, raw_block: str) -> Question | None:
    """Parse a multiple-dropdown question block."""
    if not lines:
        return None

    # First line is the question stem
    stem_line = lines[0]
    m = re.match(r'^\d+[.)]\s{0,4}([\S\s]+?)$', stem_line)
    quest = m.group(1).strip() if m else stem_line.strip()

    # Find dropdown names from the stem (e.g. [drop1], [8t])
    drop_names_ordered = list(dict.fromkeys(re.findall(r'\[(\w+)\]', quest)))

    if not drop_names_ordered:
        return None

    # Build dropdown answer dicts
    drops: dict[str, Dropdown] = {name: Dropdown(name=name) for name in drop_names_ordered}

    for line in lines[1:]:
        parts = line.split(':', 1)
        if len(parts) < 2:
            continue
        prefix = parts[0]
        ans_text = parts[1].strip()

        is_correct = prefix.startswith('*')
        drop_name = prefix.lstrip('*').strip()

        if drop_name in drops:
            drops[drop_name].answers.append(
                Answer(text=_process_formatting(ans_text), is_correct=is_correct)
            )

    dropdowns = [drops[name] for name in drop_names_ordered if drops[name].answers]
    if not dropdowns:
        return None

    return Question(
        q_type='MD',
        text=_process_formatting(quest),
        dropdowns=dropdowns,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    )


# ---------------------------------------------------------------------------
# OR parser
# ---------------------------------------------------------------------------

_OR_MAX_ITEMS = 6
_OR_MIN_ITEMS = 2


def _parse_or(lines: list[str], image_paths: list[str], points: str | None,
              raw_block: str, q_index: int, fname: str) -> tuple[Question | None, str | None]:
    """Parse an ordering question block.

    Returns (question, warning). warning is set (and question is None) when
    the block is structurally fine but can't fit the six-bubble answer sheet,
    or when its rank numbers aren't a clean 1..N sequence; None/None falls
    back to parse_file's generic "could not parse" message.
    """
    if not lines:
        return None, None

    stem_line = lines[0]
    m = re.match(r'^\d+[.)]\s{0,4}([\S\s]+?)$', stem_line)
    quest = m.group(1).strip() if m else stem_line.strip()

    top_label = ''
    bottom_label = ''
    items: list[OrderItem] = []
    for line in lines[1:]:
        m = re.match(r'^toplabel:\s*(.+)$', line, re.IGNORECASE)
        if m:
            top_label = _process_formatting(m.group(1).strip())
            continue
        m = re.match(r'^bottomlabel:\s*(.+)$', line, re.IGNORECASE)
        if m:
            bottom_label = _process_formatting(m.group(1).strip())
            continue
        m = re.match(r'^(\d+):\s*(.+)$', line)
        if m:
            items.append(OrderItem(text=_process_formatting(m.group(2).strip()), rank=int(m.group(1))))

    if not items:
        return None, None

    items.sort(key=lambda it: it.rank)

    if len(items) > _OR_MAX_ITEMS:
        return None, (f"Block {q_index} in {fname}: ordering question has {len(items)} items; "
                       f"the answer sheet allows at most {_OR_MAX_ITEMS}. Skipped.")
    if len(items) < _OR_MIN_ITEMS:
        return None, (f"Block {q_index} in {fname}: ordering question has only {len(items)} "
                       f"item(s); an ordering needs at least {_OR_MIN_ITEMS}. Skipped.")

    # Ranks must be exactly 1..N with no gaps or repeats. The key writer maps
    # rank -> display letter by looking up every rank from 1 to N, so a bank
    # numbered from 0, missing a number, or repeating one would otherwise
    # raise KeyError partway through generating the exam.
    ranks = [it.rank for it in items]
    if ranks != list(range(1, len(items) + 1)):
        return None, (f"Block {q_index} in {fname}: ordering question is numbered "
                       f"{', '.join(str(r) for r in ranks)}; items must be numbered "
                       f"1 to {len(items)} with no gaps or repeats. Skipped.")

    return Question(
        q_type='OR',
        text=_process_formatting(quest),
        order_items=items,
        order_top_label=top_label,
        order_bottom_label=bottom_label,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    ), None


# ---------------------------------------------------------------------------
# MT parser
# ---------------------------------------------------------------------------

_MT_LEFT_RE = re.compile(r'^\[(\w+)\](\w+):\s*(.+)$')
_MT_RIGHT_RE = re.compile(r'^(\w+):\s*(.+)$')


def _parse_mt(lines: list[str], image_paths: list[str], points: str | None,
              raw_block: str, q_index: int, fname: str) -> tuple[Question | None, str | None]:
    """Parse a matching question block.

    Returns (question, warning), same contract as _parse_or.
    """
    if not lines:
        return None, None

    stem_line = lines[0]
    m = re.match(r'^\d+[.)]\s{0,4}([\S\s]+?)$', stem_line)
    quest = m.group(1).strip() if m else stem_line.strip()

    lefts: list[MatchLeft] = []
    rights: dict[str, str] = {}  # label -> text, insertion order preserved

    for line in lines[1:]:
        m = _MT_LEFT_RE.match(line)
        if m:
            right_label, _left_name, text = m.group(1), m.group(2), m.group(3).strip()
            lefts.append(MatchLeft(text=_process_formatting(text), correct_label=right_label))
            continue
        m = _MT_RIGHT_RE.match(line)
        if m:
            label, text = m.group(1), m.group(2).strip()
            rights[label] = _process_formatting(text)
            continue

    if not lefts:
        return None, f"Block {q_index} in {fname}: matching question has no left-side items. Skipped."

    for left in lefts:
        if left.correct_label not in rights:
            return None, (f"Block {q_index} in {fname}: matching question references right-side "
                           f"label '{left.correct_label}', which has no matching right entry. Skipped.")

    match_rights = [MatchRight(label=label, text=text) for label, text in rights.items()]

    return Question(
        q_type='MT',
        text=_process_formatting(quest),
        match_lefts=lefts,
        match_rights=match_rights,
        image_paths=image_paths,
        points=points,
        source_text=raw_block,
    ), None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(filepath: Path) -> tuple[list[Question], list[str]]:
    """Parse a question bank file and return (questions, warnings).

    Supports MC, MA, MD, SA, TF, OR, and MT question types.
    Other types are skipped and reported in the warnings list.
    """
    with filepath.open(encoding='utf-8-sig') as f:
        raw = f.read()

    blocks = _preprocess(raw)
    questions: list[Question] = []
    warnings: list[str] = []
    q_index = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [line for line in block.split('\n') if line.strip()]
        if not lines:
            continue

        q_index += 1
        q_type, image_paths, points, remaining = _parse_header(lines)

        if q_type not in _TYPE_LIST:
            warnings.append(
                f"Block {q_index}: question type '{q_type}' is not supported "
                f"(only MC, MA, MD, SA, TF, OR, MT). Skipped."
            )
            continue

        warn: str | None = None
        if q_type in ('MC', 'MA'):
            q = _parse_mc(remaining, q_type, image_paths, points, block)
        elif q_type == 'TF':
            q = _parse_tf(remaining, image_paths, points, block)
        elif q_type == 'SA':
            q = _parse_sa(remaining, image_paths, points, block)
        elif q_type == 'OR':
            q, warn = _parse_or(remaining, image_paths, points, block, q_index, filepath.name)
        elif q_type == 'MT':
            q, warn = _parse_mt(remaining, image_paths, points, block, q_index, filepath.name)
        else:  # MD
            q = _parse_md(remaining, image_paths, points, block)

        if q is None:
            warnings.append(warn or f"Block {q_index}: could not parse question. Skipped.")
            continue

        questions.append(q)

    return questions, warnings
