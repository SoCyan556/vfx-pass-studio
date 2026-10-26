"""Disk-backed, shot-aware motion compensation shared by alpha and geometry."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image


def read_rgb(path):
    with Image.open(path) as image:
        return np.asarray(image.convert('RGB'))


class MotionSequence:
    def __init__(self, files, directory, amount):
        self.files = files
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.amount = amount
        self.cuts = {0}
        self._pair_cache = {}

    @staticmethod
    def small(rgb):
        h, w = rgb.shape[:2]
        scale = min(1., 512 / max(h, w))
        return cv2.resize(rgb, (max(8, round(w * scale)), max(8, round(h * scale))))

    @staticmethod
    def grid(shape):
        y, x = np.mgrid[:shape[0], :shape[1]].astype(np.float32)
        return np.stack((x, y), axis=-1)

    @staticmethod
    def sample(value, mapping):
        return cv2.remap(value, mapping[..., 0], mapping[..., 1], cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def build(self, check=lambda: None, progress=lambda i, n: None):
        previous = None
        total = max(1, len(self.files) - 1)
        for i, file in enumerate(self.files):
            check()
            current = cv2.cvtColor(self.small(read_rgb(file)), cv2.COLOR_RGB2GRAY)
            if previous is not None:
                progress(i - 1, total)
                flow = cv2.calcOpticalFlowFarneback(previous, current, None, .5, 4, 25, 4, 7, 1.5, 0)
                back = cv2.calcOpticalFlowFarneback(current, previous, None, .5, 4, 25, 4, 7, 1.5, 0)
                grid = self.grid(current.shape)
                confidence = []
                for src, dst, fwd, reverse in ((previous, current, flow, back), (current, previous, back, flow)):
                    mapping = grid + fwd
                    error = np.abs(src.astype(np.float32) - self.sample(dst, mapping))
                    consistency = np.linalg.norm(fwd + self.sample(reverse, mapping), axis=-1)
                    inside = ((mapping[..., 0] >= 0) & (mapping[..., 0] < src.shape[1]-1)
                              & (mapping[..., 1] >= 0) & (mapping[..., 1] < src.shape[0]-1))
                    weight = np.exp(-(error / 18.)**2 - (consistency / 1.5)**2) * inside
                    confidence.append(weight.astype(np.float32))
                if max(float(np.mean(c > .25)) for c in confidence) < .25:
                    self.cuts.add(i)
                    confidence = [np.zeros_like(c) for c in confidence]
                np.savez_compressed(self.directory / f'{i-1:06d}.npz',
                                    forward=flow.astype(np.float16), backward=back.astype(np.float16),
                                    forward_weight=confidence[0].astype(np.float16),
                                    backward_weight=confidence[1].astype(np.float16))
            previous = current
        progress(total, total)

    def pair(self, index):
        if index not in self._pair_cache:
            with np.load(self.directory / f'{index:06d}.npz') as data:
                self._pair_cache[index] = {k: data[k].astype(np.float32) for k in data.files}
            # A sliding five-frame window needs at most four adjacent pairs.
            if len(self._pair_cache) > 6:
                self._pair_cache.pop(next(iter(self._pair_cache)))
        return self._pair_cache[index]

    def mapping(self, index, neighbor, shape):
        direction = 1 if neighbor > index else -1
        first = self.pair(min(index, index + direction))
        mapping = self.grid(first['forward'].shape)
        confidence = np.ones(mapping.shape[:2], np.float32)
        for position in range(index, neighbor, direction):
            pair = self.pair(min(position, position + direction))
            key = 'forward' if direction > 0 else 'backward'
            confidence *= self.sample(pair[key + '_weight'], mapping)
            mapping += self.sample(pair[key], mapping)
        grid = self.grid(mapping.shape)
        displacement = mapping - grid
        h, w = shape[:2]
        displacement = cv2.resize(displacement, (w, h))
        displacement[..., 0] *= w / grid.shape[1]
        displacement[..., 1] *= h / grid.shape[0]
        return self.grid((h, w)) + displacement, cv2.resize(confidence, (w, h))

    def stabilize(self, index, load, support=None, normals=False, matte=False):
        current = np.asarray(load(index), np.float32)
        if not self.amount or len(self.files) < 2:
            return current
        result = current.copy()
        denominator = np.ones(current.shape[:2], np.float32)
        foreground = support(index) if support else None
        votes = [current] if matte else None
        for neighbor in range(max(0, index-2), min(len(self.files), index+3)):
            if neighbor == index:
                continue
            mapping, confidence = self.mapping(index, neighbor, current.shape)
            warped = self.sample(np.asarray(load(neighbor), np.float32), mapping)
            weight = confidence * self.amount / abs(neighbor-index)
            if support:
                weight *= np.clip(foreground, 0, 1) * np.clip(self.sample(support(neighbor), mapping), 0, 1)
            if normals:
                # A sharp real orientation change must not become a long normal trail.
                weight *= np.clip((np.sum(current * warped, axis=-1)-.5)*2, 0, 1)
            result += warped * (weight[..., None] if current.ndim == 3 else weight)
            denominator += weight
            if matte:
                votes.append(np.where(confidence > .5, warped, current))
        result /= denominator[..., None] if current.ndim == 3 else denominator
        if matte:
            # An isolated segmentation failure should not infect its otherwise stable neighbors.
            consensus = np.median(np.stack(votes), axis=0)
            result = result*(1-self.amount) + consensus*self.amount
        return result

    def align_depth(self, index, current, previous, support):
        """Match affine-ambiguous inverse depth on reliable overlapping foreground."""
        if not self.amount or index in self.cuts:
            return current
        mapping, confidence = self.mapping(index, index-1, current.shape)
        target = self.sample(previous, mapping)
        valid = ((confidence > .7) & (support(index) > .9)
                 & (self.sample(support(index-1), mapping) > .9))
        x, y = current[valid][::4], target[valid][::4]
        if len(x) < 128 or np.std(x) < 1e-5:
            return current
        keep = np.ones(len(x), bool)
        for _ in range(3):
            if np.count_nonzero(keep) < 128:
                return current
            a, b = np.linalg.lstsq(np.stack((x[keep], np.ones(np.count_nonzero(keep))), axis=1), y[keep], rcond=None)[0]
            residual = y - (a*x+b)
            median = np.median(residual)
            keep = np.abs(residual-median) < max(1e-5, 3 * 1.4826 * np.median(np.abs(residual-median)))
        scale = np.clip(a, .75, 1.33)
        span = max(float(np.percentile(y, 95)-np.percentile(y, 5)), 1e-5)
        offset = np.clip(np.median(y-scale*x), -.25*span, .25*span)
        return (current * (1 + (scale-1)*self.amount) + offset*self.amount).astype(np.float32)
