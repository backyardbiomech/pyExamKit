"""
Verification for qti_import.py, the Canvas QTI -> question-bank converter.

Two fixtures under tests/fixtures/qti_import/:

  newquiz_export.zip   a real Canvas New Quizzes export whose every question
                       and answer string has been replaced with 'Fabricated
                       text N' and whose images are 1x1 PNGs. The XML
                       structure -- identifiers, metadata, scoring
                       conditions, the $IMS-CC-FILEBASE$ image references --
                       is untouched, so it tests the reader against what
                       Canvas actually emits without putting live quiz items
                       in a public repo. Same convention as
                       tests/fixtures/or_mt/.

  all_types_export.zip qtiConverter's own bank1_export.zip, which carries one
                       question of every type it writes. It is the only
                       available sample of the QTI encodings for SA, MD, MT
                       and OR, and Canvas accepts its imports, so a bank ->
                       QTI -> bank round trip through it is the check that
                       those four readers are right.

Every converted file is also run back through parser.py: the point of the
converter is a file pyExamKit can build an exam from, so producing text the
parser rejects is a failure even when the XML was read correctly.
"""
import tempfile
import unittest
from pathlib import Path

from parser import parse_file
from qti_import import convert_qti_zip, summarize

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'qti_import'
NEWQUIZ = FIXTURE_DIR / 'newquiz_export.zip'
ALL_TYPES = FIXTURE_DIR / 'all_types_export.zip'


class _Converted(unittest.TestCase):
    """Convert a fixture once into a temp folder, then read it back."""
    zip_path: Path

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / 'bank.txt'
        cls.result = convert_qti_zip(cls.zip_path, cls.out)
        cls.questions, cls.parse_warnings = parse_file(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def by_type(self, code):
        return [q for q in self.questions if q.q_type == code]


class NewQuizzesExport(_Converted):
    zip_path = NEWQUIZ

    def test_every_item_converts(self):
        self.assertEqual(self.result.total, 15)
        self.assertEqual(self.result.warnings, [])

    def test_type_counts(self):
        # 3 true/false items land as MC: the bank format renders them as a
        # two-choice question, which is also how the answer sheet grades them.
        self.assertEqual(self.result.counts, {'MC': 9, 'MA': 3, 'TF': 3})
        self.assertEqual(len(self.by_type('MC')), 12)
        self.assertEqual(len(self.by_type('MA')), 3)

    def test_output_parses_clean(self):
        self.assertEqual(self.parse_warnings, [])
        self.assertEqual(len(self.questions), 15)

    def test_every_question_has_exactly_the_marked_answers(self):
        for q in self.by_type('MC'):
            self.assertEqual(sum(a.is_correct for a in q.answers), 1, q.text)
        for q in self.by_type('MA'):
            self.assertGreater(sum(a.is_correct for a in q.answers), 1, q.text)

    def test_true_false_keeps_its_truth_value(self):
        tf = [q for q in self.by_type('MC')
              if [a.text for a in q.answers] == ['True', 'False']]
        self.assertEqual(len(tf), 3)
        # One of the three fixture items is keyed False, the other two True.
        keyed = sorted(next(a.text for a in q.answers if a.is_correct) for q in tf)
        self.assertEqual(keyed, ['False', 'True', 'True'])

    def test_points_carry_over(self):
        self.assertTrue(all(q.points == '1' for q in self.questions))

    def test_images_extracted_and_referenced(self):
        self.assertEqual(len(self.result.images), 2)
        with_images = [q for q in self.questions if q.image_paths]
        self.assertEqual(len(with_images), 2)
        for q in with_images:
            for rel in q.image_paths:
                self.assertTrue((self.out.parent / rel).exists(), rel)

    def test_image_folder_is_named_after_the_bank_file(self):
        self.assertTrue(all(rel.startswith('bank_images/') for rel in self.result.images))

    def test_odd_filenames_survive(self):
        # Canvas keeps '+' as a literal character in uploaded filenames, and
        # .jfif is a JPEG the browser still renders; neither may be mangled.
        names = sorted(Path(rel).name for rel in self.result.images)
        self.assertEqual(names, ['sample+image+one.jfif', 'sample+image+two.jpg'])

    def test_summary_line(self):
        self.assertEqual(summarize(self.result), '15 questions (3 MA, 9 MC, 3 TF)')


class AllQuestionTypes(_Converted):
    zip_path = ALL_TYPES

    def test_supported_types_all_convert(self):
        self.assertEqual(self.result.counts,
                         {'MC': 1, 'MA': 1, 'SA': 1, 'MD': 1, 'MT': 1, 'OR': 1, 'TF': 1})

    def test_unsupported_types_are_named_not_silently_dropped(self):
        text = ' '.join(self.result.warnings)
        for expected in ('essay', 'fill-in-multiple-blanks', 'categorization', 'hot spot'):
            self.assertIn(expected, text)
        self.assertEqual(len(self.result.warnings), 5)   # 1 ES, 1 MB, 1 CT, 2 HS

    def test_output_parses_clean(self):
        self.assertEqual(self.parse_warnings, [])
        self.assertEqual(len(self.questions), 7)

    def test_multiple_answer_keeps_both_correct_choices(self):
        q = self.by_type('MA')[0]
        self.assertEqual([a.is_correct for a in q.answers], [False, True, True, False])

    def test_short_answer_accepts_every_listed_string(self):
        q = self.by_type('SA')[0]
        self.assertEqual([a.text for a in q.answers], ['correct text', 'corect tect'])
        self.assertTrue(all(a.is_correct for a in q.answers))

    def test_dropdown_blanks_line_up_with_the_stem(self):
        q = self.by_type('MD')[0]
        self.assertEqual([d.name for d in q.dropdowns], ['drop1', 'drop2'])
        for drop in q.dropdowns:
            self.assertEqual(sum(a.is_correct for a in drop.answers), 1, drop.name)
        for name in ('drop1', 'drop2'):
            self.assertIn(f'[{name}]', q.text)

    def test_matching_pairs_survive_the_round_trip(self):
        q = self.by_type('MT')[0]
        rights = {r.label: r.text for r in q.match_rights}
        pairs = [(left.text, rights[left.correct_label]) for left in q.match_lefts]
        self.assertEqual(pairs, [
            ('first left option', 'second right option correct for first and second left'),
            ('second left option', 'second right option correct for first and second left'),
            ('third left option', 'first right option correct for third left'),
        ])
        self.assertEqual(len(q.match_rights), 5)   # two distractors kept

    def test_matching_labels_are_renumbered_to_word_characters(self):
        # Canvas identifies right-hand options with hyphenated UUIDs, which
        # the bank format's \w+ labels reject.
        q = self.by_type('MT')[0]
        for right in q.match_rights:
            self.assertRegex(right.label, r'^\w+$')

    def test_ordering_keeps_sequence_and_labels(self):
        q = self.by_type('OR')[0]
        self.assertEqual([(i.rank, i.text) for i in q.order_items],
                         [(1, 'epidermis'), (2, 'dermis'), (3, 'hypodermis')])
        self.assertEqual(q.order_top_label, 'most superficial')
        self.assertEqual(q.order_bottom_label, 'deepest')


class Failures(unittest.TestCase):
    def test_zip_without_an_assessment_is_reported(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'not_qti.zip'
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('notes.txt', 'nothing here')
            with self.assertRaises(ValueError) as caught:
                convert_qti_zip(bad, Path(tmp) / 'out.txt')
            self.assertIn('No QTI assessment', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
