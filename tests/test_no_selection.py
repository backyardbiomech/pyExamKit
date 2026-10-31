'''
A select-all with no correct choice: the right answer is an unmarked row.
The key holds the 'none' sentinel for it, which has to grade (full credit
for a blank row, nothing for any mark), survive a key-file round trip, and
stay out of the code that reads a key as a set of bubble letters.

    python -m unittest tests.test_no_selection -v
'''
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import exam_key_writer  # noqa: E402
import grade_functions as gf  # noqa: E402
import keyformat  # noqa: E402
import outputs  # noqa: E402
from models import Answer, Question  # noqa: E402

NONE = keyformat.NO_SELECTION


class GradedKeyTest(unittest.TestCase):
    def test_sentinel_is_graded(self):
        self.assertTrue(gf.graded_key(NONE))

    def test_ignore_and_blank_are_not(self):
        for key in ('ignore', '', float('nan')):
            self.assertFalse(gf.graded_key(key), key)


class ScoreAnswerTest(unittest.TestCase):
    def score(self, ans):
        return gf.score_answer(ans, NONE, 2.0, partial=True)

    def test_blank_row_earns_the_points(self):
        # '-' is what the scanner writes for a row with nothing in it
        for ans in ('-', '', '  ', float('nan')):
            self.assertEqual(self.score(ans), (2.0, True), repr(ans))

    def test_any_mark_earns_nothing(self):
        for ans in ('A', 'C', 'ABD'):
            self.assertEqual(self.score(ans), (0.0, False), ans)

    def test_all_or_nothing_without_partial(self):
        self.assertEqual(gf.score_answer('-', NONE, 2.0, partial=False), (2.0, True))
        self.assertEqual(gf.score_answer('A', NONE, 2.0, partial=False), (0.0, False))

    def test_accepted_alongside_a_lettered_key(self):
        # a key edit may accept both a letter and an unmarked row
        keys = ['B', NONE]
        self.assertEqual(gf.score_answer('B', keys, 2.0, partial=True), (2.0, True))
        self.assertEqual(gf.score_answer('-', keys, 2.0, partial=True), (2.0, True))
        self.assertEqual(gf.score_answer('A', keys, 2.0, partial=True), (0.0, False))

    def test_lettered_keys_unchanged(self):
        self.assertEqual(gf.score_answer('BD', 'BD', 2.0, partial=True), (2.0, True))
        self.assertEqual(gf.score_answer('B', 'BD', 2.0, partial=True), (1.0, False))
        self.assertEqual(gf.score_answer('B', 'B', 2.0, partial=True), (2.0, True))


class UnmarkedTest(unittest.TestCase):
    def test_what_counts_as_unmarked(self):
        for v in ('-', '', '   ', float('nan'), None):
            self.assertTrue(gf.unmarked(v), repr(v))
        for v in ('A', 'ABC', '0'):
            self.assertFalse(gf.unmarked(v), repr(v))


class KeyWriterTest(unittest.TestCase):
    def ma(self, correct):
        answers = [Answer(text=t, is_correct=c)
                   for t, c in zip('abcd', correct)]
        return Question(q_type='MA', text='pick any that apply', answers=answers)

    def test_no_correct_choice_writes_the_sentinel(self):
        q = self.ma([False, False, False, False])
        self.assertEqual(exam_key_writer._mc_answer(q), NONE)

    def test_one_correct_choice_still_writes_its_letter(self):
        q = self.ma([False, True, False, False])
        self.assertEqual(exam_key_writer._mc_answer(q), 'B')

    def test_several_correct_choices_unchanged(self):
        q = self.ma([True, False, True, False])
        self.assertEqual(exam_key_writer._mc_answer(q), 'AC')


class NormalizeAnswerTest(unittest.TestCase):
    def test_sentinels_are_stored_lowercase(self):
        for typed in ('none', 'NONE', ' None ', 'ignore', 'IGNORE'):
            got = keyformat.normalize_answer(typed)
            self.assertIn(got, keyformat.ANSWER_SENTINELS, typed)
            self.assertEqual(got, typed.strip().lower())

    def test_letters_are_stored_uppercase(self):
        self.assertEqual(keyformat.normalize_answer('ab'), 'AB')
        self.assertEqual(keyformat.normalize_answer(' c '), 'C')


class DisplayTest(unittest.TestCase):
    def graded(self):
        df = pd.DataFrame({'Q001': [NONE, '-'], 'Q002': ['AC', 'A']},
                          index=['0', '1'])
        pts = df.copy()
        return outputs.Graded(version='A', df=df, pts=pts,
                              possible={'Q001': 2.0, 'Q002': 2.0},
                              choices={'Q001': 'CADB', 'Q002': 'CADB'})

    def test_key_label_names_it_in_words(self):
        g = self.graded()
        self.assertEqual(g.key_label('Q001'), 'no marks')
        self.assertEqual(g.key_label('Q001', bank=True), 'no marks')

    def test_letter_mappers_pass_it_through(self):
        g = self.graded()
        self.assertEqual(g.bank_letters('Q001', NONE), NONE)
        self.assertEqual(g.sheet_letters('Q001', NONE), NONE)
        # and still map real letters
        # Q002's sheet A is the bank's C and its C is the bank's D
        self.assertEqual(g.bank_letters('Q002', 'AC'), 'CD')


class RoundTripTest(unittest.TestCase):
    def test_key_csv_keeps_the_sentinel_without_warning(self):
        data = {'bubble_answers': {'Q001': NONE, 'Q002': 'AC'},
                'point_values': {'Q001': 2, 'Q002': 2},
                'num_questions': 2}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'key.csv'
            keyformat.save_key_csv(str(path), data)
            back = keyformat.load_key_csv(str(path))
        self.assertEqual(back['bubble_answers']['Q001'], NONE)
        self.assertEqual(back['bubble_answers']['Q002'], 'AC')


if __name__ == '__main__':
    unittest.main()
