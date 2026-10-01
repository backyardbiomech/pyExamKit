"""
Hardening around the AI-OCR boundary: the API key file's permissions, and
what happens when the model's JSON doesn't match the shape the caller
assumes. openQ indexes transcriptions by student row via int(label), so an
invented or malformed label used to raise partway through building the
review window -- after the API call had already been paid for.

No network calls here: _clean_response is pure and is tested directly, and
recognize_batch runs against a fake client.
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

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


class ModelChoice(unittest.TestCase):
    '''The model menu's choice is saved in the config file, and the request
    is shaped for the model it goes to. A fake client stands in for the API.'''

    def setUp(self):
        self.path = Path(tempfile.mkdtemp(prefix='ai_ocr_cfg_')) / '.pyexamkit_config.json'
        patcher = mock.patch.object(ai_ocr, 'CONFIG_PATH', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.requests = []

    def _run(self, *content, stop_reason='end_turn', model=''):
        requests = self.requests

        class Messages:
            def create(self, **kwargs):
                requests.append(kwargs)
                return SimpleNamespace(stop_reason=stop_reason, content=list(content))

        fake = SimpleNamespace(Anthropic=lambda api_key: SimpleNamespace(messages=Messages()))
        crops = [np.zeros((8, 8, 3), np.uint8)] * 2
        with mock.patch.dict(sys.modules, {'anthropic': fake}):
            return ai_ocr.recognize_batch(crops, ['1', '2'], api_key='sk-ant-FAKE', model=model)

    def test_default_is_haiku(self):
        self.assertEqual(ai_ocr.current_model(), 'claude-haiku-4-5')

    def test_saved_choice_is_used(self):
        ai_ocr.save_config({'ai_model': 'claude-sonnet-5-5'})
        self.assertEqual(ai_ocr.current_model(), 'claude-sonnet-5-5')
        self._run(SimpleNamespace(type='text', text='{}'))
        self.assertEqual(self.requests[0]['model'], 'claude-sonnet-5-5')

    def test_a_model_no_longer_offered_falls_back(self):
        ai_ocr.save_config({'ai_model': 'claude-haiku-4-5-20251001'})
        self.assertEqual(ai_ocr.current_model(), ai_ocr.DEFAULT_MODEL)

    def test_every_menu_label_maps_back_to_its_model(self):
        for label in ai_ocr.MODEL_LABELS:
            self.assertEqual(ai_ocr.model_label(ai_ocr.MODEL_IDS[label]), label)

    def test_sonnet_gets_effort_and_room_to_think(self):
        self._run(SimpleNamespace(type='text', text='{}'), model='claude-sonnet-5-5')
        req = self.requests[0]
        self.assertEqual(req['output_config'], {'effort': 'low'})
        self.assertGreaterEqual(req['max_tokens'], 8000)

    def test_haiku_gets_no_effort(self):
        """Haiku 4.5 rejects an effort setting."""
        self._run(SimpleNamespace(type='text', text='{}'), model='claude-haiku-4-5')
        self.assertNotIn('output_config', self.requests[0])

    def test_reply_read_past_a_leading_thinking_block(self):
        out = self._run(SimpleNamespace(type='thinking', thinking=''),
                        SimpleNamespace(type='text', text='{"1": "aorta", "2": "vena cava"}'),
                        model='claude-sonnet-5-5')
        self.assertEqual(out, {'1': 'aorta', '2': 'vena cava'})

    def test_refusal_leaves_the_batch_blank(self):
        out = self._run(SimpleNamespace(type='text', text='{"1": "x"}'), stop_reason='refusal')
        self.assertEqual(out, {})

    def test_truncated_reply_leaves_the_batch_blank(self):
        out = self._run(SimpleNamespace(type='text', text='{"1": "aor'), stop_reason='max_tokens')
        self.assertEqual(out, {})


class CacheNamesItsModel(unittest.TestCase):
    def test_saved_progress_records_the_model(self):
        q = object.__new__(openQ.OpenQs)
        out = Path(tempfile.mkdtemp(prefix='openq_cache_'))
        q.__dict__.update(_output_csv_path=str(out / 'app_data' / 'results.csv'),
                          openQcoords={'openQ_1': (0, 0, 1, 1)}, _ai_texts={},
                          openQkeytext={}, _ai_model='claude-sonnet-5-5')
        q._save_progress_cache()
        self.assertEqual(q._load_progress_cache()['ai_model'], 'claude-sonnet-5-5')


if __name__ == '__main__':
    unittest.main()
