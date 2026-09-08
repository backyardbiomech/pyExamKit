"""
Cloud AI OCR for pyExamKit — uses the Anthropic Claude API to transcribe
handwritten exam answers in batch.  Falls back gracefully when the
``anthropic`` library is not installed or no API key is configured.

Public API
----------
CONTEXT_PRESETS  : list[(label, context_string)] — preset context options for the UI
PRESET_LABELS    : list[str]
PRESET_VALUES    : dict[label, context_string | None]  (None = custom entry)

load_config()    -> dict
save_config(data)

recognize_batch(crops, student_ids, context, api_key, model) -> dict[str, str]
"""

import base64
import io
import json
import os
import re
from pathlib import Path

import numpy as np

# ── Persistent config ────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / '.pyexamkit_config.json'


def load_config() -> dict:
    """Load persisted settings (API key, etc.) from ~/.pyexamkit_config.json."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def save_config(data: dict) -> None:
    """Merge *data* into ~/.pyexamkit_config.json.

    The file is created owner-read/write only, and on POSIX an existing file
    is narrowed to the same. Creating it with the mode already set matters:
    writing at the default umask and chmod'ing afterwards leaves the API key
    world-readable in the gap between the two, however brief.

    O_CREAT's mode applies only when the file is new, so a config written by
    an older version of this app keeps its old permissions unless they are
    forced -- hence the explicit chmod as well. Windows ignores both; there
    the file's protection comes from the user profile's own ACL, which is why
    the dialogs describing this file do not promise a POSIX mode.
    """
    existing = load_config()
    existing.update(data)
    payload = json.dumps(existing, indent=2)
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(payload)
    if os.name == 'posix':
        CONFIG_PATH.chmod(0o600)


# ── Context presets ──────────────────────────────────────────────────────────

# Each entry is (display_label, context_string).
# A context_string of None means "use the custom text entry".
CONTEXT_PRESETS: list[tuple[str, str | None]] = [
    ("None (no context hint)", ""),
    ("Short answer / fill-in-the-blank",
     "Short-answer fill-in-the-blank exam. Answers are typically a word or short phrase."),
    ("Medical / anatomy exam",
     "Medical physiology exam. Answers are often anatomical terms, physiological processes, "
     "or measurements with units, possibly with equations."),
    ("Mathematics exam",
     "Mathematics exam. Answers are often equations, variables, or numerical values with units."),
    ("Computer science / CS exam",
     "Computer science exam. Answers are often algorithm names, data structures, code snippets, "
     "or technical terms."),
    ("Biology / life sciences exam",
     "Biology exam. Answers are often scientific terms, organism names, or biological processes."),
    ("Chemistry exam",
     "Chemistry exam. Answers are often chemical formulas, reaction names, or terminology."),
    ("Physics exam",
     "Physics exam. Answers are often equations, physical quantities, or concepts with units."),
    ("History / social studies exam",
     "History exam. Answers are often dates, names, events, or geographic locations."),
    ("Custom…", None),   # None signals the UI to show the custom text entry
]

PRESET_LABELS: list[str] = [label for label, _ in CONTEXT_PRESETS]
PRESET_VALUES: dict[str, str | None] = {label: val for label, val in CONTEXT_PRESETS}

# ── Encoding helpers ─────────────────────────────────────────────────────────

_BATCH_SIZE = 20   # max images per API call (stays well within token limits)


def _encode_array(arr: np.ndarray) -> tuple[str, str]:
    """Encode a numpy uint8 RGB array as a base64 JPEG string."""
    from PIL import Image as PILImage
    img = PILImage.fromarray(arr).convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    b64 = base64.standard_b64encode(buf.getvalue()).decode('utf-8')
    return b64, 'image/jpeg'


# ── Main recognition function ────────────────────────────────────────────────

def recognize_batch(
    crops: list[np.ndarray],
    student_ids: list[str],
    context: str = '',
    api_key: str = '',
    model: str = 'claude-haiku-4-5-20251001',
) -> dict[str, str]:
    """
    Transcribe a list of handwritten image crops via the Claude API.

    Parameters
    ----------
    crops       : list of numpy uint8 RGB arrays, one per student.
    student_ids : matching list of string IDs (used as dict keys in result).
    context     : optional subject-specific hint for the model.
    api_key     : Anthropic API key; falls back to saved config if empty.
    model       : Claude model identifier.

    Returns
    -------
    dict mapping student_id → transcribed text.  Returns {} on any failure.
    """
    try:
        import anthropic
    except ImportError:
        print('[AI OCR] The "anthropic" package is not installed. '
              'Run:  pip install anthropic', flush=True)
        return {}

    if not api_key:
        api_key = load_config().get('anthropic_api_key', '')
    if not api_key:
        print('[AI OCR] No API key configured. '
              'Open AI Settings in the main window.', flush=True)
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    system = (
        'You are a handwriting transcription assistant for a university exam autograder. '
        'You will be shown multiple labelled handwriting images. '
        'For each image, transcribe the handwritten text exactly as written without making any spelling corrections. '
        'The text is often a technical term, short phrase, or brief mathematical '
        'expression (1–6 words). '
        'Rules:\n'
        '- Respond with ONLY a JSON object mapping each label to the transcribed text.\n'
        '- Example: {"1": "cardiac output", "2": "O(n log n)"}\n'
        '- Preserve capitalisation, spelling, and spacing as written.\n'
        '- Use [?] for any word you cannot read.\n'
        '- No extra keys, no explanation, no markdown code fences.'
    )

    results: dict[str, str] = {}

    for chunk_start in range(0, len(crops), _BATCH_SIZE):
        chunk_crops = crops[chunk_start: chunk_start + _BATCH_SIZE]
        chunk_ids   = student_ids[chunk_start: chunk_start + _BATCH_SIZE]

        user_content: list[dict] = []
        if context:
            user_content.append({'type': 'text', 'text': f'Context: {context}'})

        for sid, crop in zip(chunk_ids, chunk_crops):
            b64, media_type = _encode_array(crop)
            user_content.append({'type': 'text', 'text': f'{sid}:'})
            user_content.append({
                'type': 'image',
                'source': {'type': 'base64', 'media_type': media_type, 'data': b64},
            })

        user_content.append({
            'type': 'text',
            'text': 'Return a JSON object mapping each label to its transcribed text.',
        })

        try:
            msg = client.messages.create(
                model=model,
                max_tokens=512,
                system=system,
                messages=[{'role': 'user', 'content': user_content}],
            )
            raw = msg.content[0].text.strip()
            # Strip any accidental markdown fences
            raw = re.sub(r'```[a-z]*\n?', '', raw).strip().rstrip('`')
            chunk_results = json.loads(raw)
            results.update(_clean_response(chunk_results, chunk_ids))
        except Exception as exc:
            print(f'[AI OCR] API call failed: {exc}', flush=True)

    return results


def _clean_response(parsed, sent_ids: list[str]) -> dict[str, str]:
    """Keep only the labels this batch actually asked about, as plain strings.

    A model can return a label that was never sent, a nested object instead of
    a string, or something that isn't a mapping at all. Callers index this
    result by student row and convert the label with int(), so letting an
    invented key through turns a bad transcription into a crash partway
    through a scan -- after the API call has already been paid for.
    """
    if not isinstance(parsed, dict):
        print(f'[AI OCR] Ignoring malformed response: expected a JSON object, '
              f'got {type(parsed).__name__}.', flush=True)
        return {}

    expected = set(sent_ids)
    cleaned: dict[str, str] = {}
    unknown: list[str] = []
    malformed: list[str] = []
    for label, text in parsed.items():
        label = str(label).strip()
        if label not in expected:
            unknown.append(label)
            continue
        # A number is a legitimate answer, so keep it as text. Anything
        # structured is the model ignoring the response format; drop it so the
        # field stays blank for review rather than showing a stringified dict.
        if isinstance(text, str):
            cleaned[label] = text
        elif isinstance(text, (int, float)) and not isinstance(text, bool):
            cleaned[label] = str(text)
        else:
            malformed.append(label)

    if unknown:
        print(f'[AI OCR] Ignoring {len(unknown)} unrecognized label(s) in the response: '
              f'{", ".join(sorted(unknown)[:5])}', flush=True)
    if malformed:
        print(f'[AI OCR] Ignoring {len(malformed)} label(s) whose transcription was not '
              f'text: {", ".join(sorted(malformed)[:5])}', flush=True)
    missing = expected - cleaned.keys()
    if missing:
        print(f'[AI OCR] No transcription returned for {len(missing)} image(s); '
              f'those will be blank for manual review.', flush=True)
    return cleaned
