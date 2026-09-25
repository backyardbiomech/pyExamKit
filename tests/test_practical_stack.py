'''
A synthetic filled and scanned practical stack goes through the scanner's own
PDF split and alignment, and every page's layout, form, and ID read back.

    python -m unittest tests.test_practical_stack -v
'''
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import bubbles  # noqa: E402
import init_functions  # noqa: E402
import make_practical_test_stack as stack  # noqa: E402
import sheet_layout as L  # noqa: E402
from image import Image  # noqa: E402
from settings import Settings  # noqa: E402

SOURCE = ROOT / 'tests' / 'fixtures' / 'practical' / 'practical_test.md'


class TestSyntheticStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix='practical_stack_'))
        # Two students: the second writes and bubbles in very light pencil
        scans = stack.make_stack(SOURCE, cls.out, n_students=2, seed=5)
        cls.pages = init_functions.filenames(str(scans), scan_jpgs_dir=cls.out / 'jpgs')
        cls.students = list(csv.DictReader(open(cls.out / 'students.csv')))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_pages_align_and_read(self):
        self.assertEqual(len(self.pages), 4)
        for i, f in enumerate(self.pages):
            s, n = self.students[i // 2], i % 2 + 1
            aligned = Image(f, Settings()).aligned
            gray = bubbles.to_gray(aligned)
            self.assertEqual(L.detect_layout(gray).practical_page, n)
            self.assertEqual(L.read_form(gray), s['form'])
            if n == 1:
                r = bubbles.read_sheet(aligned, 0)
                self.assertEqual(r.answers['studentID'], s['bubbled_id'])


if __name__ == '__main__':
    unittest.main()
