'''
Adaptive bubble reading on synthetic sheets: the blank classic sheet from
images/, with marks painted in at chosen gray levels.

    python -m unittest tests.test_bubbles -v
'''
import sys
import unittest
from pathlib import Path

import fitz
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bubbles  # noqa: E402
import sheet_layout  # noqa: E402

BLANK = ROOT / 'images' / 'pyExamScan AnswerSheet 150questions.pdf'


def blank_page() -> np.ndarray:
    page = fitz.open(BLANK)[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def paint(img, layout, key, label, gray, radius=9):
    '''Shade one bubble solid at `gray` (0 black, 255 white).'''
    for lab, cx, cy in (layout.questions | layout.id_digits)[key]:
        if lab == label:
            yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
            disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
            img[disk] = np.minimum(img[disk], gray)
            return
    raise KeyError(label)


ANSWERS = 'ABCDEFBADCFEABCDEFAB'   # 20 questions


class TestAdaptiveReading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blank = blank_page()
        cls.lay = sheet_layout.CLASSIC

    def sheet(self, gray, erasures=(), erase_gray=None, id_digits='00123456'):
        img = self.blank.copy()
        for i, a in enumerate(ANSWERS, 1):
            paint(img, self.lay, f'Q{i:03d}', a, gray)
        for q, lab in erasures:
            paint(img, self.lay, q, lab, erase_gray)
        for c, d in enumerate(id_digits, 1):
            paint(img, self.lay, f'ID{c:02d}', d, gray)
        return bubbles.read_sheet(img, len(ANSWERS), layout=self.lay)

    def answers(self, r):
        return ''.join(r.answers[f'Q{i:03d}'] for i in range(1, len(ANSWERS) + 1))

    def test_detects_classic_layout(self):
        self.assertIs(sheet_layout.detect_layout(bubbles.to_gray(self.blank)), self.lay)

    def test_heavy_marks(self):
        r = self.sheet(60)
        self.assertEqual(self.answers(r), ANSWERS)
        self.assertEqual(r.answers['studentID'], '00123456')

    def test_light_marks_still_read(self):
        # A light pencil hand: about a third as dark as the heavy one.
        r = self.sheet(185)
        self.assertEqual(self.answers(r), ANSWERS)
        self.assertEqual(r.answers['studentID'], '00123456')

    def test_heavy_hand_erasures_dropped(self):
        # An erasure by a heavy hand leaves more graphite than a light hand's
        # real mark; beside a fresh mark it must still read as erased.
        erased = [('Q001', 'F'), ('Q005', 'A'), ('Q009', 'B')]
        r = self.sheet(60, erased, erase_gray=175)
        self.assertEqual(self.answers(r), ANSWERS)

    def test_erasure_on_blank_row_flagged_not_silent(self):
        img = self.blank.copy()
        for i, a in enumerate(ANSWERS, 1):
            if i != 3:
                paint(img, self.lay, f'Q{i:03d}', a, 60)
        paint(img, self.lay, 'Q003', 'C', 150)       # a half-erased lone mark
        r = bubbles.read_sheet(img, len(ANSWERS), layout=self.lay)
        self.assertTrue(any(f.field == 'Q003' for f in r.flags))

    def test_ignored_rows(self):
        img = self.blank.copy()
        for i, a in enumerate(ANSWERS, 1):
            paint(img, self.lay, f'Q{i:03d}', a, 60)
        r = bubbles.read_sheet(img, len(ANSWERS), ignores=[4, 7], layout=self.lay)
        self.assertEqual(r.answers['Q004'], 'ignore')
        self.assertEqual(r.answers['Q007'], 'ignore')
        self.assertEqual(r.answers['Q005'], ANSWERS[4])

    def test_blank_sheet_reads_blank(self):
        r = bubbles.read_sheet(self.blank, 150, layout=self.lay)
        self.assertTrue(all(r.answers[f'Q{i:03d}'] == '-' for i in range(1, 151)))
        self.assertEqual(r.answers['studentID'], '-' * 8)


if __name__ == '__main__':
    unittest.main()
