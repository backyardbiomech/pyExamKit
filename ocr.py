"""
OCR support for handwritten answer grading.
Primary:  TrOCR (microsoft/trocr-base-handwritten) — transformer model fine-tuned
          on handwriting, significantly better quality than Tesseract on scans.
          First use downloads ~1.3 GB model to ~/.cache/huggingface/.
Fallback: pytesseract with LSTM engine.
Both paths degrade gracefully — return ('', 0.0) if unavailable.
"""
import difflib
import sys
import numpy as np
from PIL import Image, ImageOps

# Module-level cache so the TrOCR model loads only once per session
_trocr_processor = None
_trocr_model = None


def attempt_ocr(image_crop_array: np.ndarray) -> tuple:
    """
    Try to OCR a numpy uint8 RGB image crop.
    Returns (recognized_text: str, confidence: float 0–1).
    Returns ('', 0.0) if OCR is unavailable or the image is unreadable.
    """
    if image_crop_array is None or image_crop_array.size == 0:
        return ('', 0.0)
    try:
        return _trocr_ocr(image_crop_array)
    except Exception as e:
        print(f'[OCR] TrOCR failed: {e}', flush=True)
    try:
        return _tesseract_ocr(image_crop_array)
    except Exception as e:
        print(f'[OCR] Tesseract failed: {e}', flush=True)
    return ('', 0.0)


def _preprocess(arr: np.ndarray) -> Image.Image:
    """Autocontrast + upscale to 384px tall (TrOCR input size is 384x384)."""
    img = Image.fromarray(arr).convert('L')
    img = ImageOps.autocontrast(img, cutoff=0)
    target_h = 384
    if img.height != target_h:
        scale = target_h / img.height
        img = img.resize((int(img.width * scale), target_h), Image.LANCZOS)
    return img.convert('RGB')


def _trocr_ocr(arr: np.ndarray) -> tuple:
    """TrOCR handwriting model — loads once and caches for the session."""
    global _trocr_processor, _trocr_model
    if _trocr_processor is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        print('[OCR] Loading TrOCR model (first use only)…', flush=True)
        _trocr_processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten')
        _trocr_model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten')
        print('[OCR] TrOCR ready.', flush=True)

    img = _preprocess(arr)
    pixel_values = _trocr_processor(images=img, return_tensors='pt').pixel_values
    generated_ids = _trocr_model.generate(pixel_values, max_new_tokens=40)
    text = _trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    if not text:
        return ('', 0.0)
    # TrOCR doesn't give per-token confidences; use a fixed mid confidence
    # so suggest_grade can still produce a suggestion when the text looks right
    return (text, 0.65)


def _tesseract_ocr(arr: np.ndarray) -> tuple:
    import pytesseract
    img = _preprocess(arr)
    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT,
        config='--psm 6 --oem 1'
    )
    words = [w for w, c in zip(data['text'], data['conf'])
             if str(c).lstrip('-').isdigit() and int(c) != -1 and w.strip()]
    confs = [max(0, int(c)) for c in data['conf']
             if str(c).lstrip('-').isdigit() and int(c) != -1]
    if not words:
        return ('', 0.0)
    avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return (' '.join(words), avg_conf)


def suggest_grade(student_text: str, key_text: str,
                  conf: float,
                  conf_threshold: float = 0.20,
                  match_threshold: float = 0.80) -> str | None:
    """
    Suggest a grade based on OCR.
    Returns 'CC' (full credit), 'CX' (partial), 'XX' (none), or
    None when confidence is too low to suggest (defer to human grader).
    """
    if conf < conf_threshold or not student_text or not key_text:
        return None
    ratio = difflib.SequenceMatcher(
        None, key_text.strip().lower(), student_text.strip().lower()
    ).ratio()
    if ratio >= match_threshold:
        return 'CC'
    if ratio >= 0.4:
        return 'CX'
    return 'XX'
