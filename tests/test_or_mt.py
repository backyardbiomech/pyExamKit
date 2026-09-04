"""
Phase 3.5 verification: OR (ordering) and MT (matching) question types,
per docs/ordering-matching-spec.md.

Fixtures under tests/fixtures/or_mt/ are fabricated content, not real course
material, matching how tests/ten_column_key.csv and
tests/fixtures/build_migration/ were built for this public repo.
"""
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from parser import parse_file
from exam_builder import BuildConfig, ExamBuilder, _trim_mt_rights
from exam_key_writer import _distribute_points, build_key_data
from models import MatchLeft, MatchRight, Question
from renderer import ExamRenderer

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'or_mt'
BASIC = FIXTURE_DIR / 'basic.txt'
GUARDS = FIXTURE_DIR / 'guards.txt'
MT_OVER_LIMIT = FIXTURE_DIR / 'mt_over_limit.txt'


class ParseOrdering(unittest.TestCase):
    def setUp(self):
        questions, warnings = parse_file(BASIC)
        self.assertEqual(warnings, [])
        self.or_q = next(q for q in questions if q.q_type == 'OR')

    def test_item_count_and_ranks(self):
        ranks = sorted(item.rank for item in self.or_q.order_items)
        self.assertEqual(ranks, [1, 2, 3])

    def test_item_text_and_formatting(self):
        by_rank = {item.rank: item.text for item in self.or_q.order_items}
        self.assertEqual(by_rank[1], 'epidermis')
        self.assertEqual(by_rank[2], 'dermis')
        self.assertEqual(by_rank[3], 'hypodermis')

    def test_labels(self):
        self.assertEqual(self.or_q.order_top_label, 'shallow')
        self.assertEqual(self.or_q.order_bottom_label, 'deep')

    def test_stem_markdown_formatting_applied(self):
        self.assertIn('<strong>shallow</strong>', self.or_q.text)


class ParseMatching(unittest.TestCase):
    def setUp(self):
        questions, warnings = parse_file(BASIC)
        self.assertEqual(warnings, [])
        self.mt_q = next(q for q in questions if q.q_type == 'MT')

    def test_left_count_and_text(self):
        self.assertEqual(len(self.mt_q.match_lefts), 3)
        texts = [left.text for left in self.mt_q.match_lefts]
        self.assertEqual(texts, ['alpha', 'beta', 'gamma'])

    def test_shared_right_label(self):
        labels = [left.correct_label for left in self.mt_q.match_lefts]
        self.assertEqual(labels, ['catB', 'catA', 'catB'])

    def test_rights_deduplicated(self):
        # catB is referenced twice but declared once -> one MatchRight, not two.
        right_labels = [r.label for r in self.mt_q.match_rights]
        self.assertEqual(sorted(right_labels), ['catA', 'catB'])

    def test_right_text(self):
        by_label = {r.label: r.text for r in self.mt_q.match_rights}
        self.assertEqual(by_label['catA'], 'first category')
        self.assertEqual(by_label['catB'], 'second category')


class ParserGuards(unittest.TestCase):
    """The four structural guards that reject at parse time, each naming the
    file and block number (the fifth guard, a post-trim MT rejection, can't
    run until exam_builder trims -- see TrimMtRightsGuard below)."""

    @classmethod
    def setUpClass(cls):
        cls.questions, cls.warnings = parse_file(GUARDS)

    def test_four_bad_blocks_rejected_two_clean_ones_kept(self):
        self.assertEqual(len(self.warnings), 4)
        self.assertEqual(len(self.questions), 2)
        self.assertEqual({q.q_type for q in self.questions}, {'OR', 'MT'})

    def test_or_too_many_items(self):
        msg = next(w for w in self.warnings if 'Block 1' in w)
        self.assertIn('guards.txt', msg)
        self.assertIn('7 items', msg)
        self.assertIn('at most 6', msg)

    def test_or_too_few_items(self):
        msg = next(w for w in self.warnings if 'Block 2' in w)
        self.assertIn('guards.txt', msg)
        self.assertIn('only 1', msg)
        self.assertIn('at least 2', msg)

    def test_mt_no_lefts(self):
        msg = next(w for w in self.warnings if 'Block 3' in w)
        self.assertIn('guards.txt', msg)
        self.assertIn('no left-side items', msg)

    def test_mt_bad_label_reference(self):
        msg = next(w for w in self.warnings if 'Block 4' in w)
        self.assertIn('guards.txt', msg)
        self.assertIn("'rightX'", msg)
        self.assertIn('no matching right entry', msg)

    def test_or_at_six_item_ceiling_survives(self):
        or_q = next(q for q in self.questions if q.q_type == 'OR')
        self.assertEqual(len(or_q.order_items), 6)

    def test_mt_shared_right_survives(self):
        mt_q = next(q for q in self.questions if q.q_type == 'MT')
        self.assertEqual(len(mt_q.match_lefts), 3)
        self.assertEqual(len(mt_q.match_rights), 2)


