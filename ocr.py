"""
OCR helpers for handwritten answer grading.
Local OCR has been removed — transcription is handled exclusively by Claude AI
(see ai_ocr.py).  attempt_ocr() is retained as a no-op stub so call sites that
check the AI result before falling back continue to compile unchanged.
"""
import difflib
import numpy as np


def attempt_ocr(image_crop_array: np.ndarray) -> tuple:
    """Stub — local OCR removed.  Returns ('', 0.0) always."""
    return ('', 0.0)


def suggest_grade(student_text: str, key_texts,
                  conf: float,
                  conf_threshold: float = 0.20,
                  match_threshold: float = 0.80,
                  partial_texts=None) -> str | None:
    """
    Suggest a grade based on OCR.
    key_texts may be a single string or a list of acceptable answers (full credit).
    partial_texts, if given, is a list of answers that earn partial credit (CX).
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
        ratio = difflib.SequenceMatcher(
            None, key_text.strip().lower(), student_lower
        ).ratio()
        if ratio >= match_threshold:
            return 'CC'  # short-circuit on perfect match
        grade = 'CX' if ratio >= 0.4 else 'XX'
        if _rank[grade] > _rank[best]:
            best = grade
    # Explicitly-defined partial-credit answers (threshold 0.70)
    if partial_texts and _rank.get(best, 0) < _rank['CX']:
        for pt in partial_texts:
            ratio = difflib.SequenceMatcher(
                None, pt.strip().lower(), student_lower
            ).ratio()
            if ratio >= 0.70:
                best = 'CX'
                break
    return best
