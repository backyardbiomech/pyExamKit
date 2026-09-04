"""
exam_key_writer.py

Builds an exam key from an ExamVersion (pyExamPaper's build-side domain model)
and writes it through keyformat.py, the single place that knows the key CSV
format. Replaces pyExamPaper's key_generator.py, which wrote CSV rows
directly and predates keyformat.py.

Each MD question still puts the full question point value on every dropdown
row, and gradeResults sums per column, so a three-dropdown MD question scores
three times its intended value. That bug is preserved here, not fixed: the
fix is scoped to phase 3.5 alongside the OR/MT points-distribution rule it
reuses, and this module exists to move key-writing to keyformat.py without
changing behavior.
"""
from __future__ import annotations

from pathlib import Path

from models import ExamVersion, Question
from keyformat import save_key_file


def build_key_data(version: ExamVersion, default_points: float = 1.0) -> dict:
    """Translate an ExamVersion into the generic dict keyformat.py expects:
    bubble_answers, open_questions, metadata, point_values.

    SA questions produce an 'ignore' bubble placeholder (so gradeResults/
    markSheets skip that slot) plus an open question carrying the answers.
    MD questions produce one bubble row per dropdown, sequential. Every
    other question type produces a single bubble row.
    """
    bubble_answers: dict = {}
    open_questions: dict = {}
    point_values: dict = {}
    questions_to_skip: list[int] = []

    counter = 1
    for q in version.questions:
        if q.q_type == 'MD':
            pts = _effective_points(q, default_points)
            for dropdown in q.dropdowns:
                q_label = f"Q{counter:03d}"
                bubble_answers[q_label] = _dropdown_answer(dropdown)
                point_values[q_label] = pts
                counter += 1

        elif q.q_type == 'SA':
            pts = _effective_points(q, default_points)
            q_label = f"Q{counter:03d}"
            bubble_answers[q_label] = 'ignore'
            questions_to_skip.append(counter)
            full_ans = [a.text for a in q.answers if a.is_correct]
            part_ans = [a.text for a in q.answers if not a.is_correct]
            open_key = f"openQ_{counter}"
            open_questions[open_key] = {
                'full': full_ans,
                'partial': part_ans,
                'coords': None,
            }
            point_values[open_key] = pts
            counter += 1

        else:
            pts = _effective_points(q, default_points)
            q_label = f"Q{counter:03d}"
            bubble_answers[q_label] = _mc_answer(q)
            point_values[q_label] = pts
            counter += 1

    total_questions = counter - 1

    metadata: dict = {'num_questions': total_questions}
    if questions_to_skip:
        metadata['questions_to_skip'] = ','.join(str(n) for n in questions_to_skip)

    return {
        'bubble_answers': bubble_answers,
        'open_questions': open_questions,
        'metadata': metadata,
        'point_values': point_values,
    }


def save_key(version: ExamVersion, filepath: Path, default_points: float = 1.0) -> None:
    """Save the key CSV for one exam version to a file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    save_key_file(str(filepath), build_key_data(version, default_points))


# ---------------------------------------------------------------------------
# Helpers — ported unchanged from key_generator.py
# ---------------------------------------------------------------------------

def _mc_answer(q: Question) -> str:
    """Answer string for MC or MA questions.

    MC: single letter for the correct answer.
    MA: concatenated sorted letters for all correct answers (e.g. 'AC').
    """
    if q.q_type == 'MC':
        for i, ans in enumerate(q.answers):
            if ans.is_correct:
                return chr(ord('A') + i)
        return ''

    if q.q_type == 'MA':
        letters = sorted(
            chr(ord('A') + i)
            for i, ans in enumerate(q.answers)
            if ans.is_correct
        )
        return ''.join(letters)

    return ''


def _dropdown_answer(dropdown) -> str:
    """Answer letter for a single MD dropdown (single correct answer)."""
    for i, ans in enumerate(dropdown.answers):
        if ans.is_correct:
            return chr(ord('A') + i)
    return ''


def _effective_points(q: Question, default: float) -> float:
    """Return the per-question point value, falling back to default."""
    if q.points is not None:
        try:
            return float(q.points)
        except ValueError:
            pass
    return default
