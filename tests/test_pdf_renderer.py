"""
PDF exam layout (docs/dev/pdf-output-plan.md).

A PDF's bytes change with every PyMuPDF release, so nothing here compares
against a golden file. These tests read the finished PDF back and check what
the layout promises: no question starts on one page and finishes on another,
every image prints directly above the stem of its own question, a larger font
size never makes a shorter exam, and each page's footer counts the pages.
"""
import copy
import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
from PIL import Image

import renderer
from exam_builder import FONT_SIZES, BuildConfig, ExamBuilder
from models import Answer, ExamVersion, Question
from parser import parse_file
from renderer import ExamRenderer

FIXTURE_INPUT = Path(__file__).parent / 'fixtures' / 'build_migration' / 'input'
QUESTION_START = re.compile(r'^(\d+\.|Questions \d+)')


def _fixture_version() -> ExamVersion:
    config = BuildConfig(title='Layout Fixture', course='TEST101', num_versions=1,
                         shuffle_questions=False, shuffle_answers=False,
                         exact_file=FIXTURE_INPUT / 'bank1.txt')
    random.seed(42)  # OR and MT display order is always shuffled
    versions, _ = ExamBuilder().build(config)
    return versions[0]


def _stress_version() -> ExamVersion:
    """Sixty questions cycling through the fixture's types, with the tall
    organs.jpg figure on every fifth, so page breaks fall in every position
    relative to an image."""
    base = _fixture_version()
    questions = []
    for i in range(60):
        question = copy.deepcopy(base.questions[i % len(base.questions)])
        if i % 5 == 3:
            question.image_paths = ['organs.jpg']
        questions.append(question)
    return ExamVersion(title='Stress', course='TEST101', version_num=1,
                       questions=questions, source_folder=FIXTURE_INPUT)


def _mc(text: str, image_paths=(), folder: Path = FIXTURE_INPUT) -> Question:
    return Question(q_type='MC', text=text, image_paths=list(image_paths), source_folder=folder,
                    answers=[Answer('yes', True), Answer('no', False)])


def _exam(questions: list[Question]) -> ExamVersion:
    return ExamVersion(title='Edge', course='TEST101', version_num=1, questions=questions,
                       source_folder=FIXTURE_INPUT)


def _body_lines(page: fitz.Page) -> list[str]:
    """Text lines on the page above the footer."""
    clip = fitz.Rect(0, 0, page.rect.width, renderer.CONTENT_BOTTOM)
    return [line for line in page.get_text(clip=clip).splitlines() if line.strip()]


def _lines_below_images(page: fitz.Page) -> list[str]:
    """For each image on the page, the first line of text printed under it.

    When the image is the last thing in the body, that line is the footer,
    which is what makes a stranded image fail a check against QUESTION_START.
    """
    blocks = [b for b in page.get_text('dict')['blocks'] if b['type'] == 0]
    found = []
    for info in page.get_image_info():
        image_bottom = info['bbox'][3]
        below = sorted((b for b in blocks if b['bbox'][1] >= image_bottom - 1),
                       key=lambda b: b['bbox'][1])
        found.append(''.join(span['text'] for span in below[0]['lines'][0]['spans'])
                     if below else '')
    return found


class LayoutAtEverySize(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix='pdf_layout_test_'))
        cls.docs = {}
        cls.image_counts = {}
        for name, version in (('fixture', _fixture_version()), ('stress', _stress_version())):
            cls.image_counts[name] = sum(len(q.image_paths) for q in version.questions)
            for size in FONT_SIZES:
                path, _ = ExamRenderer().to_pdf(version, cls.tmpdir / f'{name}_{size}', 1, 1.0, size)
                cls.docs[name, size] = fitz.open(path)

    @classmethod
    def tearDownClass(cls):
        for doc in cls.docs.values():
            doc.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_no_page_begins_partway_through_a_question(self):
        for (name, size), doc in self.docs.items():
            for page in doc.pages(1):
                with self.subTest(exam=name, size=size, page=page.number + 1):
                    self.assertRegex(_body_lines(page)[0], QUESTION_START)

    def test_every_image_prints_directly_above_its_question(self):
        for (name, size), doc in self.docs.items():
            for page in doc:
                for line in _lines_below_images(page):
                    with self.subTest(exam=name, size=size, page=page.number + 1):
                        self.assertRegex(line, QUESTION_START)

    def test_every_image_is_printed(self):
        """Guards the check above, which would pass vacuously on a PDF with no images."""
        for (name, size), doc in self.docs.items():
            with self.subTest(exam=name, size=size):
                self.assertEqual(sum(len(page.get_image_info()) for page in doc),
                                 self.image_counts[name])

    def test_larger_font_sizes_never_shorten_the_exam(self):
        for name in ('fixture', 'stress'):
            counts = [self.docs[name, size].page_count for size in FONT_SIZES]
            self.assertEqual(counts, sorted(counts), name)
        self.assertGreater(self.docs['stress', 'larger'].page_count,
                           self.docs['stress', 'smaller'].page_count)

    def test_footer_counts_pages(self):
        doc = self.docs['stress', 'medium']
        for page in doc:
            self.assertIn(f'Page {page.number + 1} of {doc.page_count}', page.get_text())

    def test_footer_leaves_out_version_for_a_single_version(self):
        for page in self.docs['fixture', 'medium']:
            self.assertNotIn('Version A', page.get_text())

    def test_blanks_print_as_underscores(self):
        self.assertIn(f'blank {renderer.BLANK}.', self.docs['fixture', 'medium'][0].get_text())


class LayoutEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='pdf_edge_test_'))
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _render(self, version: ExamVersion, **kwargs) -> tuple[fitz.Document, list[str]]:
        path, warnings = ExamRenderer().to_pdf(version, self.tmpdir / 'out', **kwargs)
        doc = fitz.open(path)
        self.addCleanup(doc.close)
        return doc, warnings

    def test_footer_names_the_version_when_several_are_built(self):
        doc, _ = self._render(_exam([_mc('one')]), total_versions=2)
        self.assertIn('Version A · Page 1 of 1', doc[0].get_text())

    def test_math_prints_as_typed_and_is_named_in_a_warning(self):
        bank = self.tmpdir / 'math.txt'
        bank.write_text('MC\n1. If $a<b$ and $$c > d$$, which holds?\n*A. $a<d$\nB. neither\n',
                        encoding='utf-8')
        questions, _ = parse_file(bank)
        for question in questions:
            question.source_folder = self.tmpdir
        doc, warnings = self._render(_exam(questions))
        text = doc[0].get_text()
        self.assertIn('$a<b$', text)
        self.assertIn('$a<d$', text)
        self.assertEqual(len(warnings), 1)
        self.assertIn('math', warnings[0])

    def test_unreadable_image_is_named_and_the_question_still_prints(self):
        doc, warnings = self._render(_exam([_mc('where is it', ['nope.png'])]))
        self.assertIn('where is it', doc[0].get_text())
        self.assertEqual(doc[0].get_image_info(), [])
        self.assertTrue(any('nope.png' in w for w in warnings), warnings)

    def test_images_resolve_from_each_questions_own_folder(self):
        """Pools can come from different folders, and an image path can
        name a subfolder and contain spaces."""
        pool_a = self.tmpdir / 'pool A'
        (pool_a / 'figs').mkdir(parents=True)
        pool_b = self.tmpdir / 'poolB'
        pool_b.mkdir()
        shutil.copy(FIXTURE_INPUT / 'testImage.png', pool_a / 'figs' / 'my figure.png')
        shutil.copy(FIXTURE_INPUT / 'organs.jpg', pool_b / 'organs.jpg')
        version = _exam([_mc('from pool A', ['figs/my figure.png'], pool_a),
                         _mc('from pool B', ['organs.jpg'], pool_b)])
        doc, warnings = self._render(version)
        self.assertEqual(warnings, [])
        self.assertEqual(sum(len(page.get_image_info()) for page in doc), 2)

    def test_image_too_tall_for_any_page_shrinks_to_stay_with_its_question(self):
        Image.new('RGB', (600, 3000), 'gray').save(self.tmpdir / 'tall.png')
        version = _exam([_mc('first'), _mc('the tall one', ['tall.png'], self.tmpdir)])
        # Lift the usual height cap so the image really is taller than a page.
        with mock.patch.object(renderer, 'QUESTION_IMAGE_MAX_HEIGHT', 10_000):
            doc, warnings = self._render(version)
        self.assertEqual(warnings, [])
        self.assertEqual(doc.page_count, 2)
        [line] = _lines_below_images(doc[1])
        self.assertTrue(line.startswith('2.'), line)

    def test_question_taller_than_a_page_without_images_runs_on_and_warns(self):
        doc, warnings = self._render(_exam([_mc('word ' * 2500)]))
        self.assertGreaterEqual(doc.page_count, 2)
        self.assertTrue(any('taller than a page' in w for w in warnings), warnings)

    def test_sizes_other_than_medium_are_named_in_the_filename(self):
        version = _exam([_mc('one')])
        medium, _ = ExamRenderer().to_pdf(version, self.tmpdir)
        large, _ = ExamRenderer().to_pdf(version, self.tmpdir, font_size='large')
        self.assertEqual((medium.name, large.name), ('Edge_vA.pdf', 'Edge_vA_large.pdf'))

    def test_unknown_font_size_is_rejected(self):
        with self.assertRaises(ValueError):
            ExamRenderer().to_pdf(_exam([_mc('x')]), self.tmpdir, font_size='huge')


if __name__ == '__main__':
    unittest.main()
