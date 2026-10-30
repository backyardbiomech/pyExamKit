"""
Answer text instead of letters (docs/dev/results-tab.md, Phase 5): the key
records the shown choices' text in bank order, and Graded.labeled keeps the
letter it is given while naming the choice the bank had behind it.

    python -m unittest tests.test_options_text -v
"""
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import grade_functions  # noqa: E402
import outputs  # noqa: E402
from exam_key_writer import build_key_data  # noqa: E402
from models import Answer, ExamVersion, MatchLeft, MatchRight, OrderItem, Question  # noqa: E402


def version_of(*questions) -> ExamVersion:
    return ExamVersion(title='Quiz', course='TEST101', version_num=1, questions=list(questions))


def shuffled_mc() -> Question:
    # Bank order is [alpha, <b>beta</b>, gamma, delta]; the sheet shows C, A, D, B
    bank = ['alpha', '<b>beta</b>', 'gamma', 'delta']
    shown = [2, 0, 3, 1]
    q = Question(q_type='MC', text='stem', source_id='bank.md#1')
    q.answers = [Answer(text=bank[i], is_correct=(i == 1), src=i) for i in shown]
    return q


class KeyWriterOptions(unittest.TestCase):
    def key(self, *qs):
        try:
            return build_key_data(version_of(*qs))
        except Exception as exc:        # pragma: no cover - fixture shape drifted
            self.fail(f'could not build key data: {exc!r}')

    def test_mc_options_in_bank_order(self):
        data = self.key(shuffled_mc())
        self.assertEqual(data['choices']['Q001'], 'CADB')
        self.assertEqual(data['options']['Q001'], ['alpha', 'beta', 'gamma', 'delta'])

    def test_no_options_without_bank_positions(self):
        q = shuffled_mc()
        for a in q.answers:
            a.src = -1
        self.assertEqual(self.key(q)['options'], {})

    def test_or_options_in_true_order(self):
        q = Question(q_type='OR', text='order', source_id='bank.md#2')
        q.order_items = [OrderItem(text='second', rank=2), OrderItem(text='first', rank=1)]
        data = self.key(q)
        self.assertEqual(data['options']['Q001'], ['first', 'second'])

    def test_mt_options_by_bank_position(self):
        q = Question(q_type='MT', text='match', source_id='bank.md#3')
        q.match_lefts = [MatchLeft(text='L', correct_label='r1', src=0)]
        q.match_rights = [MatchRight(label='r0', text='zero', src=1),
                          MatchRight(label='r1', text='one', src=0)]
        self.assertEqual(self.key(q)['options']['Q001'], ['one', 'zero'])


def graded(options=None, choices='CADB') -> outputs.Graded:
    return outputs.Graded(
        version='A', df=pd.DataFrame(), pts=pd.DataFrame(), possible={},
        choices={'Q001': choices} if choices else {},
        options={'Q001': options} if options else {})


class Labeled(unittest.TestCase):
    OPTS = ['alpha', 'beta', 'gamma', 'delta']

    def test_sheet_letter_keeps_its_letter_and_gains_the_bank_text(self):
        # The sheet printed the bank's C first, so its A said gamma; the letter
        # shown is the one the student bubbled, not the bank's
        g = graded(self.OPTS)
        self.assertEqual(g.labeled('Q001', 'A'), 'A — gamma')
        self.assertEqual(g.labeled('Q001', 'D'), 'D — beta')

    def test_bank_letter_is_not_converted(self):
        self.assertEqual(graded(self.OPTS).labeled('Q001', 'A', bank=True), 'A — alpha')

    def test_select_all(self):
        self.assertEqual(graded(self.OPTS).labeled('Q001', 'AB'),
                         'A — gamma; B — alpha')

    def test_written_code_and_non_letters_unchanged(self):
        g = graded(self.OPTS)
        self.assertEqual(g.labeled('openQ_1', 'CC'), 'CC')
        self.assertEqual(g.labeled('Q001', 'ignore'), 'ignore')
        self.assertEqual(g.labeled('Q001', ''), '')

    def test_no_options_recorded(self):
        g = graded(None)
        self.assertEqual(g.labeled('Q001', 'A'), 'A')
        self.assertEqual(g.option_text('Q001', 'C'), '')
        self.assertEqual(g.option_text('Q009', 'C'), '')

    def test_gap_in_options(self):
        self.assertEqual(graded(['alpha', '']).labeled('Q001', 'D'), 'D')


class RecordCarriesOptions(unittest.TestCase):
    def test_options_reach_graded_and_item(self):
        root = Path(tempfile.mkdtemp())
        try:
            out = root / 'ExamScanner_outputs'
            (out / 'marked').mkdir(parents=True)
            path = Path(outputs.results_csv(out, 'A'))
            pd.DataFrame([['0', 'KEY', '', '', 'A'], ['1', 'AMES', 'X', '1', 'A']],
                         columns=['index', 'LastName', 'FirstName', 'studentID', 'Q001']
                         ).to_csv(path, index=False)
            with contextlib.redirect_stdout(io.StringIO()):
                grade_functions.gradeResults(
                    str(path), False, False, 1, 2, out / 'marked', key_data={
                        'sources': {'Q001': 'bank.md#1'}, 'choices': {'Q001': 'CADB'},
                        'options': {'Q001': ['alpha', 'beta', 'gamma', 'delta']}})
            g = outputs.load(path)
            self.assertEqual(g.labeled('Q001', 'A'), 'A — gamma')
            table = outputs.item_table([g])
            self.assertEqual(table.items[0].options, ['alpha', 'beta', 'gamma', 'delta'])
        finally:
            shutil.rmtree(root)


if __name__ == '__main__':
    unittest.main()
