"""Regression checks for the empty AutoImageProcessor lookup seen on a new PC."""
import json
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from depth_backend import ASSETS, load_processor, load_model


class DepthLoadingTests(unittest.TestCase):
    def test_processor_works_with_broken_lookup_and_no_network(self):
        from transformers import AutoImageProcessor, DPTImageProcessor
        image = Image.fromarray(np.random.default_rng(2).integers(0, 256, (48, 96, 3), dtype=np.uint8))
        reference = DPTImageProcessor.from_json_file(str(ASSETS / 'preprocessor_config.json'))
        with patch.object(AutoImageProcessor, 'from_pretrained', side_effect=IndexError('list index out of range')) as lookup, \
             patch('socket.socket.connect', side_effect=AssertionError('Processor must not use network')):
            actual = load_processor()(images=image, return_tensors='np')['pixel_values']
        lookup.assert_not_called()
        np.testing.assert_array_equal(actual, reference(images=image, return_tensors='np')['pixel_values'])

    def test_download_failure_retains_underlying_detail(self):
        from huggingface_hub.errors import LocalEntryNotFoundError
        with patch('huggingface_hub.hf_hub_download', side_effect=[LocalEntryNotFoundError('empty cache'), OSError('TLS connection failed')]) as download:
            with self.assertRaisesRegex(RuntimeError, 'TLS connection failed'):
                load_model('cpu')
        self.assertTrue(download.call_args_list[0].kwargs['local_files_only'])
        self.assertTrue(download.call_args_list[1].kwargs['force_download'])

    def test_bundled_config_and_weights_share_revision(self):
        from depth_backend import REVISION
        upstream = json.loads((ASSETS / 'UPSTREAM.json').read_text())
        self.assertEqual(upstream['revision'], REVISION)


if __name__ == '__main__':
    unittest.main()
