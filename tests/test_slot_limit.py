"""
The printed answer sheet has 150 numbered question slots, and MD, OR, and MT
questions each occupy one slot per dropdown, ordered item, or left-hand item.
So an exam's slot count runs ahead of its question count, and the count that
has to fit the paper is the slot count -- which nothing checked before.

Fixtures here are fabricated content, matching the rest of tests/.
"""
import random
import tempfile
import unittest
from pathlib import Path

from exam_builder import (ANSWER_SHEET_SIZES, BuildConfig, ExamBuilder,
                          MAX_QUESTION_SLOTS, answer_sheet_for, slot_count)
from models import Dropdown, MatchLeft, MatchRight, OrderItem, Question


def _bank(n_mc: int, n_or: int = 0, or_items: int = 6) -> str:
    """A bank of n_mc single-slot MC questions plus n_or orderings."""
    blocks = [f"MC\n{i + 1}. Fabricated question {i}?\n*A. a\nB. b\n" for i in range(n_mc)]
    for j in range(n_or):
        items = '\n'.join(f'{k + 1}: item {k}' for k in range(or_items))
        blocks.append(f"OR\n{1000 + j}. Fabricated ordering.\n{items}\n")
    return '\n'.join(blocks)


def _build(text: str):
    tmp = Path(tempfile.mkdtemp(prefix='slot_limit_')) / 'bank.txt'
    tmp.write_text(text, encoding='utf-8')
    random.seed(0)
    return ExamBuilder().build(BuildConfig(
        title='Slot Limit', course='TEST', num_versions=1,
        shuffle_questions=False, shuffle_answers=False, exact_file=tmp,
        default_points=1.0,
    ))


class SlotCount(unittest.TestCase):
    def test_ordinary_question_takes_one_slot(self):
        for q_type in ('MC', 'MA', 'SA', 'TF'):
            with self.subTest(q_type=q_type):
                self.assertEqual(slot_count(Question(q_type=q_type, text='x')), 1)

    def test_md_takes_one_slot_per_dropdown(self):
        q = Question(q_type='MD', text='x',
                     dropdowns=[Dropdown(name='a'), Dropdown(name='b'), Dropdown(name='c')])
        self.assertEqual(slot_count(q), 3)

    def test_or_takes_one_slot_per_item(self):
        q = Question(q_type='OR', text='x',
                     order_items=[OrderItem(text=str(i), rank=i) for i in (1, 2, 3, 4)])
        self.assertEqual(slot_count(q), 4)

    def test_mt_takes_one_slot_per_left_not_per_right(self):
        q = Question(
            q_type='MT', text='x',
            match_lefts=[MatchLeft(text='l1', correct_label='r1'),
                         MatchLeft(text='l2', correct_label='r1')],
            match_rights=[MatchRight(label='r1', text='a'), MatchRight(label='r2', text='b'),
                          MatchRight(label='r3', text='c')],
        )
        self.assertEqual(slot_count(q), 2)


class AnswerSheetChoice(unittest.TestCase):
    def test_picks_the_smallest_sheet_that_fits(self):
        self.assertEqual(answer_sheet_for(1), 30)
        self.assertEqual(answer_sheet_for(30), 30)
        self.assertEqual(answer_sheet_for(31), 60)
        self.assertEqual(answer_sheet_for(150), 150)

    def test_no_sheet_fits_past_the_limit(self):
        self.assertIsNone(answer_sheet_for(MAX_QUESTION_SLOTS + 1))

    def test_largest_sheet_is_the_limit(self):
        self.assertEqual(max(ANSWER_SHEET_SIZES), MAX_QUESTION_SLOTS)


class BuildWarnsPastTheSheet(unittest.TestCase):
    def test_no_warning_when_it_fits(self):
        versions, warnings = _build(_bank(n_mc=20, n_or=2))
        slots = sum(slot_count(q) for q in versions[0].questions)
        self.assertEqual(slots, 32)  # 20 single slots + 2 orderings of 6
        self.assertEqual(warnings, [])

    def test_question_count_alone_would_have_looked_safe(self):
        """The regression this guards: 109 questions reads as comfortably
        under 150, but the orderings push it to 154 real slots."""
        versions, warnings = _build(_bank(n_mc=100, n_or=9))
        self.assertEqual(len(versions[0].questions), 109)
        self.assertEqual(sum(slot_count(q) for q in versions[0].questions), 154)
        self.assertEqual(len(warnings), 1)
        self.assertIn('154 answer-sheet slots', warnings[0])
        self.assertIn(str(MAX_QUESTION_SLOTS), warnings[0])

    def test_warns_on_plain_questions_too(self):
        _, warnings = _build(_bank(n_mc=MAX_QUESTION_SLOTS + 1))
        self.assertEqual(len(warnings), 1)
        self.assertIn(f'{MAX_QUESTION_SLOTS + 1} answer-sheet slots', warnings[0])

    def test_exactly_at_the_limit_is_fine(self):
        _, warnings = _build(_bank(n_mc=MAX_QUESTION_SLOTS))
        self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
