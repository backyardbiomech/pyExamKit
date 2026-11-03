'''
What a school changes to make the sheets its own: the logo, the name of its
student ID, the letters written before an ID, and how many digits it has.

Kept in the per-user config beside the AI OCR key. Longwood's values are the
defaults, so nothing changes until someone sets these. The ID length chosen
here is what a sheet prints; the scanner reads each sheet's own length from
the squares printed on it (see sheet_layout.ID_LENGTH_CELLS), so a sheet
printed under another setting still reads correctly. The design record is
docs/dev/school-settings.md.
'''
from pathlib import Path

import ai_ocr

HERE = Path(__file__).resolve().parent
DEFAULT_LOGO = HERE / 'images' / 'longwood_logo.pdf'
DEFAULT_LABEL = 'Longwood ID number'
DEFAULT_PREFIX = 'L'
DEFAULT_DIGITS = 8
MIN_DIGITS, MAX_DIGITS = 4, 10
LOGO_TYPES = ('.pdf', '.png', '.jpg', '.jpeg')
# Stored for the bundled logo instead of its path, which moves when the app
# is reinstalled
USE_DEFAULT = 'default'

_LOGO, _LABEL, _PREFIX, _DIGITS = 'sheet_logo', 'id_label', 'canvas_id_prefix', 'id_digits'


def logo() -> Path | None:
    '''The logo file to print, or None for no logo. A file that has gone
    missing prints no logo rather than stopping the build.'''
    value = ai_ocr.load_config().get(_LOGO)
    if value is None or value == USE_DEFAULT:
        return DEFAULT_LOGO
    path = Path(value).expanduser() if value else None
    return path if path and path.exists() else None


def logo_setting() -> str | None:
    '''What is stored: None (never set), USE_DEFAULT, '' (no logo), or a path.'''
    return ai_ocr.load_config().get(_LOGO)


def id_label() -> str:
    return str(ai_ocr.load_config().get(_LABEL) or DEFAULT_LABEL)


def id_prefix() -> str:
    '''Printed before the ID boxes and put before each ID in the Canvas file.'''
    return str(ai_ocr.load_config().get(_PREFIX, DEFAULT_PREFIX))


def id_digits() -> int:
    try:
        n = int(ai_ocr.load_config().get(_DIGITS, DEFAULT_DIGITS))
    except (TypeError, ValueError):
        return DEFAULT_DIGITS
    return n if MIN_DIGITS <= n <= MAX_DIGITS else DEFAULT_DIGITS


def check(logo_path: str, digits) -> int:
    '''Validate what the settings dialog was given; returns the digit count.
    Raises ValueError with a message for the user.'''
    if logo_path and logo_path != USE_DEFAULT:
        p = Path(logo_path).expanduser()
        if p.suffix.lower() not in LOGO_TYPES:
            raise ValueError('The logo must be a PDF, PNG, or JPG file.')
        if not p.exists():
            raise ValueError(f'No logo file at {p}.')
    try:
        n = int(digits)
    except (TypeError, ValueError):
        raise ValueError('The ID length must be a whole number.') from None
    if not MIN_DIGITS <= n <= MAX_DIGITS:
        raise ValueError(f'The ID length must be {MIN_DIGITS} to {MAX_DIGITS} digits.')
    return n


def save(logo_path: str | None = None, label: str | None = None,
         prefix: str | None = None, digits: int | None = None) -> None:
    '''Store the settings given; None leaves one as it is. A logo of ''
    means no logo, and USE_DEFAULT the bundled one.'''
    data = {}
    if logo_path is not None:
        data[_LOGO] = str(logo_path)
    if label is not None:
        data[_LABEL] = label.strip()
    if prefix is not None:
        data[_PREFIX] = prefix.strip()
    if digits is not None:
        data[_DIGITS] = check('', digits)
    ai_ocr.save_config(data)
