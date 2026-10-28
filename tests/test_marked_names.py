'''
Every student gets their own marked page, even when the name and ID were
not read. Pages were named by name and ID alone, so unread students shared
one file and each overwrote the last: 61 students made a 19-page PDF. A
version graded on its own is named by each student's place in the whole
stack, so two versions' students cannot collide either.

    python -m unittest tests.test_marked_names -v
'''
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import grade_functions  # noqa: E402
import outputs  # noqa: E402


def mark(scan_rows=None, version=''):
    out = Path(tempfile.mkdtemp(prefix='marked_names_'))
    csv = outputs.results_csv(out, version) if version else outputs.results_csv(out)
    pd.DataFrame(
        {'LastName': ['KEY', '-', '-', 'Named'],
         'FirstName': ['', '-', '-', 'A'],
         'studentID': ['', '-', '-', '1'],
         'Q1': ['A', 'A', 'B', 'A']},
        index=['0', '1', '2', '3'],
    ).to_csv(csv, index=True, index_label='index')
    markeddir = out / 'marked'
    markeddir.mkdir()
    grade_functions.gradeResults(csv, False, False, 1, 1, markeddir)
    images = [None]
    for name in ('s1', 's2', 's3'):
        path = out / f'{name}.jpg'
        PILImage.new('RGB', (200, 200), 'white').save(path)
        images.append(str(path))
    grade_functions.markSheets(csv, images, markeddir, {'Q1': ((10, 10), (100, 30))},
                               {'A': 20, 'B': 40}, False, False, scan_rows=scan_rows)
    return sorted(p.name for p in markeddir.glob('*.jpg'))


class MarkedNames(unittest.TestCase):
    def test_unread_students_each_keep_a_page(self):
        self.assertEqual(len(mark()), 3)

    def test_names_carry_the_place_in_the_stack(self):
        names = mark(scan_rows={'1': 12, '2': 40, '3': 7}, version='B')
        self.assertEqual(names, ['-_-_-_012.jpg', '-_-_-_040.jpg', 'Named_A_1_007.jpg'])


if __name__ == '__main__':
    unittest.main()