'''
The registration circles are found at the print scales office printers use:
wide printer margins shrink a sheet to 85% or less, and a copier can scan a
little large. Each is checked with blur, which fattens every mark.

    python -m unittest tests.test_registration -v
'''
import sys
import unittest
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import answer_sheet  # noqa: E402
import scan_functions  # noqa: E402
from settings import Settings  # noqa: E402


def page_at(page: fitz.Page, scale: float) -> np.ndarray:
    '''The page printed at `scale`, scanned at 200 dpi, and resized as image.Image does.'''
    pix = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), colorspace=fitz.csRGB)
    full = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    small = full.resize((int(full.width * scale), int(full.height * scale)), Image.LANCZOS)
    printed = Image.new('RGB', full.size, 'white')
    printed.paste(small, ((full.width - small.width) // 2, (full.height - small.height) // 2))
    scanned = printed.filter(ImageFilter.GaussianBlur(1.2))
    w = 1224
    return np.array(scanned.resize((w, int(scanned.height * w / scanned.width)), Image.LANCZOS))


def expected(scale: float) -> np.ndarray:
    '''Where the circles land after shrinking about the page center.'''
    s = Settings()
    center = np.array([s.sz[1] / 2, s.sz[0] / 2])
    return center + (s.keyRegPts - center) * scale


class TestRegistration(unittest.TestCase):
    SHEETS = {
        'classic': lambda: fitz.open(ROOT / 'images' / 'pyExamScan AnswerSheet 150questions.pdf'),
        'v2': lambda: fitz.open(stream=answer_sheet.build_sheet(60).pdf),
        'practical': lambda: fitz.open(stream=answer_sheet.build_practical_sheet(25, 'AC')),
    }

    def test_every_design_at_every_scale(self):
        for name, make in self.SHEETS.items():
            page = make()[0]
            for scale in (0.80, 0.85, 0.92, 1.0, 1.03):
                with self.subTest(sheet=name, scale=scale):
                    pts = scan_functions.getRegPts(page_at(page, scale), Settings())
                    # Within 2 px of the right circle, in the right order
                    self.assertLess(np.abs(pts - expected(scale)).max(), 2.0)

    def test_blank_page_raises(self):
        with self.assertRaises(ValueError):
            scan_functions.getRegPts(np.full((1584, 1224, 3), 255, np.uint8), Settings())


if __name__ == '__main__':
    unittest.main()
