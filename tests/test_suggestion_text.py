'''
The grading window's one-line explanation of each suggested grade.

    python -m unittest tests.test_suggestion_text -v
'''
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr import explain_suggestion, suggest_grade  # noqa: E402

FULL, PARTIAL = ['renal pelvis', 'pelvis of kidney'], ['pelvis']


def explain(text, threshold=None):
    s = suggest_grade(text, FULL, 0.9, partial_texts=PARTIAL, partial_threshold=threshold)
    return s, explain_suggestion(text, FULL, PARTIAL, s, threshold)


class TestExplain(unittest.TestCase):
    def test_correct_names_the_match(self):
        s, msg = explain('renal pelvus')
        self.assertEqual(s, 'CC')
        self.assertIn('correct', msg)
        self.assertIn('“renal pelvis”', msg)

    def test_partial_from_the_list(self):
        s, msg = explain('pelvis')
        self.assertEqual(s, 'CX')
        self.assertIn('partial-credit answer “pelvis”', msg)

    def test_partial_from_strictness(self):
        s, msg = explain('renal pyramid', threshold=0.5)
        self.assertEqual(s, 'CX')
        self.assertIn('strictness', msg)

    def test_wrong_names_the_closest(self):
        s, msg = explain('seminal vesicle')
        self.assertEqual(s, 'XX')
        self.assertTrue(msg.startswith('Suggested: wrong.'))
        self.assertIn('% alike', msg)

    def test_no_reading(self):
        self.assertIn('by eye', explain_suggestion('', FULL, PARTIAL, None))

    def test_blank_box(self):
        msg = explain_suggestion('', FULL, PARTIAL, 'XX', blank=True)
        self.assertEqual(msg, 'Suggested: wrong. The box is blank. Enter accepts.')

    def test_empty_key(self):
        self.assertIn('no answers', explain_suggestion('urine', [], [], None))


if __name__ == '__main__':
    unittest.main()