class TrimMtRightsUnit(unittest.TestCase):
    def _mt(self, n_lefts_sharing_one_right: int, n_distractors: int) -> Question:
        """Build an MT question with n_lefts_sharing_one_right lefts that all
        share ONE required right, plus n_distractors extra unused rights."""
        lefts = [MatchLeft(text=f'left{i}', correct_label='req') for i in range(n_lefts_sharing_one_right)]
        rights = [MatchRight(label='req', text='required right')]
        rights += [MatchRight(label=f'd{i}', text=f'distractor {i}') for i in range(n_distractors)]
        return Question(q_type='MT', text='q', match_lefts=lefts, match_rights=rights)

    def test_no_trim_needed_below_limit(self):
        q = self._mt(2, 3)  # 4 rights total
        trimmed, warn = _trim_mt_rights(q)
        self.assertIsNone(warn)
        self.assertEqual(len(trimmed.match_rights), 4)

    def test_trims_distractors_down_to_six(self):
        q = self._mt(1, 9)  # 1 required + 9 distractors = 10 rights
        trimmed, warn = _trim_mt_rights(q)
        self.assertIsNone(warn)
        self.assertEqual(len(trimmed.match_rights), 6)
        self.assertIn('req', {r.label for r in trimmed.match_rights})

    def test_required_rights_alone_exceed_limit(self):
        # 7 lefts, each requiring its OWN right (see mt_over_limit.txt) ->
        # 7 required rights, nothing droppable, still over the limit.
        lefts = [MatchLeft(text=f'left{i}', correct_label=f'r{i}') for i in range(7)]
        rights = [MatchRight(label=f'r{i}', text=f'right {i}') for i in range(7)]
        q = Question(q_type='MT', text='q', match_lefts=lefts, match_rights=rights)
        trimmed, warn = _trim_mt_rights(q)
        self.assertIsNotNone(warn)
        self.assertIn('exceeding the 6-option', warn)

    def test_non_mt_question_passes_through(self):
        q = Question(q_type='MC', text='q')
        trimmed, warn = _trim_mt_rights(q)
        self.assertIsNone(warn)
        self.assertIs(trimmed, q)


class TrimMtRightsGuard(unittest.TestCase):
    """The fifth guard (post-trim rejection) runs in exam_builder, not
    parser.py, since it depends on random distractor trimming -- so it's
    identified by file name + question text rather than a block number."""

    def test_over_limit_mt_dropped_with_warning(self):
        config = BuildConfig(
            title='Guard Test', course='TEST', num_versions=1,
            shuffle_questions=False, shuffle_answers=False,
            exact_file=MT_OVER_LIMIT,
        )
        versions, warnings = ExamBuilder().build(config)
        self.assertEqual(versions[0].questions, [])
        self.assertTrue(any('mt_over_limit.txt' in w and 'exceeding the 6-option' in w
                             for w in warnings))


class DistributePoints(unittest.TestCase):
    def test_spec_example_one_point_three_slots(self):
        self.assertEqual(_distribute_points(1.0, 3), [0.34, 0.33, 0.33])

    def test_evenly_divisible(self):
        self.assertEqual(_distribute_points(2.0, 2), [1.0, 1.0])

    def test_single_slot(self):
        self.assertEqual(_distribute_points(1.5, 1), [1.5])

    def test_zero_slots(self):
        self.assertEqual(_distribute_points(1.0, 0), [])

    def test_sums_exactly_to_total(self):
        for total, n in [(1.0, 3), (2.0, 7), (0.5, 4), (10.0, 6)]:
            parts = _distribute_points(total, n)
            self.assertAlmostEqual(sum(parts), total, places=2)


