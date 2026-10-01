'''
An answer is graded without the window only when the student wrote a key
answer exactly (capitals and spacing aside); a near miss, such as a
misspelling, goes to the grader whether it is suggested as correct or as
partial. Upgrades after a key change follow the same rule.

    python -m unittest tests.test_graded_unseen -v
'''
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grade_functions  # noqa: E402
import openQ  # noqa: E402
from ocr import exact_match  # noqa: E402

QK = 'openQ_1A'
FULL, PARTIAL = ['radius'], ['forearm bone']


class Shown(Exception):
    '''Raised in place of opening the grading window.'''


def grade(reading, strictness=0.5, review_perfect=False):
    '''The grade given without review, or 'shown' when the window opens.'''
    q = object.__new__(openQ.OpenQs)
    q.__dict__.update(_ai_texts={QK: {1: reading}}, openQkeytext={}, openQkeyimgs={},
                      _transcriptions={},
                      acceptable_answers={QK: list(FULL)},
                      partial_credit_answers={QK: list(PARTIAL)},
                      _strictness=strictness, _review_perfect=review_perfect, _root=None)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / 'page.png'
        Image.new('RGB', (40, 40), 'white').save(page)
        with mock.patch.object(openQ.tk, 'Toplevel', side_effect=Shown):
            try:
                return q._gradeOneAnswer(str(page), QK, (0, 0, 40, 40), img_idx=1)
            except Shown:
                return 'shown'


class TestReview(unittest.TestCase):
    def test_exact_full_answer_is_accepted(self):
        self.assertEqual(grade(' Radius'), 'CC')

    def test_exact_full_answer_is_shown_when_reviewing_perfect_matches(self):
        self.assertEqual(grade('radius', review_perfect=True), 'shown')

    def test_misspelled_full_answer_is_shown(self):
        # 86% like "radius": suggested correct, but not graded unseen
        self.assertEqual(grade('radious'), 'shown')

    def test_exact_partial_answer_is_accepted(self):
        self.assertEqual(grade('Forearm  Bone'), 'CX')

    def test_exact_partial_answer_is_accepted_when_reviewing_perfect_matches(self):
        self.assertEqual(grade('forearm bone', review_perfect=True), 'CX')

    def test_misspelled_partial_answer_is_shown(self):
        self.assertEqual(grade('forarm bone'), 'shown')

    def test_misspelled_full_answer_offered_partial_is_shown(self):
        # 67% like "radius": partial by strictness, not by the key
        self.assertEqual(grade('raduis'), 'shown')

    def test_wrong_answer_is_shown(self):
        self.assertEqual(grade('ulna', strictness=0), 'shown')

    def test_exact_match_ignores_only_capitals_and_spacing(self):
        self.assertTrue(exact_match(' Forearm   BONE ', PARTIAL))
        self.assertFalse(exact_match('forearm bones', PARTIAL))
        self.assertFalse(exact_match('radius.', FULL))
        self.assertFalse(exact_match('', PARTIAL))


class TestUpgrades(unittest.TestCase):
    READINGS = {1: 'raduis', 2: 'forarm bone', 3: 'forearm bone', 4: 'Radius', 5: 'radious'}

    def test_upgrade_while_grading_needs_an_exact_match(self):
        q = object.__new__(openQ.OpenQs)
        q.__dict__.update(
            _transcriptions={QK: {i: (t, 0.9) for i, t in self.READINGS.items()}},
            openQres=pd.DataFrame({QK: ['', 'XX', 'XX', 'XX', 'XX', 'XX']}),
            acceptable_answers={QK: list(FULL)}, partial_credit_answers={QK: list(PARTIAL)},
            _strictness=0.5)
        self.assertEqual(q._upgrade_earlier(QK, 6), 2)
        self.assertEqual(list(q.openQres[QK][1:]), ['XX', 'XX', 'CX', 'CC', 'XX'])

    def test_regrade_needs_an_exact_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = Path(tmp) / 'results.csv'
            pd.DataFrame({'index': [str(i) for i in range(6)],
                          QK: ['', 'XX', 'XX', 'XX', 'XX', 'XX']}).to_csv(csv, index=False)
            trans = {QK: {str(i): [t, 0.9] for i, t in self.READINGS.items()}}
            n = grade_functions.regrade_open_questions(
                str(csv), {QK: FULL}, trans, partial_answers={QK: PARTIAL})
            self.assertEqual(n, 2)
            out = pd.read_csv(csv, dtype=object)
            self.assertEqual(list(out[QK][1:]),
                             ['XX', 'XX', 'CX: forearm bone', 'CC: Radius', 'XX'])


if __name__ == '__main__':
    unittest.main()
