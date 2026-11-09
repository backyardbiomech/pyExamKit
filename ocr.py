"""
OCR helpers for handwritten answer grading.
Local OCR has been removed — transcription is handled exclusively by Claude AI
(see ai_ocr.py).  attempt_ocr() is retained as a no-op stub so call sites that
check the AI result before falling back continue to compile unchanged.
"""
import numpy as np


def attempt_ocr(image_crop_array: np.ndarray) -> tuple:
    """Stub — local OCR removed.  Returns ('', 0.0) always."""
    return ('', 0.0)


def _levenshtein_ratio(a: str, b: str) -> float:
    """
    Normalized Levenshtein similarity: 1.0 = identical, 0.0 = completely different.
    Score = 1 - edit_distance / max(len(a), len(b)).
    Order-sensitive: single-character insertions, deletions, substitutions only.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return 1.0 - dp[n] / max(m, n)


def _normalized(text: str) -> str:
    return ' '.join(text.split()).lower()


# Similarity at which a reading counts as a listed partial-credit answer
LISTED_PARTIAL_MATCH = 0.70


def _closest(answers, reading: str) -> float:
    """Highest similarity of the normalized reading to any of answers."""
    return max((_levenshtein_ratio(_normalized(a), reading) for a in answers), default=0.0)


def exact_match(student_text: str, answers) -> bool:
    """
    True when the reading is one of answers word for word, ignoring only
    capitals and spacing.
    """
    reading = _normalized(student_text or '')
    return bool(reading) and any(reading == _normalized(a) for a in answers if a)


def exact_grade(student_text: str, full, partial) -> str | None:
    """
    The grade an answer may be given without the grader seeing it: 'CC' when
    the reading is a full-credit answer exactly, 'CX' when it is a
    partial-credit answer exactly, otherwise None. A near miss, a misspelling
    included, always goes to the grader.
    """
    if exact_match(student_text, full):
        return 'CC'
    if exact_match(student_text, partial):
        return 'CX'
    return None


def suggest_grade(student_text: str, key_texts,
                  conf: float,
                  conf_threshold: float = 0.20,
                  match_threshold: float = 0.80,
                  partial_texts=None,
                  partial_threshold: float | None = None) -> str | None:
    """
    Suggest a grade based on OCR.
    key_texts may be a single string or a list of acceptable answers (full credit).
    partial_texts, if given, is a list of answers that earn partial credit (CX).
    Similarity is measured with normalized Levenshtein edit distance (order-sensitive).
    A reading that is a key answer exactly takes that answer's grade; otherwise
    the listed answer it most resembles decides, so a near miss of a partial
    answer is not lifted to full credit by a similar full answer.
    partial_threshold (the strictness) is also a floor on every near match:
    at 1, only an exact match earns anything.
    Returns 'CC' (full credit), 'CX' (partial), 'XX' (none), or
    None when confidence is too low to suggest (defer to human grader).
    """
    if conf < conf_threshold or not student_text:
        return None
    if isinstance(key_texts, str):
        key_texts = [key_texts]
    key_texts = [k for k in key_texts if k]
    partial_texts = [p for p in (partial_texts or []) if p]
    if not key_texts and not partial_texts:
        return None
    exact = exact_grade(student_text, key_texts, partial_texts)
    if exact:
        return exact
    reading = _normalized(student_text)
    floor = partial_threshold or 0.0
    full = _closest(key_texts, reading)
    listed = _closest(partial_texts, reading)
    full_ok = full >= max(match_threshold, floor)
    listed_ok = listed >= max(LISTED_PARTIAL_MATCH, floor)
    if full_ok and not (listed_ok and listed > full):
        return 'CC'
    if listed_ok or (partial_threshold is not None and full >= partial_threshold):
        return 'CX'
    return 'XX' if key_texts else None


def explain_suggestion(student_text: str, full: list, partial: list,
                       suggestion: str | None, partial_threshold: float | None = None,
                       blank: bool = False) -> str:
    """
    One plain sentence for the grading window: what is suggested and why,
    naming the key answer the reading came closest to. blank is a box with
    no writing in it.
    """
    if blank:
        return 'Suggested: wrong. The box is blank. Enter accepts.'
    if not student_text:
        return 'No reading of the handwriting. Grade it by eye with C, P, or X.'
    reading = _normalized(student_text)
    scored = [(_levenshtein_ratio(_normalized(a), reading), a, 'full') for a in full if a]
    scored += [(_levenshtein_ratio(_normalized(a), reading), a, 'partial')
               for a in partial if a]
    if not scored:
        return 'The key has no answers for this question yet. Grade it by eye.'
    ratio, answer, kind = max(scored)
    alike = f'{round(ratio * 100)}% alike'
    if suggestion == 'CC':
        best = max(s for s in scored if s[2] == 'full')
        if exact_match(student_text, [best[1]]):
            return f'Suggested: correct. It matches “{best[1]}”. Enter accepts.'
        return (f'Suggested: correct. It is {round(best[0] * 100)}% like “{best[1]}”. '
                f'Enter accepts.')
    if suggestion == 'CX':
        bar = max(LISTED_PARTIAL_MATCH, partial_threshold or 0.0)
        pmatch = [s for s in scored if s[2] == 'partial' and s[0] >= bar]
        if pmatch:
            best = max(pmatch)
            if exact_match(student_text, [best[1]]):
                return (f'Suggested: partial. It matches the partial-credit answer “{best[1]}”. '
                        f'Enter accepts.')
            return (f'Suggested: partial. It is {round(best[0] * 100)}% like the partial-credit '
                    f'answer “{best[1]}”. Enter accepts.')
        best = max(s for s in scored if s[2] == 'full')
        return (f'Suggested: partial. It is {round(best[0] * 100)}% like “{best[1]}”, '
                f'within the partial-credit strictness. Enter accepts.')
    if suggestion == 'XX':
        return f'Suggested: wrong. The closest key answer is “{answer}” ({alike}). Enter accepts.'
    return f'No suggestion. The closest key answer is “{answer}” ({alike}). Grade it by eye.'
