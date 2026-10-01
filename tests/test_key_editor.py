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


class TestPrintedBoxes(unittest.TestCase):
    '''The editor offers no box tools for a key whose boxes the sheet printed.'''

    def editor(self, path):
        with mock.patch.object(openQ.KeyFileEditorDialog, '_build_ui', lambda self: None):
            return openQ.KeyFileEditorDialog(None, path=str(path))

    def test_built_keys_are_recognized(self):
        with tempfile.TemporaryDirectory() as d:
            marked = Path(d) / 'new.csv'
            data = keyformat.load_key_file(str(HERE / 'testkey.csv'))
            data['metadata']['answer_boxes'] = 'printed'
            keyformat.save_key_file(str(marked), data)
            self.assertTrue(self.editor(marked).printed_boxes)
            # the marker survives a save from the editor
            with mock.patch.object(openQ.KeyFileEditorDialog, '_commit_current_edit',
                                   lambda self: None):
                keyformat.save_key_file(str(marked), self.editor(marked)._to_data())
            self.assertEqual(keyformat.load_key_file(str(marked))['metadata']['answer_boxes'],
                             'printed')
        self.assertTrue(self.editor(BUILT_KEY).printed_boxes)       # older: sheet_rows
        self.assertFalse(self.editor(HERE / 'testkey.csv').printed_boxes)


class TestPracticalMarks(unittest.TestCase):
    '''Each graded box is marked with the points it earned, beside the box
    and never on the writing.'''
    GRADES = [('CC', 2.0, '2'), ('CX', 0.5, '0.5'), ('XX', 0.0, '0'), ('CX', 2 / 3, '0.67')]

    @classmethod
    def setUpClass(cls):
        cls.p = practical.load(PRACTICAL)
        cls.pdf = answer_sheet.build_practical_sheet(len(cls.p.stations), 'AC', cls.p.title, None)
        cls.boxes = L.practical_boxes(len(cls.p.stations))
        row = {'LastName': 'Doe', 'FirstName': 'Jo', 'studentID': '1', 'partialscore': 0}
        pts, cls.expected = {}, {}
        qs = [q for q in cls.p.questions() if q.letter in 'AC']
        for n, q in enumerate(qs):
            grade, earned, text = cls.GRADES[n % len(cls.GRADES)]
            row[f'openQ_{q.key}'] = f'{grade}: written'
            pts[f'openQ_{q.key}'] = earned
            cls.expected[q.key] = text
        cls.results = pd.DataFrame([row], index=['1'])
        cls.points = pd.DataFrame([pts], index=['1'])

    def _mark(self, out: Path) -> list[practical_scan.PageRead]:
        reads = []
        for n, page in enumerate(fitz.open(stream=self.pdf, filetype='pdf'), 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            path = out / f'a{n}.png'
            Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(path)
            reads.append(practical_scan.PageRead(n, n, 'AC', str(path)))
        practical_scan.mark_sheets(self.results, self.points,
                                   [practical_scan.Sheet('AC', reads)], self.p, out,
                                   grade_functions._get_font(28))
        return reads

    def test_marks_sit_outside_the_boxes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            self._mark(out)
            pages = [np.array(Image.open(out / f'Doe_Jo_1_p{n}.jpg').convert('RGB'))
                     .astype(int) for n in (1, 2)]
        # Green, orange, and red marks are saturated; the printed sheet is not
        inked = lambda a: ((a.max(axis=-1) - a.min(axis=-1)) > 100).sum()  # noqa: E731
        for (_, _), (page, (x0, y0, x1, y1)) in self.boxes.items():
            im = pages[page - 1]
            self.assertEqual(inked(im[y0:y1, x0:x1]), 0, 'a mark inside a box')
            self.assertGreater(inked(im[y0:y1, x1:x1 + 40]), 20, 'no mark beside a box')

    def test_each_mark_is_the_points_earned(self):
        drawn = []

        class Recorder:
            def __init__(self, image):
                pass

            def text(self, xy, text, fill=None, font=None, **_):
                drawn.append((xy, text, fill))

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(practical_scan.ImageDraw, 'Draw', Recorder):
            self._mark(Path(d))
        marks = [text for _, text, _ in drawn if not text.startswith('Form')]
        qs = [q for q in self.p.questions() if q.letter in 'AC']
        self.assertEqual(marks, [self.expected[q.key] for q in qs])
        colors = {text: fill for _, text, fill in drawn}
        self.assertEqual(colors['2'], practical_scan.GRADE_COLOR['CC'])
        self.assertEqual(colors['0.5'], practical_scan.GRADE_COLOR['CX'])
        self.assertEqual(colors['0'], practical_scan.GRADE_COLOR['XX'])

    def test_a_wide_mark_shrinks_to_clear_the_next_letter(self):
        font = grade_functions._get_font(28)
        room = practical_scan.MARK_ROOM[0]
        self.assertIs(practical_scan._fit(font, '2', room), font)
        self.assertLessEqual(practical_scan._fit(font, '0.67', room).getlength('0.67'), room)


if __name__ == '__main__':
    unittest.main()
