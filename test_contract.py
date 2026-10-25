import json
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
import OpenEXR

from media import PASSES, camera_metadata, save_depth, save_png, validate_package
from pipeline import Generator, Settings, TemporalFilter, depth_normals
from supermat_backend import prepare, restore, shot_box, tracked_boxes


class ContractTests(unittest.TestCase):
    def test_supermat_crop_preserves_aspect_and_restores_coordinates(self):
        rgb = np.zeros((32, 64, 3), np.uint8)
        rgb[4:28, 20:36] = [51, 102, 204]
        alpha = np.zeros((32, 64), np.uint8)
        alpha[4:28, 20:36] = 255
        square, layout = prepare(rgb, alpha, (20, 4, 36, 28), size=24)
        self.assertEqual(square.shape, (24, 24, 3))
        np.testing.assert_allclose(square[:, 4:20], np.array([.2,.4,.8])[None,None,:] * np.ones((24,16,1)), atol=1e-6)
        np.testing.assert_allclose(square[:, :4], .5)
        full = restore(square, layout, (20, 4, 36, 28), rgb.shape, 0)
        np.testing.assert_allclose(full[4:28, 20:36], rgb[4:28, 20:36]/255, atol=1e-6)
        np.testing.assert_allclose(full[:, :20], 0)

    def test_supermat_shot_crop_covers_motion_and_empty_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            files=[]
            for index, x in enumerate((2, 90)):
                a=np.zeros((100, 100), np.uint8);a[40:50,x:x+5]=255
                f=Path(temp)/f'{index}.png';Image.fromarray(a).save(f);files.append(f)
            left, top, right, bottom=shot_box(files)
            self.assertLessEqual(left, 2);self.assertGreaterEqual(right, 95)
            self.assertLessEqual(top, 40);self.assertGreaterEqual(bottom, 50)
            tracking=tracked_boxes(files)
            a,b=tracking[files[0].name],tracking[files[1].name]
            self.assertEqual(a[2]-a[0],b[2]-b[0])
            self.assertLess(a[0],b[0])
            self.assertLessEqual(a[0],2);self.assertGreaterEqual(b[2],95)

    def test_uniform_materials_skip_inference_and_neutralize_only_background(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('source', 'alpha', 'basecolor', 'roughness', 'metallic', 'specular'):
                (root / name).mkdir()
            file = root / 'source' / '000000.png'
            rgb = np.full((2, 3, 3), 80, np.uint8)
            Image.fromarray(rgb).save(file)
            Image.fromarray(np.array([[0, 128, 255], [0, 128, 255]], np.uint8)).save(root / 'alpha' / file.name)
            gen = Generator(Settings('unused.mov', temp, roughness=.7, metallic=.2, materials='Uniform values'))
            gen.root = root
            gen.load_marigold = Mock(side_effect=AssertionError('Must not load appearance model'))
            with patch('pipeline.release'):
                gen.make_materials([file])
            with Image.open(root / 'roughness' / file.name) as image:
                np.testing.assert_array_equal(np.asarray(image), [[255, 179, 179], [255, 179, 179]])
            with Image.open(root / 'metallic' / file.name) as image:
                np.testing.assert_array_equal(np.asarray(image), [[0, 51, 51], [0, 51, 51]])
            gen.load_marigold.assert_not_called()

    def test_material_basecolor_choice_preserves_source_without_changing_data_maps(self):
        # A deliberately bad AI estimate must never leak into Source colors.
        rgb = np.array([[[20, 80, 120], [205, 35, 60]],
                        [[0, 0, 0], [110, 140, 90]]], dtype=np.uint8)
        albedo = np.full(rgb.shape, .96, np.float32)
        material = np.full(rgb.shape, .25, np.float32)
        material[..., 1] = .8
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('source', 'alpha', 'basecolor', 'roughness', 'metallic', 'specular'):
                (root / name).mkdir()
            frame = root / 'source' / '000000.png'
            Image.fromarray(rgb).save(frame)
            Image.new('L', (2, 2), 255).save(root / 'alpha' / frame.name)
            gen = Generator(Settings('unused.mov', temp, temporal=0, materials='AI estimates'))
            gen.root = root
            gen.load_marigold = Mock(return_value=Mock(target_properties={'target_names':['albedo','material'], 'material':{'sub_target_names':['roughness','metallicity',None]}}))
            gen.predict = Mock(return_value=np.stack((albedo, material)))
            for mode in ('Source colors', 'AI albedo'):
                gen.s.basecolor = mode
                with patch('pipeline.release'):
                    gen.make_materials([frame])
                with Image.open(root / 'basecolor' / frame.name) as image:
                    expected = rgb if mode == 'Source colors' else np.full(rgb.shape, 245, np.uint8)
                    np.testing.assert_array_equal(np.asarray(image), expected)
                for name in ('roughness', 'metallic'):
                    with Image.open(root / name / frame.name) as image:
                        np.testing.assert_array_equal(np.asarray(image), np.full(rgb.shape[:2], 64 if name == 'roughness' else 204, np.uint8))

    def test_fractional_fps_and_independent_camera_frames(self):
        data = camera_metadata(1920, 1080, Fraction(24000, 1001), 3)
        self.assertAlmostEqual(data['frame_rate'], 23.976023976)
        self.assertEqual(data['fps_denominator'], 1001)
        data['frames'][0]['depth_min'] = 7
        self.assertEqual(data['frames'][1]['depth_min'], 1)

    def test_depth_exr_keeps_half_float_and_all_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'depth.exr'
            expected = np.linspace(0, 1, 12, dtype=np.float32).reshape(3, 4)
            save_depth(path, expected)
            with OpenEXR.File(str(path), separate_channels=True) as image:
                for key in ('R', 'G', 'B'):
                    np.testing.assert_allclose(image.channels()[key].pixels, expected, atol=.001)

    def test_missing_middle_frame_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Camera.json').write_text(json.dumps(camera_metadata(8, 8, Fraction(24), 3)))
            for name in PASSES:
                (root / name).mkdir()
                for i in range(3):
                    if name == 'depth':
                        save_depth(root / name / f'{i:06d}.exr', np.zeros((8, 8)))
                    else:
                        save_png(root / name / f'{i:06d}.png', np.zeros((8, 8)))
            validate_package(root)
            (root / 'normal' / '000001.png').unlink()
            with self.assertRaisesRegex(ValueError, 'normal'):
                validate_package(root)

    def test_flat_depth_normal_faces_camera(self):
        normal = depth_normals(np.ones((16, 16), np.float32))
        np.testing.assert_allclose(normal[..., :2], 0)
        np.testing.assert_allclose(normal[..., 2], 1)

    def test_temporal_cut_does_not_ghost_previous_frame(self):
        filt = TemporalFilter(.8)
        filt(np.zeros((24, 32, 3), np.uint8), np.zeros((24, 32), np.float32))
        result = filt(np.full((24, 32, 3), 255, np.uint8), np.ones((24, 32), np.float32))
        np.testing.assert_allclose(result, 1)


if __name__ == '__main__':
    unittest.main()
