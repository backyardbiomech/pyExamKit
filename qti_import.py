"""
qti_import.py

Convert a Canvas QTI export (a .zip downloaded from Canvas) into the
markdown/text question-bank format that parser.py reads.

Canvas exports New Quizzes in the *classic* QTI 1.2 wrapper
(`imsqti_xmlv1p2`), the same one classic quizzes use, so one reader covers
both. Everything here is driven by the shape of the XML -- the number of
`response_lid` blocks, whether `rcardinality` is Single/Multiple/Ordered,
which `varequal` idents a scoring `respcondition` names -- rather than by
Canvas's internal identifier strings, which differ between the two quiz
engines and between exports.

The `question_type` metadata field routes each item to a writer. Types
pyExamKit's answer sheet cannot represent (essay, numerical, fill-in-
multiple-blanks, categorization, hot spot) are skipped by name so the
report says what was dropped.

Images referenced as $IMS-CC-FILEBASE$/... are extracted from the zip into
a folder beside the output file and become `image:` header lines, whose
paths parser.py resolves relative to the bank file's own folder.
"""
from __future__ import annotations

import html as _html
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

# Canvas's own question_type strings -> pyExamKit's two-letter codes.
TYPE_MAP = {
    'multiple_choice_question': 'MC',
    'multiple_answers_question': 'MA',
    'true_false_question': 'TF',
    'short_answer_question': 'SA',
    'multiple_dropdowns_question': 'MD',
    'matching_question': 'MT',
    'ordering_question': 'OR',
}

# Recognized but unrepresentable on a six-bubble answer sheet. Named here so
# the warning can say what the item was instead of "unknown type".
SKIPPED_TYPES = {
    'essay_question': 'essay',
    'numerical_question': 'numerical',
    'fill_in_multiple_blanks_question': 'fill-in-multiple-blanks',
    'calculated_question': 'calculated/formula',
    'file_upload_question': 'file upload',
    'text_only_question': 'text-only (no answer)',
    'categorization_question': 'categorization',
    'hot_spot_question': 'hot spot',
}

_FILEBASE_RE = re.compile(r'^(?:\$IMS-CC-FILEBASE\$|%24IMS-CC-FILEBASE%24)/*', re.IGNORECASE)


@dataclass
class ImportResult:
    """What one conversion produced. `text` is the bank file's content."""
    text: str
    titles: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)   # two-letter code -> n
    warnings: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)        # paths written, relative to out file

    @property
    def total(self) -> int:
        return sum(self.counts.values())


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _strip_ns(elem: ET.Element) -> ET.Element:
    """Drop XML namespaces in place so every find() below can use bare tags.

    Canvas writes the QTI namespace on the root, but hand-made and
    older exports sometimes omit it; stripping makes both parse the same.
    """
    for el in elem.iter():
        if isinstance(el.tag, str) and el.tag.startswith('{'):
            el.tag = el.tag.split('}', 1)[1]
    return elem


def _metadata(item: ET.Element) -> dict[str, str]:
    """itemmetadata fieldlabel -> fieldentry."""
    meta = {}
    for f in item.iter('qtimetadatafield'):
        label = f.find('fieldlabel')
        entry = f.find('fieldentry')
        if label is not None and label.text:
            meta[label.text.strip()] = (entry.text or '').strip() if entry is not None else ''
    return meta


def _mattext(parent: ET.Element) -> str:
    """Raw HTML from the first <material>/<mattext> directly under parent."""
    material = parent.find('material')
    if material is None:
        return ''
    return ''.join((mt.text or '') for mt in material.findall('mattext'))


