'''
A written answer is marked on the student's sheet with the points it earned,
not the grader's code (CC, CX, XX): full credit, half for partial, 0 for
none, at the question's own point value. The key's sheet shows what each
question is worth.

    python -m unittest tests.test_written_marks -v
'''
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import grade_functions  # noqa: E402
import outputs  # noqa: E402


class Recorder:
    '''Stands in for ImageDraw.Draw, keeping what was written on each sheet,
    named in the order markSheets opens them: the key, then each student.'''
    names = []
    marks = []

    def __init__(self, image):
        self.name = Recorder.names.pop(0)

    def text(self, xy, text, fill=None, font=None, **_):
        Recorder.marks.append((self.name, text, fill))


class WrittenMarks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = Path(tempfile.mkdtemp(prefix='written_marks_'))
        cls.csv = outputs.results_csv(out)
        pd.DataFrame(
            {'LastName': ['KEY', 'Full', 'Part', 'None'],
             'FirstName': ['', 'A', 'B', 'C'],
             'studentID': ['', '1', '2', '3'],
             'Q1': ['A', 'A', 'B', 'A'],
             'openQ_1': ['CC', 'CC: aorta', 'CX: aort', 'XX: vein']},
            index=['0', '1', '2', '3'],
        ).to_csv(cls.csv, index=True, index_label='index')
        markeddir = out / 'marked'
        markeddir.mkdir()
        grade_functions.gradeResults(cls.csv, False, True, 1, 1, markeddir,
                                     point_values={'openQ_1': 3})
        images = []
        for name in ('key', 's1', 's2', 's3'):
            path = out / f'{name}.jpg'
            PILImage.new('RGB', (200, 200), 'white').save(path)
            images.append(str(path))
        areas = {'Q1': ((10, 10), (100, 30)), 'openQ_1': ((10, 50), (150, 90))}
        Recorder.names = ['key', 's1', 's2', 's3']
        Recorder.marks = []
        with mock.patch.object(grade_functions.ImageDraw, 'Draw', Recorder):
            grade_functions.markSheets(cls.csv, images, markeddir, areas,
                                       {'A': 20, 'B': 40}, False)
        cls.written = {name: (text, fill) for name, text, fill in Recorder.marks
                       if text not in ('C', 'X')}

    def test_full_credit_shows_the_question_value(self):
        self.assertEqual(self.written['s1'], ('3', (0, 255, 0)))

    def test_partial_credit_shows_half(self):
        self.assertEqual(self.written['s2'], ('1.5', (255, 140, 0)))

    def test_no_credit_shows_zero_in_red(self):
        self.assertEqual(self.written['s3'], ('0', (255, 0, 0)))

    def test_key_sheet_shows_what_the_question_is_worth(self):
        self.assertEqual(self.written['key'][0], '3')

    def test_grade_codes_are_gone(self):
        texts = [t for t, _ in self.written.values()]
        for code in ('CC', 'CX', 'XX'):
            self.assertNotIn(code, texts)


class MissedAnswers(unittest.TestCase):
    """A right answer left unmarked gets a blue # when correct answers are
    shown, and nothing beside the question number."""

    def marks_for(self, mark_correct):
        out = Path(tempfile.mkdtemp(prefix='missed_marks_'))
        csv = outputs.results_csv(out)
        pd.DataFrame({'LastName': ['KEY', 'Wrong', 'Blank'], 'FirstName': ['', 'A', 'B'],
                      'studentID': ['', '1', '2'], 'Q1': ['A', 'B', '-']},
                     index=['0', '1', '2']).to_csv(csv, index=True, index_label='index')
        markeddir = out / 'marked'
        markeddir.mkdir()
        grade_functions.gradeResults(csv, True, False, 1, 1, markeddir)
        images = []
        for name in ('key', 's1', 's2'):
            path = out / f'{name}.jpg'
            PILImage.new('RGB', (200, 200), 'white').save(path)
            images.append(str(path))
        Recorder.names = ['key', 's1', 's2']
        Recorder.marks = []
        with mock.patch.object(grade_functions.ImageDraw, 'Draw', Recorder):
            grade_functions.markSheets(csv, images, markeddir, {'Q1': ((10, 10), (100, 30))},
                                       {'A': 20, 'B': 40, '-': 0}, mark_correct)
        return [(name, text) for name, text, _ in Recorder.marks]

    def test_no_missing_mark(self):
        for shown in (True, False):
            self.assertNotIn('M', [text for _, text in self.marks_for(shown)])

    def test_correct_answer_shown_on_wrong_and_blank_rows(self):
        marks = self.marks_for(True)
        self.assertIn(('s1', '#'), marks)
        self.assertIn(('s2', '#'), marks)


class PointsMark(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(grade_functions.points_mark(2.0), '2')
        self.assertEqual(grade_functions.points_mark('1.5'), '1.5')
        self.assertEqual(grade_functions.points_mark(2 / 3), '0.67')
        self.assertEqual(grade_functions.points_mark(0), '0')

    def test_not_a_number(self):
        self.assertIsNone(grade_functions.points_mark('CC: aorta'))
        self.assertIsNone(grade_functions.points_mark(None))
        self.assertIsNone(grade_functions.points_mark(float('nan')))


if __name__ == '__main__':
    unittest.main()
