"""
Hardening around the AI-OCR boundary: the API key file's permissions, and
what happens when the model's JSON doesn't match the shape the caller
assumes. openQ indexes transcriptions by student row via int(label), so an
invented or malformed label used to raise partway through building the
review window -- after the API call had already been paid for.

No network calls here; _clean_response is pure and is tested directly.
"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ai_ocr
import openQ

SENT = ['0', '1', '2']


class CleanResponse(unittest.TestCase):
    def test_well_formed_response_passes_through(self):
        payload = {'0': 'key text', '1': 'aorta', '2': 'vena cava'}
        self.assertEqual(ai_ocr._clean_response(payload, SENT), payload)

    def test_labels_never_sent_are_dropped(self):
        out = ai_ocr._clean_response({'0': 'a', 'student_1': 'b', '2': 'c'}, SENT)
        self.assertEqual(out, {'0': 'a', '2': 'c'})

    def test_non_mapping_response_yields_nothing(self):
        self.assertEqual(ai_ocr._clean_response(['a', 'b'], SENT), {})
        self.assertEqual(ai_ocr._clean_response('a string', SENT), {})

    def test_numbers_are_kept_as_text(self):
        """A numeric answer is legitimate on a physiology exam."""
        self.assertEqual(ai_ocr._clean_response({'0': 42, '1': 3.5}, SENT),
                         {'0': '42', '1': '3.5'})

    def test_structured_values_are_dropped_not_stringified(self):
        """Showing a stringified dict as the transcription is worse than a
        blank field the grader fills in."""
        out = ai_ocr._clean_response({'0': {'text': 'a'}, '1': ['b'], '2': 'c'}, SENT)
        self.assertEqual(out, {'2': 'c'})

    def test_every_surviving_label_is_int_convertible(self):
        """The contract openQ depends on."""
        out = ai_ocr._clean_response({'0': 'a', 'nonsense': 'b', ' 1 ': 'c'}, SENT)
        for label in out:
            int(label)  # must not raise


class ByStudentIndex(unittest.TestCase):
    def test_numeric_labels_become_integer_rows(self):
        self.assertEqual(openQ._by_student_index({'1': 'ok', '3': 'fine'}),
                         {1: 'ok', 3: 'fine'})

    def test_corrupted_cache_entries_are_skipped_not_raised(self):
        self.assertEqual(openQ._by_student_index({'1': 'ok', 'bogus': 'x', None: 'y'}),
                         {1: 'ok'})

    def test_empty_map_is_fine(self):
        self.assertEqual(openQ._by_student_index({}), {})


@unittest.skipUnless(os.name == 'posix', 'file modes are meaningless on Windows')
class ApiKeyFilePermissions(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp(prefix='ai_ocr_cfg_')) / '.pyexamkit_config.json'
        patcher = mock.patch.object(ai_ocr, 'CONFIG_PATH', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _mode(self) -> int:
        return stat.S_IMODE(self.path.stat().st_mode)

    def test_new_file_is_owner_only(self):
        ai_ocr.save_config({'anthropic_api_key': 'sk-ant-FAKE'})
        self.assertEqual(self._mode(), 0o600)

    def test_pre_existing_loose_file_is_narrowed(self):
        """A config written by an older version of the app kept its 0644 mode,
        because O_CREAT's mode only applies when the file is new."""
        self.path.write_text('{}')
        self.path.chmod(0o644)
        ai_ocr.save_config({'anthropic_api_key': 'sk-ant-FAKE'})
        self.assertEqual(self._mode(), 0o600)

    def test_save_merges_rather_than_replacing(self):
        ai_ocr.save_config({'anthropic_api_key': 'sk-ant-FAKE'})
        ai_ocr.save_config({'ai_context': 'Biology exam.'})
        self.assertEqual(json.loads(self.path.read_text()),
                         {'anthropic_api_key': 'sk-ant-FAKE', 'ai_context': 'Biology exam.'})


if __name__ == '__main__':
    unittest.main()