def _correct_map(item: ET.Element) -> dict[str, list[str]]:
    """respident -> answer idents a scoring respcondition marks correct.

    A condition counts as scoring when its setvar assigns a positive value,
    which covers both `action="Set"` (whole-question, MC/MA/SA) and
    `action="Add"` (per-blank partial credit, MD/MT). varequal nodes nested
    inside a <not> are the distractors an MA condition explicitly excludes,
    so they are dropped. Order is preserved for ordering questions.
    """
    correct: dict[str, list[str]] = {}
    for rc in item.iter('respcondition'):
        setvar = rc.find('setvar')
        if setvar is None:
            continue
        try:
            if float((setvar.text or '0').strip()) <= 0:
                continue
        except ValueError:
            continue
        cv = rc.find('conditionvar')
        if cv is None:
            continue
        negated = {id(ve) for nt in cv.iter('not') for ve in nt.iter('varequal')}
        for ve in cv.iter('varequal'):
            if id(ve) in negated:
                continue
            respident = ve.get('respident') or 'response1'
            correct.setdefault(respident, []).append((ve.text or '').strip())
    return correct


# ---------------------------------------------------------------------------
# HTML -> bank text
# ---------------------------------------------------------------------------

_IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
_SRC_RE = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')

_INLINE_MARKERS = [
    (re.compile(r'</?(?:strong|b)\b[^>]*>', re.IGNORECASE), '**'),
    (re.compile(r'</?(?:em|i)\b[^>]*>', re.IGNORECASE), '*'),
    (re.compile(r'</?sup\b[^>]*>', re.IGNORECASE), '^'),
    (re.compile(r'</?sub\b[^>]*>', re.IGNORECASE), '~'),
]


def _html_to_text(raw: str) -> tuple[str, list[str]]:
    """Convert one field's HTML to bank text; return (text, image src list).

    Everything collapses to a single line. The bank format splits questions
    on blank lines and reads a line beginning with a letter and a period as
    an answer choice, so a preserved line break inside a stem would either
    end the question early or invent an answer.
    """
    images = []
    for tag in _IMG_RE.findall(raw or ''):
        m = _SRC_RE.search(tag)
        if m:
            images.append(m.group(1))
    text = _IMG_RE.sub(' ', raw or '')
    for pattern, marker in _INLINE_MARKERS:
        text = pattern.sub(marker, text)
    text = re.sub(r'<br\b[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|li|tr|h[1-6])>', ' ', text, flags=re.IGNORECASE)
    text = _TAG_RE.sub('', text)
    text = _html.unescape(text)
    text = text.replace('\xa0', ' ')
    # Empty markers left by a tag pair around nothing, e.g. <strong></strong>
    for marker in ('****', '^^', '~~'):
        text = text.replace(marker, '')
    return re.sub(r'\s+', ' ', text).strip(), images


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

class _ImageStore:
    """Pulls referenced files out of the zip into `folder`, once each."""

    def __init__(self, zf: zipfile.ZipFile, folder: Path, rel_prefix: str):
        self.zf = zf
        self.folder = folder
        self.rel_prefix = rel_prefix
        self.names = zf.namelist()
        self._by_base = {}
        for name in self.names:
            self._by_base.setdefault(Path(name).name, name)
        self.written: list[str] = []
        self._cache: dict[str, str | None] = {}

    def resolve(self, src: str) -> str | None:
        """Return the path to write into the bank file, or None if not found."""
        if src in self._cache:
            return self._cache[src]
        rel = _FILEBASE_RE.sub('', src.strip())
        candidates = [rel, unquote(rel), Path(rel).name, Path(unquote(rel)).name]
        member = None
        for cand in candidates:
            if cand in self.names:
                member = cand
                break
            if cand in self._by_base:
                member = self._by_base[cand]
                break
        if member is None:
            self._cache[src] = None
            return None
        self.folder.mkdir(parents=True, exist_ok=True)
        out_name = Path(member).name
        dest = self.folder / out_name
        if not dest.exists():
            with self.zf.open(member) as fsrc:
                dest.write_bytes(fsrc.read())
        rel_path = f'{self.rel_prefix}/{out_name}'
        self.written.append(rel_path)
        self._cache[src] = rel_path
        return rel_path


