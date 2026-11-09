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


class TestSuggestion(unittest.TestCase):
    OSTEO_FULL, OSTEO_PARTIAL = ['osteoclast'], ['osteoblast']   # 90% alike

    def suggest(self, text, threshold=None):
        return suggest_grade(text, self.OSTEO_FULL, 0.9, partial_texts=self.OSTEO_PARTIAL,
                             partial_threshold=threshold)

    def test_exact_partial_beats_a_similar_full_answer(self):
        self.assertEqual(self.suggest('Osteoblast'), 'CX')

    def test_exact_full_answer_is_correct(self):
        self.assertEqual(self.suggest('osteoclast'), 'CC')

    def test_near_miss_takes_the_grade_of_the_closer_answer(self):
        self.assertEqual(self.suggest('osteoblaast'), 'CX')
        self.assertEqual(self.suggest('osteoclaast'), 'CC')

    def test_answer_on_both_lists_earns_full_credit(self):
        self.assertEqual(suggest_grade('ulna', ['ulna'], 0.9, partial_texts=['ulna']), 'CC')

    def test_strictness_one_refuses_a_one_letter_misspelling(self):
        self.assertEqual(self.suggest('osteoclaast', threshold=1.0), 'XX')

    def test_strictness_one_refuses_a_misspelled_partial(self):
        self.assertEqual(self.suggest('osteoblaast', threshold=1.0), 'XX')

    def test_strictness_one_keeps_exact_answers(self):
        self.assertEqual(self.suggest(' OSTEOCLAST ', threshold=1.0), 'CC')
        self.assertEqual(self.suggest('osteoblast', threshold=1.0), 'CX')

    def test_strictness_below_the_correct_bar_leaves_it_alone(self):
        # 86% like "radius": correct at the default strictness
        self.assertEqual(suggest_grade('radious', ['radius'], 0.9, partial_threshold=0.5), 'CC')

    def test_strictness_above_the_correct_bar_raises_it(self):
        self.assertEqual(suggest_grade('radious', ['radius'], 0.9, partial_threshold=0.9), 'XX')

    def test_explanation_at_strictness_one(self):
        s = self.suggest('osteoblast', threshold=1.0)
        msg = explain_suggestion('osteoblast', self.OSTEO_FULL, self.OSTEO_PARTIAL, s, 1.0)
        self.assertIn('matches the partial-credit answer “osteoblast”', msg)


class TestExplain(unittest.TestCase):
    def test_correct_names_the_match(self):
        s, msg = explain('Renal Pelvis')
        self.assertEqual(s, 'CC')
        self.assertIn('correct. It matches “renal pelvis”', msg)

    def test_correct_near_miss_gives_the_likeness(self):
        s, msg = explain('renal pelvus')
        self.assertEqual(s, 'CC')
        self.assertIn('correct. It is 92% like “renal pelvis”', msg)

    def test_partial_from_the_list(self):
        s, msg = explain('pelvis')
        self.assertEqual(s, 'CX')
        self.assertIn('matches the partial-credit answer “pelvis”', msg)

    def test_partial_near_miss_gives_the_likeness(self):
        s, msg = explain('pelvus')
        self.assertEqual(s, 'CX')
        self.assertIn('83% like the partial-credit answer “pelvis”', msg)

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
