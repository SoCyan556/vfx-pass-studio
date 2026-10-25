"""Release boundary and desktop icon checks; no model downloads."""
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from build_distribution import ROOT, source_files
from media import binary

class PackagingTests(unittest.TestCase):
    def test_public_source_excludes_private_runtime(self):
        files = source_files()
        self.assertEqual(len(files), len(set(files)))
        for path in files:
            self.assertTrue(path.is_file(), path)
            parts = path.relative_to(ROOT).parts
            self.assertNotIn(parts[0], {'models', 'outputs', 'cache', 'research', '.venv', 'test-artifacts', 'build', 'runtime'})
            self.assertNotIn(path.name, {'app_settings.json', 'fangs.png'})
        self.assertIn(ROOT / 'LICENSE', files)
        self.assertIn(ROOT / 'ui/assets/vfx-pass-studio.ico', files)
        self.assertIn(ROOT / 'vendor/supermat/LICENSE', files)

    def test_multisize_icon_has_alpha(self):
        with Image.open(ROOT / 'ui/assets/vfx-pass-studio.ico') as icon:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes())
            self.assertEqual(icon.convert('RGBA').getextrema()[3], (0, 255))

    def test_private_ffmpeg_precedes_system_path(self):
        executable = ROOT / 'tools/ffmpeg/bin/ffmpeg.exe'
        with patch.object(Path, 'is_file', lambda p: p == executable), patch('shutil.which', return_value='system-ffmpeg'):
            self.assertEqual(binary('ffmpeg'), str(executable))

if __name__ == '__main__':
    unittest.main()
