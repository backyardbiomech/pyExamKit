'''
An answer is graded without the window only when the student wrote a key
answer exactly (capitals and spacing aside); a near miss, such as a
misspelling, goes to the grader whether it is suggested as correct or as
partial. Upgrades after a key change follow the same rule.

    python -m unittest tests.test_graded_unseen -v
'''
import sys
import tempfile
import tkinter as tk
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


def grade(reading, strictness=0.5, review_perfect=False, add=None, partial=PARTIAL):
    '''The grade given without review, or 'shown' when the window opens.
    add is an answer the grader writes into the key first.'''
    q = object.__new__(openQ.OpenQs)
    q.__dict__.update(_ai_texts={QK: {1: reading}}, openQkeytext={}, openQkeyimgs={},
                      _transcriptions={}, _added_answers={},
                      acceptable_answers={QK: list(FULL)},
                      partial_credit_answers={QK: list(partial)},
                      _strictness=strictness, _review_perfect=review_perfect, _root=None)
    if add:
        q._add_acceptable_and_regrade(QK, add, 1)
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

    def test_exact_partial_similar_to_a_full_answer_is_accepted(self):
        # "radios" is 83% like "radius" but is a partial answer exactly
        self.assertEqual(grade('radios', partial=['radios']), 'CX')

    def test_answer_added_to_the_key_is_accepted_when_reviewing_perfect_matches(self):
        self.assertEqual(grade(' Radial  Bone', review_perfect=True, add='radial bone'), 'CC')

    def test_other_answers_are_still_shown_after_an_addition(self):
        self.assertEqual(grade('radius', review_perfect=True, add='radial bone'), 'shown')

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

    def test_upgrade_after_grading_needs_an_exact_match(self):
        self.assertEqual([grade_functions.upgraded_cell('XX', t, FULL, PARTIAL)
                          for t in self.READINGS.values()],
                         [None, None, 'CX: forearm bone', 'CC: Radius', None])

    def test_upgrade_never_lowers(self):
        self.assertIsNone(grade_functions.upgraded_cell('CC: x', 'forearm bone', FULL, PARTIAL))
        self.assertIsNone(grade_functions.upgraded_cell('CX', 'forearm bone', FULL, PARTIAL))
        self.assertEqual(grade_functions.upgraded_cell('CX', 'radius', FULL, PARTIAL), 'CC: radius')


class TestCorrectingAReading(unittest.TestCase):
    MISREAD, RIGHT = 'radious', 'radius'

    def window(self, reading, type_in=None):
        '''The real grading window: type_in goes in the reading's field and
        Correct is clicked. Returns the grader object and the grade.'''
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display for Tk')
        self.addCleanup(root.destroy)
        root.withdraw()
        q = object.__new__(openQ.OpenQs)
        q.__dict__.update(_ai_texts={QK: {1: reading}}, openQkeytext={}, openQkeyimgs={},
                          _transcriptions={}, _added_answers={},
                          acceptable_answers={QK: list(FULL)},
                          partial_credit_answers={QK: list(PARTIAL)}, _strictness=0.5,
                          _review_perfect=False, _root=root, _progress=None, _q_text={},
                          _student_info=None, _key_file_mode=False, _key_file_path=None)

        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)

        def click_correct(win):
            win.update()
            field = next(w for w in walk(win) if isinstance(w, tk.Entry) and w.get() == reading)
            field.delete(0, 'end')
            field.insert(0, type_in)
            next(w for w in walk(win) if isinstance(w, tk.Button)
                 and w.cget('text').startswith('Correct')).invoke()

        root.wait_window = click_correct
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / 'page.png'
            Image.new('RGB', (40, 40), 'white').save(page)
            return q, q._gradeOneAnswer(str(page), QK, (0, 0, 40, 40), img_idx=1)

    def test_a_correction_made_in_the_window_is_kept(self):
        q, g = self.window(self.MISREAD, self.RIGHT)
        self.assertEqual(g, 'CC')
        self.assertEqual(q._transcriptions[QK][1][0], self.RIGHT)
        self.assertEqual(q._ai_texts[QK][1], self.RIGHT)

    def test_a_field_left_alone_changes_nothing(self):
        q, _ = self.window(self.MISREAD, self.MISREAD)
        self.assertEqual(q._transcriptions[QK][1][0], self.MISREAD)

    def test_a_later_key_answer_finds_the_corrected_reading(self):
        q = object.__new__(openQ.OpenQs)
        q.__dict__.update(_transcriptions={QK: {1: ('acetulcholine', 0.9)}}, _ai_texts={},
                          _added_answers={}, openQres=pd.DataFrame({QK: ['', 'XX']}),
                          acceptable_answers={QK: []}, partial_credit_answers={QK: []})
        self.assertEqual(q._add_acceptable_and_regrade(QK, 'acetylcholine', 2), 0)
        q.acceptable_answers[QK] = []
        q._correct_reading(QK, 1, 'acetylcholine')
        self.assertEqual(q._add_acceptable_and_regrade(QK, 'acetylcholine', 2), 1)
        self.assertEqual(q.openQres[QK][1], 'CC')


if __name__ == '__main__':
    unittest.main()
