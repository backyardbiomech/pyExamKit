"""
Phase 2 verification: models.py, parser.py, exam_builder.py, renderer.py, and
exam_config.py were copied byte-for-byte from pyExamPaper into this repo, and
exam_key_writer.py replaces key_generator.py, routing key-writing through
keyformat.py instead of writing CSV rows directly.

This test proves the move was clean by rebuilding the exact exam the golden
fixtures in tests/fixtures/build_migration/golden/ were generated from
(pyExamPaper's own, untouched code, run against
tests/fixtures/build_migration/input/bank1.txt) and asserting the newly
copied-in code produces byte-identical HTML, Markdown, and key CSV output.

Phase 3.5 added OR/MT parsing (docs/ordering-matching-spec.md), so bank1.txt's
one OR and one MT block -- previously skipped as unsupported types, counted
among the 7 warnings below -- now parse and appear in the golden output too.
The golden files were regenerated from this repo's own new code rather than
pyExamPaper's (which never supported OR/MT either, so there's no independent
implementation left to diff against for that content); the pre-existing
MC/MA/SA/TF/MD content is unchanged apart from the MD points-distribution fix.
OR items are unconditionally shuffled for display (exam_builder._finalize_or_mt),
so random.seed() is fixed before building to keep this fixture reproducible.
"""
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from exam_builder import BuildConfig, ExamBuilder
from renderer import ExamRenderer, safe_name
import exam_key_writer
import keyformat

_TIMESTAMP_RE = re.compile(r'\(auto-generated \d{4}-\d{2}-\d{2} \d{2}:\d{2}\)')


def _normalize_timestamp(text: str) -> str:
    """renderer.to_markdown() stamps the file with datetime.now() at minute
    granularity, so two separate runs can never be byte-identical there.
    Blank it out before comparing — everything else in the line is static."""
    return _TIMESTAMP_RE.sub('(auto-generated TIMESTAMP)', text)

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'build_migration'
INPUT_BANK = FIXTURE_DIR / 'input' / 'bank1.txt'
GOLDEN_DIR = FIXTURE_DIR / 'golden'


def _build_config() -> BuildConfig:
    return BuildConfig(
        title='Migration Fixture',
        course='TEST101',
        num_versions=1,
        shuffle_questions=False,
        shuffle_answers=False,
        exact_file=INPUT_BANK,
        pools=[],
        version_question=False,
        version_question_position='last',
        default_points=1.0,
        same_questions=False,
    )


class BuildMigrationGoldenFixture(unittest.TestCase):
    """Rebuilds the fixture exam with the copied-in code and diffs the
    output against golden files generated from pyExamPaper's own code."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix='build_migration_test_'))
        config = _build_config()
        builder = ExamBuilder()
        renderer = ExamRenderer()

        random.seed(42)  # OR's display order is shuffled; fix it for a reproducible golden diff
        versions, cls.warnings = builder.build(config)
        assert len(versions) == 1, f'expected 1 version, got {len(versions)}'
        cls.version = versions[0]

        cls.html_path = renderer.to_html(cls.version, cls.tmpdir, len(versions), config.default_points)
        cls.md_path = renderer.to_markdown(cls.version, cls.tmpdir)
        key_name = f"{safe_name(cls.version.title)}_v{cls.version.version_letter}_key.csv"
        cls.key_path = cls.tmpdir / key_name
        exam_key_writer.save_key(cls.version, cls.key_path, config.default_points)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_seven_question_types_survive_parsing(self):
        # MC, MA, SA, MD (2 dropdowns), TF, MT, OR -> 8 bubble/open question slots.
        # ES, MB, CT, and both HS blocks are not supported by parser.py today
        # and are dropped with a warning.
        self.assertEqual(len(self.warnings), 5)

    def test_html_matches_golden(self):
        golden = GOLDEN_DIR / self.html_path.name
        self.assertEqual(self.html_path.read_text(encoding='utf-8'),
                          golden.read_text(encoding='utf-8'))

    def test_markdown_matches_golden(self):
        golden = GOLDEN_DIR / self.md_path.name
        self.assertEqual(_normalize_timestamp(self.md_path.read_text(encoding='utf-8')),
                          _normalize_timestamp(golden.read_text(encoding='utf-8')))

    def test_key_csv_matches_golden(self):
        """Compare loaded key data, not raw text. keyformat.py's writer
        always emits an explicit page number for 'open' rows (defaulting to
        1), where key_generator.py's own writer left that cell blank —
        cosmetic only, since keyformat.py's reader already normalizes a
        blank page cell to 1, so the two forms load back identically. Raw
        text would flag that non-difference; loading both and comparing is
        what actually matters for a key file."""
        golden = GOLDEN_DIR / self.key_path.name
        self.assertEqual(keyformat.load_key_csv(str(self.key_path)),
                          keyformat.load_key_csv(str(golden)))

    def test_copied_images_match_golden(self):
        new_images = sorted(p.name for p in (self.tmpdir / 'images').glob('*'))
        golden_images = sorted(p.name for p in (GOLDEN_DIR / 'images').glob('*'))
        self.assertEqual(new_images, golden_images)
        for name in golden_images:
            self.assertEqual((self.tmpdir / 'images' / name).read_bytes(),
                              (GOLDEN_DIR / 'images' / name).read_bytes())

    def test_md_question_points_bug_fixed(self):
        """Phase 3.5 fix (docs/ordering-matching-spec.md): a 1-point MD
        question with two dropdowns must split the point evenly across its
        two bubble rows (0.5 each), not carry the full point value on both."""
        data = exam_key_writer.build_key_data(self.version, 1.0)
        md_dropdown_points = [
            pts for qk, pts in data['point_values'].items()
            if qk in ('Q004', 'Q005')
        ]
        self.assertEqual(md_dropdown_points, [0.5, 0.5])


if __name__ == '__main__':
    unittest.main()