# ---------------------------------------------------------------------------
# Per-type writers
#
# Each returns (list of body lines, warning or None). The caller prepends the
# type/image/points header and the question number.
# ---------------------------------------------------------------------------

def _choices(response_lid: ET.Element) -> list[tuple[str, str, list[str]]]:
    """(ident, html, image srcs) for every response_label under one response_lid."""
    out = []
    for label in response_lid.iter('response_label'):
        text, imgs = _html_to_text(_mattext(label))
        out.append((label.get('ident') or '', text, imgs))
    return out


def _write_choice(item, correct, images, label_prefix='') -> tuple[list[str], str | None]:
    """MC and MA: one response_lid, a star on every correct choice."""
    lid = item.find('./presentation/response_lid')
    if lid is None:
        return [], 'no response_lid'
    right = set(correct.get(lid.get('ident') or 'response1', []))
    lines = []
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    choices = _choices(lid)
    if not choices:
        return [], 'no answer choices'
    if len(choices) > len(letters):
        return [], f'{len(choices)} answer choices is more than the bank format can letter'
    for i, (ident, text, imgs) in enumerate(choices):
        star = '*' if ident in right else ''
        src = images.resolve(imgs[0]) if imgs else None
        body = f'image: {src}' if (src and not text) else text
        lines.append(f'{star}{letters[i]}. {body}')
    if not right:
        return lines, 'no correct answer marked in the export'
    return lines, None


def _write_tf(item, correct) -> tuple[list[str], str | None]:
    """TF: the bank format takes the truth value, not lettered choices."""
    lid = item.find('./presentation/response_lid')
    if lid is None:
        return [], 'no response_lid'
    right = set(correct.get(lid.get('ident') or 'response1', []))
    for ident, text, _ in _choices(lid):
        if ident in right:
            value = text.strip().lower()
            if value in ('true', 'false'):
                return [f'A: {value.capitalize()}'], None
            return [], f"correct choice is '{text}', which is neither True nor False"
    return [], 'no correct answer marked in the export'


def _write_sa(item, correct) -> tuple[list[str], str | None]:
    """SA: the varequal values are the accepted answer strings themselves."""
    accepted = []
    for values in correct.values():
        for v in values:
            text, _ = _html_to_text(v)
            if text and text not in accepted:
                accepted.append(text)
    if not accepted:
        return [], 'no accepted answers in the export'
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if len(accepted) > len(letters):
        accepted = accepted[:len(letters)]
    return [f'{letters[i]}. {a}' for i, a in enumerate(accepted)], None


def _write_md(item, correct, stem: str) -> tuple[list[str], str | None]:
    """MD: one response_lid per blank, keyed to a [name] in the stem.

    Canvas names each blank's response `response_<blank>`; parser.py needs
    the bare `<blank>` to line up with the `[blank]` placeholders it finds
    in the stem, so the prefix comes off here.
    """
    lids = item.findall('./presentation/response_lid')
    if not lids:
        return [], 'no response_lid'
    stem_blanks = set(re.findall(r'\[(\w+)\]', stem))
    lines = []
    for lid in lids:
        ident = lid.get('ident') or ''
        blank = re.sub(r'^response_', '', ident)
        if blank not in stem_blanks:
            return [], (f"blank '{blank}' has no matching [{blank}] placeholder in the stem")
        right = set(correct.get(ident, []))
        for choice_id, text, _ in _choices(lid):
            star = '*' if choice_id in right else ''
            lines.append(f'{star}{blank}: {text}')
        if not right:
            return [], f"blank '{blank}' has no correct answer marked in the export"
    return lines, None


