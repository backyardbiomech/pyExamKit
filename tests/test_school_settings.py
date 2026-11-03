'''
School settings: the logo, ID label, prefix, and ID length a sheet prints,
and the ID length squares that let the scanner read any length. Every ID
here is invented.

    python -m unittest tests.test_school_settings -v
'''
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_ocr  # noqa: E402
import answer_sheet  # noqa: E402
import bubbles  # noqa: E402
import roster  # noqa: E402
import school  # noqa: E402
import sheet_layout as L  # noqa: E402


def setUpModule():
    # Full-size renders stand in for aligned scans, and the settings come
    # from a config file of the test's own, never the user's.
    mock.patch.object(answer_sheet, 'PRINT_SCALE', 1).start()
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    mock.patch.object(ai_ocr, 'CONFIG_PATH', Path(tmp.name) / 'config.json').start()
    unittest.addModuleCleanup(mock.patch.stopall)


def render(pdf: bytes) -> np.ndarray:
    page = fitz.open(stream=pdf, filetype='pdf')[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def text(pdf: bytes) -> str:
    return fitz.open(stream=pdf, filetype='pdf')[0].get_text()


def paint_id(img, digits: str):
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    for c, d in enumerate(digits, 1):
        for lab, cx, cy in L.v2_id_rows(len(digits))[f'ID{c:02d}']:
            if lab == d:
                img[(xx - cx) ** 2 + (yy - cy) ** 2 <= 81] = 40


class TestIdLength(unittest.TestCase):
    def test_eight_digits_sit_where_they_always_have(self):
        old = {f'ID{c + 1:02d}': [(d, 890 + 30 * c, 250 + 26 * i) for i, d in enumerate(L.DIGITS)]
               for c in range(8)}
        self.assertEqual(L.v2_id_rows(8), old)
        self.assertEqual(L.V2.id_digits, old)

    def test_eight_digits_print_no_length_squares(self):
        self.assertEqual(L.id_length_bits(8), [False, False, False])

    def test_every_length_reads_back_its_id(self):
        for n in L.ID_LENGTHS:
            sid = '9876543210'[:n]
            with self.subTest(digits=n):
                img = render(answer_sheet.build_sheet(30, id_digits=n).pdf)
                gray = bubbles.to_gray(img)
                self.assertEqual(L.read_id_length(gray), n)
                paint_id(img, sid)
                r = bubbles.read_sheet(img, 30)
                self.assertEqual(r.answers['studentID'], sid)

    def test_a_grouped_sheet_reads_its_length_too(self):
        cols = [[5, 3, 5]]
        img = render(answer_sheet.build_sheet(13, columns=cols, id_digits=6).pdf)
        paint_id(img, '204816')
        r = bubbles.read_sheet(img, 13, keyed={'': L.keyed_layout(cols)})
        self.assertEqual(r.answers['studentID'], '204816')

    def test_practical_page_one_reads_its_length(self):
        pdf = answer_sheet.build_practical_sheet(10, 'AB', id_digits=10)
        img = render(pdf)
        paint_id(img, '0123456789')
        gray = bubbles.to_gray(img)
        r = bubbles.read_sheet(img, 0, layout=L.detect_layout(gray))
        self.assertEqual(r.answers['studentID'], '0123456789')

    def test_the_squares_leave_layout_and_form_alone(self):
        for n in L.ID_LENGTHS:
            gray = bubbles.to_gray(render(
                answer_sheet.build_practical_sheet(10, 'AC', id_digits=n)))
            self.assertEqual(L.detect_layout(gray).practical_page, 1)
            self.assertEqual(L.read_form(gray), 'AC')

    def test_unprintable_lengths_are_refused(self):
        for n in (3, 11):
            with self.assertRaises(answer_sheet.SheetError):
                answer_sheet.build_sheet(30, id_digits=n)


class TestPrintedText(unittest.TestCase):
    def tearDown(self):
        ai_ocr.CONFIG_PATH.unlink(missing_ok=True)

    def test_defaults_are_longwoods(self):
        t = text(answer_sheet.build_sheet(30).pdf)
        self.assertIn('Longwood ID number', t)
        self.assertIn('L\n', t)

    def test_label_and_prefix_from_the_settings(self):
        school.save(label='Student number', prefix='')
        t = text(answer_sheet.build_sheet(30).pdf)
        self.assertIn('Student number', t)
        self.assertNotIn('Longwood', t)

    def test_digits_from_the_settings(self):
        school.save(digits=6)
        gray = bubbles.to_gray(render(answer_sheet.build_sheet(30).pdf))
        self.assertEqual(L.read_id_length(gray), 6)

    def test_an_image_logo_fits_its_box(self):
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / 'crest.png'
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
            pix.set_rect(pix.irect, (20, 60, 140))
            pix.save(png)
            school.save(logo_path=str(png))
            page = fitz.open(stream=answer_sheet.build_sheet(30).pdf, filetype='pdf')[0]
            (info,) = page.get_image_info()
            x0, y0, x1, y1 = (v * L.PX_PER_PT for v in info['bbox'])
            bx0, by0, bx1, by1 = answer_sheet.LOGO_BOX
            self.assertGreaterEqual(x0, bx0 - 0.5)
            self.assertLessEqual(y1, by1 + 0.5)
            self.assertAlmostEqual(x1 - x0, y1 - y0, delta=1)   # still square

    def test_a_missing_logo_prints_none(self):
        school.save(logo_path='/no/such/logo.pdf')
        self.assertIsNone(school.logo())
        answer_sheet.build_sheet(30)                            # and does not fail

    def test_no_logo_and_back_to_default(self):
        school.save(logo_path='')
        self.assertIsNone(school.logo())
        school.save(logo_path=school.USE_DEFAULT)
        self.assertEqual(school.logo(), school.DEFAULT_LOGO)

    def test_check_refuses_bad_input(self):
        for logo, digits in (('logo.gif', 8), ('', 'eight'), ('', 12)):
            with self.assertRaises(ValueError):
                school.check(logo, digits)


class TestRosterLength(unittest.TestCase):
    def test_pads_and_strips_by_the_settings(self):
        self.assertEqual(roster.normalize_id('L123456', 8, 'L'), '00123456')
        self.assertEqual(roster.normalize_id('S1234', 6, 'S'), '001234')
        self.assertEqual(roster.normalize_id('1234567', 6, ''), None)    # too long
        self.assertEqual(roster.normalize_id('L1234', 6, ''), None)      # not this prefix

    def test_a_sheet_of_another_length_says_why(self):
        r = {'00123456': roster.Student('Doe', 'Jon', '00123456')}
        s, note = roster.match_id('123456', r)
        self.assertIsNone(s)
        self.assertIn('6-digit', note)


if __name__ == '__main__':
    unittest.main()
