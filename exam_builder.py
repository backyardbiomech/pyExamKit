"""
exam_builder.py

Assembles ExamVersion objects from parsed question pools or a single exact file.
Handles random sampling, question shuffling, answer shuffling, and MD expansion.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from pathlib import Path

from models import Answer, ExamVersion, Question
from parser import parse_file


@dataclass
class PoolConfig:
    filepath: Path
    count: int             # number of questions to randomly select from this file
    points: float | None = None  # per-pool pts/question override (None = use global default)


@dataclass
class BuildConfig:
    title: str
    course: str
    num_versions: int
    shuffle_questions: bool
    shuffle_answers: bool
    exact_file: Path | None = None       # use all questions from one file
    pools: list[PoolConfig] = field(default_factory=list)
    version_question: bool = False       # append a "Fill in bubble X" version ID question
    version_question_position: str = 'last'  # 'last' or 'first'
    default_points: float = 1.0             # fallback points per question if not set in source
    same_questions: bool = False            # if True, all versions draw from the same question sample


class BuildError(Exception):
    pass


# The printed answer sheet has 150 numbered question slots; init_functions
# .makeAreaDict lays them out against fixed coordinates and runs off the
# bottom of the aligned image past roughly 151, so anything beyond this can
# be printed on the exam but never bubbled or graded.
MAX_QUESTION_SLOTS = 150

# The answer sheets shipped in images/, smallest first.
ANSWER_SHEET_SIZES = (30, 60, 90, 120, 150)


def slot_count(q: Question) -> int:
    """Answer-sheet slots one question occupies.

    Most questions take one. MD, OR, and MT each take one per dropdown,
    ordered item, or left-hand item, which is why an exam's slot count runs
    ahead of its question count as soon as those types are used.
    """
    if q.q_type == 'MD':
        return len(q.dropdowns)
    if q.q_type == 'OR':
        return len(q.order_items)
    if q.q_type == 'MT':
        return len(q.match_lefts)
    return 1


def answer_sheet_for(slots: int) -> int | None:
    """Smallest shipped answer sheet that fits `slots`, or None if none does."""
    return next((size for size in ANSWER_SHEET_SIZES if slots <= size), None)


class ExamBuilder:
    def build(self, config: BuildConfig) -> tuple[list[ExamVersion], list[str]]:
        """Build exam versions according to config.

        Returns (versions, all_warnings).
        """
        all_warnings: list[str] = []

        if config.exact_file:
            source_folder = config.exact_file.parent
            base_questions, warnings = parse_file(config.exact_file)
            all_warnings.extend(warnings)
            base_questions, trim_warnings = _trim_and_filter(base_questions, config.exact_file.name)
            all_warnings.extend(trim_warnings)
            pool_sources = [(base_questions, None, source_folder, None)]  # None count = use all
        else:
            pool_sources = []
            source_folder = None
            for pool in config.pools:
                qs, warnings = parse_file(pool.filepath)
                all_warnings.extend(warnings)
                qs, trim_warnings = _trim_and_filter(qs, pool.filepath.name)
                all_warnings.extend(trim_warnings)
                if pool.count > len(qs):
                    all_warnings.append(
                        f"Pool '{pool.filepath.name}': requested {pool.count} questions "
                        f"but only {len(qs)} available. Using all {len(qs)}."
                    )
                pool_sources.append((qs, pool.count, pool.filepath.parent, pool.points))

        versions: list[ExamVersion] = []

        # When same_questions is requested, sample once and reuse across versions.
        shared_sample: list[Question] | None = None
        if config.same_questions:
            shared_sample = []
            for (pool_qs, count, folder, pool_pts) in pool_sources:
                pool_copy = copy.deepcopy(pool_qs)
                if count is None:
                    chosen = pool_copy
                else:
                    k = min(count, len(pool_copy))
                    chosen = random.sample(pool_copy, k)
                for q in chosen:
                    if pool_pts is not None and q.points is None:
                        q.points = str(pool_pts)
                    q.source_folder = folder
                shared_sample.extend(chosen)

        for v in range(1, config.num_versions + 1):
            selected: list[Question] = []

            if shared_sample is not None:
                # Deep-copy so each version can shuffle independently
                selected = copy.deepcopy(shared_sample)
            else:
                for (pool_qs, count, folder, pool_pts) in pool_sources:
                    pool_copy = copy.deepcopy(pool_qs)
                    if count is None:
                        chosen = pool_copy
                    else:
                        k = min(count, len(pool_copy))
                        chosen = random.sample(pool_copy, k)
                    for q in chosen:
                        if pool_pts is not None and q.points is None:
                            q.points = str(pool_pts)
                        q.source_folder = folder
                    selected.extend(chosen)

            if config.shuffle_questions:
                random.shuffle(selected)

            # Optionally shuffle answers (MD shuffles within each dropdown).
            # Diagram-letter alignment is applied unconditionally so that
            # bubble A always matches label A on the diagram even when
            # shuffle_answers is False.
            expanded: list[Question] = []
            for q in selected:
                if config.shuffle_answers:
                    q = _shuffle_answers(q)
                _finalize_or_mt(q, config.shuffle_questions)
                _align_diagram_letters(q)
                expanded.append(q)

            # Determine source_folder for this version
            # If multiple pools, we use the parent of the first pool for image resolution
            # (each question carries its own source_text; GUI handles image copying separately)
            if config.exact_file:
                ver_source_folder = config.exact_file.parent
            elif config.pools:
                ver_source_folder = config.pools[0].filepath.parent
            else:
                ver_source_folder = Path('.')

            versions.append(ExamVersion(
                title=config.title,
                course=config.course,
                version_num=v,
                questions=expanded,
                source_folder=ver_source_folder,
            ))

        # Append / prepend version identifier question if requested
        if config.version_question:
            for version in versions:
                vq = _make_version_question(version.version_letter)
                if config.version_question_position == 'first':
                    version.questions.insert(0, vq)
                else:
                    version.questions.append(vq)

        # Versions can differ in slot count when each draws its own random
        # sample, so warn against the worst one.
        worst = max(sum(slot_count(q) for q in v.questions) for v in versions)
        if worst > MAX_QUESTION_SLOTS:
            all_warnings.append(
                f"This exam needs {worst} answer-sheet slots, but the printed sheet has "
                f"only {MAX_QUESTION_SLOTS}. Questions past {MAX_QUESTION_SLOTS} can be "
                f"printed but never bubbled or graded. Ordering, matching, and "
                f"multi-dropdown questions each take one slot per item, so the slot count "
                f"runs ahead of the question count -- drop questions or shorten those."
            )

        return versions, all_warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_version_question(version_letter: str) -> Question:
    """Create a synthetic MC question that identifies the exam version.

    Students are instructed to fill in a specific bubble (A for version A, etc.).
    Choices run A–E, or far enough to reach the version letter when that letter
    is F. They never run past F: the answer sheet has six bubbles per question,
    so a seventh choice would be unmarkable and ungradeable.
    """
    letters = 'ABCDEF'
    if version_letter not in letters:
        raise BuildError(
            f'Version {version_letter} cannot be encoded: the answer sheet has six '
            f'bubbles per question, so versions stop at {letters[-1]}.'
        )
    # Show choices A–E so there is always a superset of common version letters
    num_choices = max(5, letters.index(version_letter) + 1)
    # All choices give the same instruction so students aren't confused by
    # options pointing to different bubbles.
    answers = [
        Answer(text=f'Fill in bubble {version_letter}', is_correct=(letter == version_letter))
        for letter in letters[:num_choices]
    ]
    return Question(
        q_type='MC',
        text=f'EXAM VERSION — Fill in the bubble for version <strong>{version_letter}</strong>.',
        answers=answers,
        points='0',
        source_text='',
    )


def _shuffle_answers(q: Question) -> Question:
    """Return a copy of the question with answers (and dropdown answers) shuffled."""
    q = copy.deepcopy(q)
    if q.q_type in ('MC', 'MA'):
        random.shuffle(q.answers)
    elif q.q_type == 'MD':
        for dropdown in q.dropdowns:
            random.shuffle(dropdown.answers)
    return q


def _finalize_or_mt(q: Question, shuffle_lefts: bool) -> None:
    """Assign OR/MT their display order in-place.

    OR items and MT rights are both scrambled unconditionally, regardless of
    shuffle_answers. The source format lists an ordering's items in true-answer
    order, and habitually declares a matching question's lefts in the same
    order as the rights they point at, so leaving either unscrambled prints
    the answer key as the question — a diagonal A, B, C, ... down the page.
    This is a deliberate departure from how MC/MA/MD treat that setting.

    MT's left column becomes the exam's own numbered question slots (see the
    HTML template) rather than a choice list, so it follows shuffle_questions.
    """
    if q.q_type == 'OR':
        random.shuffle(q.order_items)
    elif q.q_type == 'MT':
        random.shuffle(q.match_rights)
        if shuffle_lefts:
            random.shuffle(q.match_lefts)


def _align_diagram_letters(q: Question) -> None:
    """Sort answer lists in-place when every option is a single uppercase letter.

    When all answer texts are lone letters (e.g. "A", "B", "C", "D") the
    choices point to labels on a diagram.  Sorting them alphabetically ensures
    bubble A always matches label A on the diagram, regardless of the order
    they appear in the source file or after shuffling.
    """
    if q.q_type in ('MC', 'MA'):
        if _answers_are_diagram_letters(q.answers):
            q.answers.sort(key=lambda a: a.text.strip())
    elif q.q_type == 'MD':
        for dropdown in q.dropdowns:
            if _answers_are_diagram_letters(dropdown.answers):
                dropdown.answers.sort(key=lambda a: a.text.strip())


def _answers_are_diagram_letters(answers: list[Answer]) -> bool:
    """Return True if every answer text is a single uppercase letter (A–Z).

    Image-only answers (empty text) are ignored; if *all* answers are
    image-only the function returns False.
    """
    texts = [a.text.strip() for a in answers if a.text.strip()]
    return bool(texts) and all(len(t) == 1 and t.isupper() for t in texts)


def _trim_mc_answers(q: Question, max_choices: int = 6) -> Question:
    """Trim MC/MA questions to at most max_choices answers.

    The correct answer is always kept; wrong answers are randomly sampled to
    fill the remaining slots.  Trimming is applied once at load time so every
    exam version sees the same answer subset (order may still differ when
    shuffle_answers is enabled).
    """
    if q.q_type not in ('MC', 'MA'):
        return q
    if len(q.answers) <= max_choices:
        return q
    q = copy.deepcopy(q)
    correct = [a for a in q.answers if a.is_correct]
    wrong = [a for a in q.answers if not a.is_correct]
    slots_for_wrong = max_choices - len(correct)
    if slots_for_wrong <= 0:
        q.answers = correct[:max_choices]
    else:
        q.answers = correct + random.sample(wrong, min(slots_for_wrong, len(wrong)))
    return q


def _trim_mt_rights(q: Question, max_rights: int = 6) -> tuple[Question, str | None]:
    """Trim an MT question's right-side options to at most max_rights.

    Mirrors _trim_mc_answers: every right that is some left's correct answer
    is kept unconditionally; distractors are randomly sampled to fill the
    remaining slots. If the required (non-droppable) rights alone already
    exceed max_rights, trimming can't help -- returns a warning instead of
    silently leaving the question over the sheet's limit.
    """
    if q.q_type != 'MT':
        return q, None
    if len(q.match_rights) <= max_rights:
        return q, None
    q = copy.deepcopy(q)
    required_labels = {left.correct_label for left in q.match_lefts}
    required = [r for r in q.match_rights if r.label in required_labels]
    distractors = [r for r in q.match_rights if r.label not in required_labels]
    slots_for_distractors = max_rights - len(required)
    if slots_for_distractors <= 0:
        q.match_rights = required
    else:
        q.match_rights = required + random.sample(
            distractors, min(slots_for_distractors, len(distractors))
        )
    if len(q.match_rights) > max_rights:
        return q, (f"matching question \"{q.text[:60]}\" has {len(q.match_rights)} right-side "
                   f"options after trimming distractors, exceeding the {max_rights}-option "
                   f"sheet limit. Skipped.")
    return q, None


def _trim_and_filter(questions: list[Question], fname: str) -> tuple[list[Question], list[str]]:
    """Apply MC/MA and MT trimming to a freshly-parsed pool, dropping any
    question that still can't fit the answer sheet even after trimming."""
    kept: list[Question] = []
    warnings: list[str] = []
    for q in questions:
        q = _trim_mc_answers(q)
        q, warn = _trim_mt_rights(q)
        if warn:
            warnings.append(f"'{fname}': {warn}")
            continue
        kept.append(q)
    return kept, warnings