def _write_mt(item, correct) -> tuple[list[str], str | None]:
    """MT: one response_lid per left item, each listing every right option.

    Canvas identifies the right-hand options with UUIDs, which the bank
    format's `\\w+` labels reject, so they are renumbered right1..rightN in
    the order the first left item lists them.
    """
    lids = item.findall('./presentation/response_lid')
    if not lids:
        return [], 'no response_lid'
    right_labels: dict[str, str] = {}
    right_text: dict[str, str] = {}
    for lid in lids:
        for ident, text, _ in _choices(lid):
            if ident not in right_labels:
                right_labels[ident] = f'right{len(right_labels) + 1}'
                right_text[ident] = text
    if not right_labels:
        return [], 'no right-hand options'
    left_lines = []
    for i, lid in enumerate(lids, start=1):
        ident = lid.get('ident') or ''
        text, _ = _html_to_text(_mattext(lid))
        answer_ids = correct.get(ident, [])
        if not answer_ids:
            return [], f"left item {i} has no correct match marked in the export"
        label = right_labels.get(answer_ids[0])
        if label is None:
            return [], f"left item {i} matches an option that is not among the choices"
        left_lines.append(f'[{label}]left{i}: {text}')
    right_lines = [f'{label}: {right_text[ident]}' for ident, label in right_labels.items()]
    return left_lines + right_lines, None


def _write_or(item, correct) -> tuple[list[str], str | None]:
    """OR: the scoring condition lists the answer idents in correct order."""
    lid = item.find('./presentation/response_lid')
    if lid is None:
        return [], 'no response_lid'
    order = correct.get(lid.get('ident') or 'response1', [])
    if not order:
        return [], 'no correct order in the export'
    texts = {ident: text for ident, text, _ in _choices(lid)}
    lines = []
    for material in lid.iter('material'):
        position = material.get('position')
        if position in ('top', 'bottom'):
            text, _ = _html_to_text(''.join(
                (mt.text or '') for mt in material.findall('mattext')))
            if text:
                lines.append(f'{position}label: {text}')
    for rank, ident in enumerate(order, start=1):
        if ident not in texts:
            return [], 'correct order names an item that is not among the choices'
        lines.append(f'{rank}: {texts[ident]}')
    return lines, None


# ---------------------------------------------------------------------------
# Item + assessment conversion
# ---------------------------------------------------------------------------

def _convert_item(item: ET.Element, number: int, images: _ImageStore,
                  label: str) -> tuple[str | None, str | None, str | None]:
    """Return (block text, two-letter code, warning)."""
    meta = _metadata(item)
    raw_type = meta.get('question_type', '')
    code = TYPE_MAP.get(raw_type)
    if code is None:
        friendly = SKIPPED_TYPES.get(raw_type, raw_type or 'unlabeled')
        return None, None, f'{label}: {friendly} question. Skipped.'

    presentation = item.find('presentation')
    if presentation is None:
        return None, None, f'{label}: item has no presentation block. Skipped.'
    stem, stem_images = _html_to_text(_mattext(presentation))
    if not stem:
        return None, None, f'{label}: item has no question text. Skipped.'

    correct = _correct_map(item)
    if code in ('MC', 'MA'):
        body, warn = _write_choice(item, correct, images)
    elif code == 'TF':
        body, warn = _write_tf(item, correct)
    elif code == 'SA':
        body, warn = _write_sa(item, correct)
    elif code == 'MD':
        body, warn = _write_md(item, correct, stem)
    elif code == 'MT':
        body, warn = _write_mt(item, correct)
    else:
        body, warn = _write_or(item, correct)

    if warn:
        return None, None, f'{label}: {raw_type} -- {warn}. Skipped.'

    header = [code]
    resolved = [images.resolve(src) for src in stem_images]
    missing = [src for src, got in zip(stem_images, resolved) if got is None]
    found = [r for r in resolved if r]
    if found:
        header.append(f'image: {", ".join(found)}')
    points = meta.get('points_possible', '').strip()
    if points:
        try:
            header.append(f'({float(points):g} pts)')
        except ValueError:
            pass

    block = '\n'.join(header + [f'{number}. {stem}'] + body)
    note = None
    if missing:
        note = (f'{label}: image {missing[0]} is referenced but not in the zip. '
                f'Question kept without it.')
    return block, code, note


