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
    _rank = {'CC': 3, 'CX': 2, 'XX': 1, None: 0}
    best = None
    student_lower = student_text.strip().lower()
    for key_text in key_texts:
        ratio = _levenshtein_ratio(key_text.strip().lower(), student_lower)
        if ratio >= match_threshold:
            return 'CC'  # short-circuit on perfect match
        if partial_threshold is not None and ratio >= partial_threshold:
            grade = 'CX'
        else:
            grade = 'XX'
        if _rank[grade] > _rank[best]:
            best = grade
    # Explicitly-defined partial-credit answers (threshold 0.70)
    if partial_texts and _rank.get(best, 0) < _rank['CX']:
        for pt in partial_texts:
            ratio = _levenshtein_ratio(pt.strip().lower(), student_lower)
            if ratio >= 0.70:
                best = 'CX'
                break
    return best


def explain_suggestion(student_text: str, full: list, partial: list,
                       suggestion: str | None, partial_threshold: float | None = None) -> str:
    """
    One plain sentence for the grading window: what is suggested and why,
    naming the key answer the reading came closest to.
    """
    if not student_text:
        return 'No reading of the handwriting. Grade it by eye.'
    reading = student_text.strip().lower()
    scored = [(_levenshtein_ratio(a.strip().lower(), reading), a, 'full') for a in full if a]
    scored += [(_levenshtein_ratio(a.strip().lower(), reading), a, 'partial')
               for a in partial if a]
    if not scored:
        return 'The key has no answers for this question yet. Grade it by eye.'
    ratio, answer, kind = max(scored)
    alike = f'{round(ratio * 100)}% alike'
    if suggestion == 'CC':
        best = max(s for s in scored if s[2] == 'full')
        return (f'Suggested: correct. It matches “{best[1]}” ({round(best[0] * 100)}% alike). '
                f'Enter accepts.')
    if suggestion == 'CX':
        pmatch = [s for s in scored if s[2] == 'partial' and s[0] >= 0.70]
        if pmatch:
            best = max(pmatch)
            return (f'Suggested: partial. It matches the partial-credit answer “{best[1]}” '
                    f'({round(best[0] * 100)}% alike). Enter accepts.')
        best = max(s for s in scored if s[2] == 'full')
        return (f'Suggested: partial. It is {round(best[0] * 100)}% like “{best[1]}”, '
                f'within the partial-credit strictness. Enter accepts.')
    if suggestion == 'XX':
        return f'Suggested: wrong. The closest key answer is “{answer}” ({alike}). Enter accepts.'
    return f'No suggestion. The closest key answer is “{answer}” ({alike}). Grade it by eye.'
