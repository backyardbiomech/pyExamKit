'''
Lab practical form sheets: the scanner can tell each page and form apart,
reads the ID from page 1, and crops land inside the printed boxes.

    python -m unittest tests.test_practical_sheet -v
'''
import sys
import unittest
from pathlib import Path

import fitz
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import answer_sheet  # noqa: E402
import bubbles  # noqa: E402
import practical  # noqa: E402
import sheet_layout as L  # noqa: E402


def render(pdf: bytes) -> list[np.ndarray]:
    '''Every page at the canonical 144 dpi, as the aligner would leave it.'''
    out = []
    for page in fitz.open(stream=pdf, filetype='pdf'):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
        out.append(np.frombuffer(pix.samples, np.uint8)
                   .reshape(pix.height, pix.width, 3).copy())
    return out


def paint_id(img, digits, gray):
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    for c, d in enumerate(digits, 1):
        for lab, cx, cy in L.V2.id_digits[f'ID{c:02d}']:
            if lab == d:
                img[(xx - cx) ** 2 + (yy - cy) ** 2 <= 81] = gray


class TestFormSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {f: render(answer_sheet.build_practical_sheet(25, f, 'Practical'))
                     for f in practical.DEFAULT_FORMS}

    def test_twenty_five_stations_take_two_pages(self):
        self.assertTrue(all(len(p) == 2 for p in self.pages.values()))

    def test_every_page_names_its_page_and_form(self):
        for form, pages in self.pages.items():
            for n, img in enumerate(pages, 1):
                gray = bubbles.to_gray(img)
                lay = L.detect_layout(gray)
                self.assertEqual(lay.practical_page, n, form)
                self.assertEqual(L.read_form(gray), form)

    def test_other_sheets_read_no_form(self):
        img = render(answer_sheet.build_sheet(questions=30).pdf)[0]
        self.assertEqual(L.read_form(bubbles.to_gray(img)), '')

    def test_crops_are_blank_paper_inside_the_boxes(self):
        pages = self.pages['AC']
        for (station, slot), (page, box) in L.practical_boxes(25).items():
            x0, y0, x1, y1 = L.practical_crop(box)
            crop = bubbles.to_gray(pages[page - 1])[y0:y1, x0:x1]
            self.assertGreater(crop.min(), 200, f'station {station} slot {slot}')
            # and the printed border sits just outside the crop
            x0, y0, x1, y1 = box
            border = bubbles.to_gray(pages[page - 1])[y0 - 1:y0 + 2, x0 + 20:x1 - 20]
            self.assertLess(border.min(), 100)

    def test_blank_page_reads_blank_id(self):
        r = bubbles.read_sheet(self.pages['AB'][0], 0)
        self.assertEqual(r.answers['studentID'], '-' * 8)

    def test_id_read_heavy_and_light(self):
        for gray in (60, 215):      # 215 is under the old fixed-level cutoff
            img = self.pages['BD'][0].copy()
            paint_id(img, '00123456', gray)
            r = bubbles.read_sheet(img, 0)
            self.assertEqual(r.answers['studentID'], '00123456', f'gray {gray}')

    def test_page_count_and_limit(self):
        self.assertEqual(L.practical_pages(11), 1)
        self.assertEqual(L.practical_pages(26), 2)
        self.assertEqual(L.practical_pages(27), 3)
        with self.assertRaises(answer_sheet.SheetError):
            answer_sheet.build_practical_sheet(42, 'AB')

    def test_bad_form(self):
        for form in ('AA', 'AE', 'ABC'):
            with self.assertRaises(answer_sheet.SheetError):
                answer_sheet.build_practical_sheet(5, form)

    def test_form_letters_sorted(self):
        img = render(answer_sheet.build_practical_sheet(5, 'CA'))[0]
        self.assertEqual(L.read_form(bubbles.to_gray(img)), 'AC')



class TestDoubleSided(unittest.TestCase):
    '''Sheets are printed on both sides, so each starts on fresh paper.'''

    def pages(self, stations, double_sided=True):
        return len(fitz.open(stream=answer_sheet.build_practical_sheet(
            stations, 'AC', 'T', None, double_sided=double_sided), filetype='pdf'))

    def test_odd_page_sheets_get_a_blank_back(self):
        self.assertEqual(self.pages(11), 2)       # one page and its back
        self.assertEqual(self.pages(25), 2)       # already two
        self.assertEqual(self.pages(27), 4)       # three and a back
        self.assertEqual(self.pages(11, double_sided=False), 1)

    def test_blank_back_is_told_from_the_emptiest_page(self):
        '''A 27-station sheet's third page holds one station, the least ink
        any printed page has; its fourth is the blank back.'''
        import random
        import tempfile
        from PIL import Image
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
        import make_practical_test_stack as stack
        import practical_scan
        doc = fitz.open(stream=answer_sheet.build_practical_sheet(27, 'BD', 'T', None,
                                                                  double_sided=True),
                        filetype='pdf')
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as d:
            for n, want in ((3, False), (4, True)):
                pix = doc[n - 1].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72))
                img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                for scale in (1.0, 0.8):
                    path = Path(d) / f'p{n}_{scale}.jpg'
                    stack.scan(stack.printed(img, scale), rng).save(path, quality=80)
                    self.assertEqual(practical_scan.is_blank(path), want, (n, scale))


if __name__ == '__main__':
    unittest.main()