def _assessment_title(root: ET.Element) -> str:
    node = root.find('assessment')
    if node is not None and node.get('title'):
        return node.get('title')
    return ''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def peek_titles(zip_path: Path) -> list[str]:
    """Assessment titles in the zip, for naming the output file before converting."""
    titles = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in sorted(zf.namelist()):
                if not name.lower().endswith('.xml') or name.lower().endswith('imsmanifest.xml'):
                    continue
                try:
                    root = _strip_ns(ET.fromstring(zf.read(name)))
                except ET.ParseError:
                    continue
                if root.tag != 'questestinterop':
                    continue
                title = _assessment_title(root)
                if title:
                    titles.append(title)
    except (zipfile.BadZipFile, OSError):
        return []
    return titles


def convert_qti_zip(zip_path: Path, out_path: Path) -> ImportResult:
    """Convert a Canvas QTI export zip into a pyExamKit question-bank file.

    Writes `out_path`, plus any referenced images into
    `<out_path stem>_images/` beside it, and returns what happened. Every
    assessment in the zip is folded into the one bank file: an item-bank
    export can hold several, and pyExamKit draws from a pool per file.
    """
    zip_path = Path(zip_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img_rel = f'{out_path.stem}_images'
    result = ImportResult(text='')
    blocks: list[str] = []
    number = 0

    with zipfile.ZipFile(zip_path) as zf:
        images = _ImageStore(zf, out_path.parent / img_rel, img_rel)
        xml_names = [n for n in zf.namelist()
                     if n.lower().endswith('.xml') and not n.lower().endswith('imsmanifest.xml')]
        assessments = []
        for name in sorted(xml_names):
            try:
                root = _strip_ns(ET.fromstring(zf.read(name)))
            except ET.ParseError as exc:
                result.warnings.append(f'{name}: not readable as XML ({exc}). Skipped.')
                continue
            if root.tag != 'questestinterop':
                continue      # assessment_meta.xml and friends
            assessments.append((name, root))

        if not assessments:
            raise ValueError(
                'No QTI assessment found in this zip. Export the quiz from Canvas '
                'with Export Course Content > Quiz, or the item bank from the '
                'Item Banks page, and choose the QTI option.')

        for name, root in assessments:
            title = _assessment_title(root) or Path(name).stem
            result.titles.append(title)
            items = list(root.iter('item'))
            for index, item in enumerate(items, start=1):
                label = f'{title} q{index}'
                number += 1
                block, code, note = _convert_item(item, number, images, label)
                if note:
                    result.warnings.append(note)
                if block is None:
                    number -= 1
                    continue
                blocks.append(block)
                result.counts[code] = result.counts.get(code, 0) + 1

        result.images = images.written

    head = ['# Converted from a Canvas QTI export by pyExamKit.',
            f'# Source: {zip_path.name}']
    for title in result.titles:
        head.append(f'# Assessment: {title}')
    head.append('#')
    head.append('# Check the converted questions before building an exam: Canvas '
                'question text is HTML,')
    head.append('# and anything it cannot express as plain text (tables, nested '
                'lists) is flattened here.')

    result.text = '\n'.join(head) + '\n\n' + '\n\n'.join(blocks) + '\n'
    out_path.write_text(result.text, encoding='utf-8')
    return result


def summarize(result: ImportResult) -> str:
    """One-line count summary, e.g. '12 questions (9 MC, 3 TF)'."""
    if not result.counts:
        return 'no questions converted'
    parts = ', '.join(f'{n} {code}' for code, n in sorted(result.counts.items()))
    return f'{result.total} question{"s" if result.total != 1 else ""} ({parts})'
