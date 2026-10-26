import tempfile
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from temporal import MotionSequence


class TemporalTests(unittest.TestCase):
    def sequence(self, directory, images, amount=.6):
        files = []
        for i, rgb in enumerate(images):
            path = Path(directory) / f'{i}.png'
            Image.fromarray(rgb).save(path)
            files.append(path)
        motion = MotionSequence(files, Path(directory) / 'motion', amount)
        motion.build()
        return motion

    def test_isolated_mask_dropout_is_reduced_without_network_or_models(self):
        rgb = np.random.default_rng(8).integers(32, 224, (64, 96, 3), dtype=np.uint8)
        values = [np.ones((64, 96), np.float32) for _ in range(7)]
        values[3][16:48, 24:72] = 0
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, [rgb]*7)
            result = [motion.stabilize(i, lambda n: values[n], matte=True) for i in range(7)]
        before = np.stack(values)[:, 20:44, 28:68]
        after = np.stack(result)[:, 20:44, 28:68]
        self.assertLess(np.mean(np.abs(np.diff(after, axis=0))), .3*np.mean(np.abs(np.diff(before, axis=0))))
        self.assertGreater(float(np.mean(after[3])), .8)

    def test_cut_does_not_leak_masks_or_depth_between_shots(self):
        dark = np.zeros((64, 96, 3), np.uint8)
        bright = np.full_like(dark, 255)
        values = [np.zeros((64, 96), np.float32), np.ones((64, 96), np.float32)]
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, [dark, bright])
            self.assertIn(1, motion.cuts)
            for i in range(2):
                np.testing.assert_allclose(motion.stabilize(i, lambda n: values[n], matte=True), values[i])
            np.testing.assert_array_equal(motion.align_depth(1, values[1], values[0], lambda n: np.ones((64,96))), values[1])

    def test_depth_alignment_reduces_affine_model_drift(self):
        rgb = np.random.default_rng(10).integers(32, 224, (64, 96, 3), dtype=np.uint8)
        first = np.tile(np.linspace(.2, 1., 96, dtype=np.float32), (64, 1))
        drifted = first*1.25+.05
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, [rgb, rgb], .8)
            result = motion.align_depth(1, drifted, first, lambda n: np.ones((64,96), np.float32))
        self.assertLess(float(np.mean(np.abs(result-first))), .3*float(np.mean(np.abs(drifted-first))))

    def test_zero_strength_and_single_frame_preserve_inputs(self):
        rgb = np.zeros((32, 32, 3), np.uint8)
        value = np.random.default_rng(3).random((32, 32)).astype(np.float32)
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, [rgb], .6)
            np.testing.assert_array_equal(motion.stabilize(0, lambda n: value, matte=True), value)
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, [rgb, rgb], 0.)
            np.testing.assert_array_equal(motion.stabilize(1, lambda n: value, matte=True), value)

    def test_motion_mapping_follows_translation(self):
        import cv2
        rng = np.random.default_rng(19)
        rgb = rng.integers(0, 256, (96, 128, 3), dtype=np.uint8)
        rgb = cv2.GaussianBlur(rgb, (5,5), 0)
        images = [cv2.warpAffine(rgb, np.float32([[1,0,3*i],[0,1,0]]), (128,96)) for i in range(3)]
        with tempfile.TemporaryDirectory() as temp:
            motion = self.sequence(temp, images)
            mapping, confidence = motion.mapping(0, 2, (96,128))
        x = np.mgrid[:96,:128][1]
        self.assertAlmostEqual(float(np.median((mapping[...,0]-x)[16:-16,16:-16])), 6., delta=.5)
        self.assertGreater(float(np.mean(confidence[16:-16,16:-16])), .5)


if __name__ == '__main__':
    unittest.main()