class BuildRenderKeyRoundTrip(unittest.TestCase):
    """Full build -> render -> key pipeline on a small exam with one OR and
    one MT question. shuffle_questions/shuffle_answers are both off, so MT's
    lefts/rights stay in source order and only OR's mandatory display
    shuffle introduces randomness -- expected letters for OR are derived
    from the built Question object itself rather than hardcoded, so this
    test doesn't depend on a particular random seed."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix='or_mt_roundtrip_'))
        config = BuildConfig(
            title='OR MT Round Trip', course='TEST', num_versions=1,
            shuffle_questions=False, shuffle_answers=False,
            exact_file=BASIC, default_points=1.0,
        )
        cls.versions, cls.warnings = ExamBuilder().build(config)
        cls.version = cls.versions[0]
        cls.or_q = next(q for q in cls.version.questions if q.q_type == 'OR')
        cls.mt_q = next(q for q in cls.version.questions if q.q_type == 'MT')
        cls.key_data = build_key_data(cls.version, config.default_points)
        cls.html_path = ExamRenderer().to_html(cls.version, cls.tmpdir, 1, config.default_points)
        cls.md_path = ExamRenderer().to_markdown(cls.version, cls.tmpdir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_no_warnings(self):
        self.assertEqual(self.warnings, [])

    def test_or_key_letters_match_built_display_order(self):
        # Q001 = OR's first slot (rank 1), Q002 = rank 2, Q003 = rank 3
        expected = {}
        for i, item in enumerate(self.or_q.order_items):
            expected[item.rank] = chr(ord('A') + i)
        bubbles = self.key_data['bubble_answers']
        self.assertEqual(bubbles['Q001'], expected[1])
        self.assertEqual(bubbles['Q002'], expected[2])
        self.assertEqual(bubbles['Q003'], expected[3])

    def test_or_points_split_evenly(self):
        pts = self.key_data['point_values']
        self.assertEqual([pts['Q001'], pts['Q002'], pts['Q003']], [0.34, 0.33, 0.33])

    def test_mt_key_letters_source_order(self):
        # shuffle_answers=False -> match_rights stays in declaration order:
        # catA is declared before catB in basic.txt, so catA=index 0 ('A'),
        # catB=index 1 ('B'), regardless of which left references which first.
        bubbles = self.key_data['bubble_answers']
        self.assertEqual(bubbles['Q004'], 'B')  # term1 -> catB -> index 1
        self.assertEqual(bubbles['Q005'], 'A')  # term2 -> catA -> index 0
        self.assertEqual(bubbles['Q006'], 'B')  # term3 -> catB -> index 1

    def test_mt_points_split_evenly(self):
        pts = self.key_data['point_values']
        self.assertEqual([pts['Q004'], pts['Q005'], pts['Q006']], [0.34, 0.33, 0.33])

    def test_html_contains_lettered_rows_and_slots(self):
        html = self.html_path.read_text(encoding='utf-8')
        self.assertIn('Questions 1', html)  # OR range header
        self.assertIn('shallow', html)
        self.assertIn('deep', html)
        self.assertIn('(Question 4)', html)  # MT's first slot
        self.assertIn('alpha', html)  # MT right-side text shown in the lettered row
        self.assertIn('first category', html)

    def test_markdown_round_trips_to_equivalent_structure(self):
        reparsed, warnings = parse_file(self.md_path)
        self.assertEqual(warnings, [])
        reparsed_or = next(q for q in reparsed if q.q_type == 'OR')
        reparsed_mt = next(q for q in reparsed if q.q_type == 'MT')

        # OR must round-trip in TRUE RANK order regardless of this version's
        # shuffled display order.
        self.assertEqual(
            sorted((it.rank, it.text) for it in reparsed_or.order_items),
            [(1, 'epidermis'), (2, 'dermis'), (3, 'hypodermis')],
        )
        self.assertEqual(reparsed_or.order_top_label, 'shallow')
        self.assertEqual(reparsed_or.order_bottom_label, 'deep')

        self.assertEqual([l.text for l in reparsed_mt.match_lefts], ['alpha', 'beta', 'gamma'])
        self.assertEqual([l.correct_label for l in reparsed_mt.match_lefts], ['catB', 'catA', 'catB'])
        by_label = {r.label: r.text for r in reparsed_mt.match_rights}
        self.assertEqual(by_label, {'catA': 'first category', 'catB': 'second category'})


class OrItemsAlwaysShuffled(unittest.TestCase):
    """The spec requires OR items to scramble regardless of shuffle_answers,
    since the source lists them in true-answer order."""

    def test_or_display_order_changes_across_many_builds_even_with_shuffle_answers_off(self):
        config = BuildConfig(
            title='Shuffle Check', course='TEST', num_versions=1,
            shuffle_questions=False, shuffle_answers=False,
            exact_file=BASIC, default_points=1.0,
        )
        orders = set()
        random.seed(1)
        for _ in range(20):
            versions, _ = ExamBuilder().build(config)
            or_q = next(q for q in versions[0].questions if q.q_type == 'OR')
            orders.add(tuple(item.rank for item in or_q.order_items))
        # With 3! = 6 possible orderings and 20 draws, seeing more than one
        # distinct order is overwhelmingly likely if shuffling is happening.
        self.assertGreater(len(orders), 1)


if __name__ == '__main__':
    unittest.main()
