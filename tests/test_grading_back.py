'''
Back in the grading window returns to the last answer the grader reviewed,
skipping answers accepted without review, across question boundaries too.

    python -m unittest tests.test_grading_back -v
'''
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openQ  # noqa: E402


class Script:
    '''
    Stands in for the grading window. `auto` answers are accepted without
    review unless forced into view; `presses` are what the grader does at
    each answer shown, in order.
    '''

    def __init__(self, auto, presses):
        self.auto, self.presses, self.shown = set(auto), list(presses), []

    def __call__(self, q, filename, k, v, img_idx=None, force_show=False):
        item = (k, img_idx - 1)
        if item in self.auto and not force_show:
            q._last_shown = False
            return 'CC'
        q._last_shown = True
        self.shown.append(item)
        return self.presses.pop(0)


def run(questions, students, auto, presses, who=None):
    q = object.__new__(openQ.OpenQs)
    script = Script(auto, presses)
    q.__dict__.update(
        _locate=lambda k, s: ('page.jpg', (0, 0, 1, 1)) if who is None or s in who[k] else None,
        openQres=pd.DataFrame('', index=range(students + 1), columns=questions),
        _save_progress_cache=lambda **kw: None)
    q._gradeOneAnswer = lambda *a, **kw: script(q, *a, **kw)
    q._grade_all(questions, [None] * (students + 1), students)
    return script.shown, q.openQres


class TestBack(unittest.TestCase):
    def test_back_skips_an_auto_accepted_answer(self):
        # Student 1's answer is accepted without review; Back from student 2
        # goes to student 0, the last one the grader saw
        shown, res = run(['1A'], 3, auto={('1A', 1)}, presses=['XX', 'back', 'CC', 'XX'])
        self.assertEqual(shown, [('1A', 0), ('1A', 2), ('1A', 0), ('1A', 2)])
        self.assertEqual(list(res['1A'][1:]), ['CC', 'CC', 'XX'])

    def test_back_crosses_into_the_previous_question(self):
        shown, _ = run(['1A', '1B'], 2, auto={('1A', 1)}, presses=['XX', 'back', 'CC', 'XX', 'XX'])
        self.assertEqual(shown, [('1A', 0), ('1B', 0), ('1A', 0), ('1B', 0), ('1B', 1)])

    def test_back_twice_walks_further_back_then_forward_again(self):
        shown, _ = run(['1A'], 3, auto=set(),
                       presses=['XX', 'XX', 'back', 'back', 'CC', 'CC', 'CC'])
        self.assertEqual(shown, [('1A', 0), ('1A', 1), ('1A', 2), ('1A', 1), ('1A', 0),
                                 ('1A', 1), ('1A', 2)])

    def test_back_at_the_first_answer_shows_it_again(self):
        shown, _ = run(['1A'], 1, auto=set(), presses=['back', 'CC'])
        self.assertEqual(shown, [('1A', 0), ('1A', 0)])

    def test_reviewed_answer_is_shown_even_if_now_auto_accepted(self):
        # After student 0 is reviewed, the grader adds a key answer that would
        # accept it on sight; Back from student 1 must still show it
        class KeyChanges(Script):
            def __call__(self, q, *a, **kw):
                out = super().__call__(q, *a, **kw)
                self.auto.add(('1A', 0))
                return out
        q = object.__new__(openQ.OpenQs)
        script = KeyChanges(set(), ['XX', 'back', 'CC', 'CC'])
        q.__dict__.update(_locate=lambda k, s: ('page.jpg', (0, 0, 1, 1)),
                          openQres=pd.DataFrame('', index=range(3), columns=['1A']),
                          _save_progress_cache=lambda **kw: None)
        q._gradeOneAnswer = lambda *a, **kw: script(q, *a, **kw)
        q._grade_all(['1A'], [None] * 3, 2)
        self.assertEqual(script.shown, [('1A', 0), ('1A', 1), ('1A', 0), ('1A', 1)])
        self.assertEqual(q.openQres.loc[1, '1A'], 'CC')

    def test_students_without_the_question_are_never_visited(self):
        who = {'1A': {0, 2}, '1C': {1}}
        shown, res = run(['1A', '1C'], 3, auto=set(), presses=['XX', 'back', 'CC', 'CC', 'CC'],
                         who=who)
        self.assertEqual(shown, [('1A', 0), ('1A', 2), ('1A', 0), ('1A', 2), ('1C', 1)])
        self.assertEqual(res.loc[3, '1C'], '')      # student 2 has no 1C


if __name__ == '__main__':
    unittest.main()
