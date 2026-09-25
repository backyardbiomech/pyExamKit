'''
The key editor (Scan Exams, Edit…) saves a key without changing what the
scanner reads from it, and practical grade marks stay off the writing.

    python -m unittest tests.test_key_editor -v
'''
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import answer_sheet  # noqa: E402
import grade_functions  # noqa: E402
import keyformat  # noqa: E402
import openQ  # noqa: E402
import practical  # noqa: E402
import practical_scan  # noqa: E402
import sheet_layout as L  # noqa: E402

HERE = Path(__file__).resolve().parent
BUILT_KEY = HERE / 'fixtures' / 'build_migration' / 'golden' / 'migration_fixture_vA_key.csv'
PRACTICAL = HERE / 'fixtures' / 'practical' / 'practical_test.md'


def editor_data(path) -> dict:
    '''What the editor would save for `path`, without opening its window.'''
    with mock.patch.object(openQ.KeyFileEditorDialog, '_build_ui', lambda self: None), \
            mock.patch.object(openQ.KeyFileEditorDialog, '_commit_current_edit',
                              lambda self: None):
        return openQ.KeyFileEditorDialog(None, path=str(path))._to_data()


class TestEditorKeepsTheKey(unittest.TestCase):
    def test_question_count_keeps_written_rows(self):
        '''A built key's written question has a bubble row too; saving once
        used to drop it from the count, so the last question went unread.'''
        before = keyformat.load_key_file(str(BUILT_KEY))['metadata']
        after = editor_data(BUILT_KEY)['metadata']
        self.assertEqual(after['num_questions'], before['num_questions'])
        for field in ('questions_to_skip', 'sheet_rows', 'version'):
            self.assertEqual(str(after[field]), str(before[field]), field)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'key.csv'
            keyformat.save_key_file(str(out), editor_data(BUILT_KEY))
            before, after = (keyformat.load_key_file(str(p)) for p in (BUILT_KEY, out))
        self.assertEqual(after['metadata']['num_questions'],
                         before['metadata']['num_questions'])
        self.assertEqual(after['bubble_answers'], before['bubble_answers'])
        self.assertEqual(after['point_values'], before['point_values'])


class TestPracticalMarks(unittest.TestCase):
    def test_marks_sit_outside_the_boxes(self):
        p = practical.load(PRACTICAL)
        pdf = answer_sheet.build_practical_sheet(len(p.stations), 'AC', p.title, None)
        boxes = L.practical_boxes(len(p.stations))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            reads = []
            for n, page in enumerate(fitz.open(stream=pdf, filetype='pdf'), 1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                path = out / f'a{n}.png'
                Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(path)
                reads.append(practical_scan.PageRead(n, n, 'AC', str(path)))
            row = {'LastName': 'Doe', 'FirstName': 'Jo', 'studentID': '1', 'partialscore': 0}
            row.update({f'openQ_{q.key}': 'XX' for q in p.questions() if q.letter in 'AC'})
            practical_scan.mark_sheets(pd.DataFrame([row], index=['1']),
                                       [practical_scan.Sheet('AC', reads)], p, out,
                                       grade_functions._get_font(40),
                                       grade_functions._get_font(28))
            pages = [np.array(Image.open(out / f'Doe_Jo_1_p{n}.jpg').convert('RGB'))
                     .astype(int) for n in (1, 2)]
        for (_, _), (page, (x0, y0, x1, y1)) in boxes.items():
            im = pages[page - 1]
            red = lambda a: ((a[..., 0] > 150) & (a[..., 1] < 90)).sum()  # noqa: E731
            self.assertEqual(red(im[y0:y1, x0:x1]), 0, 'a mark inside a box')
            self.assertGreater(red(im[y0:y1, x1:x1 + 40]), 20, 'no mark beside a box')


if __name__ == '__main__':
    unittest.main()
