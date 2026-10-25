"""Local inference. No Beeble code, service, or model is used."""
from __future__ import annotations

import gc
import json
import os
import re
import shutil
import threading
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('HF_HOME', str(ROOT / 'models' / 'huggingface'))
os.environ.setdefault('U2NET_HOME', str(ROOT / 'models' / 'matting'))
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

import cv2
import numpy as np
from PIL import Image
from media import PASSES, Cancelled, camera_metadata, extract, probe, save_depth, save_png, validate_package


@dataclass
class Settings:
    video: str
    output: str
    max_size: int = 1080
    fps: str = ''
    max_frames: int = 0
    alpha: str = 'Anime subject'
    mask_video: str = ''
    quality: str = 'AI materials + normals'
    basecolor: str = 'Source colors'
    materials: str = 'SuperMat estimates'
    steps: int = 4
    processing_size: int = 512
    temporal: float = .2
    roughness: float = .65
    specular: float = .5
    metallic: float = 0.
    normal_strength: float = 2.
    zip_output: bool = True


def resize(array, shape):
    return cv2.resize(array, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


class TemporalFilter:
    """Warp the previous estimate onto the current frame; reject cuts and occlusions."""
    def __init__(self, amount):
        self.amount = amount
        self.gray = None
        self.value = None

    def __call__(self, rgb, value):
        small = cv2.resize(rgb, (min(384, rgb.shape[1]), max(2, round(rgb.shape[0] * min(384, rgb.shape[1]) / rgb.shape[1]))))
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        if self.gray is None or self.amount == 0:
            result = value
        else:
            backward = cv2.calcOpticalFlowFarneback(gray, self.gray, None, .5, 3, 15, 3, 5, 1.2, 0)
            forward = cv2.calcOpticalFlowFarneback(self.gray, gray, None, .5, 3, 15, 3, 5, 1.2, 0)
            h, w = gray.shape
            yy, xx = np.mgrid[:h, :w].astype(np.float32)
            maps = (xx + backward[..., 0], yy + backward[..., 1])
            warped_gray = cv2.remap(self.gray, *maps, cv2.INTER_LINEAR)
            warped_forward = cv2.remap(forward, *maps, cv2.INTER_LINEAR)
            valid = ((np.abs(gray.astype(float) - warped_gray) < 20)
                     & (np.linalg.norm(backward + warped_forward, axis=2) < 1.5)
                     & (maps[0] >= 0) & (maps[0] < w - 1) & (maps[1] >= 0) & (maps[1] < h - 1))
            if np.mean(valid) < .25:
                result = value  # A cut or a large disocclusion: never carry the previous frame across it.
            else:
                vh, vw = value.shape[:2]
                full = resize(backward, value.shape)
                full[..., 0] *= vw / w
                full[..., 1] *= vh / h
                fy, fx = np.mgrid[:vh, :vw].astype(np.float32)
                previous = cv2.remap(self.value, fx + full[..., 0], fy + full[..., 1], cv2.INTER_LINEAR)
                weight = resize(valid.astype(np.float32), value.shape) * self.amount
                if value.ndim == 3:
                    weight = weight[..., None]
                result = value * (1 - weight) + previous * weight
        self.gray, self.value = gray, np.asarray(result, np.float32)
        return self.value


def depth_normals(depth, strength=2.):
    smooth = cv2.GaussianBlur(depth.astype(np.float32), (0, 0), 1.5)
    dy, dx = np.gradient(smooth)
    # X right, Y up, Z toward viewer. Scale gradients independently of output resolution.
    normals = np.stack((-dx * depth.shape[1] * strength,
                         dy * depth.shape[0] * strength, np.ones_like(depth)), axis=-1)
    return normals / np.maximum(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-6)


def release():
    gc.collect()
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class Generator:
    def __init__(self, settings: Settings, notify=None, cancel=None):
        self.s = settings
        self.notify = notify or (lambda event: print(json.dumps(event), flush=True))
        self.cancel = cancel or threading.Event()
        self.root = None
        self._progress = 0.
        self._phases = ['Decode', 'Alpha', 'Depth', 'Depth export']
        self._phases += ['Normals', 'Materials'] if settings.quality == 'AI materials + normals' else ['Materials']
        self._phases += ['Export']

    def event(self, message, phase='', current=0, total=0, preview=None):
        self.check()
        canonical = {'SuperMat materials': 'Materials', 'Draft materials': 'Materials'}.get(phase, phase)
        if phase == 'Complete':
            self._progress = 1.
        elif canonical in self._phases:
            fraction = min(1., max(0., current / total)) if total else 0.
            self._progress = max(self._progress, (self._phases.index(canonical) + fraction) / len(self._phases))
        self.notify(dict(message=message, phase=phase, current=current, total=total, preview=preview,
                         progress=self._progress, indeterminate=not total and phase != 'Complete'))

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def each(self, phase, files):
        for index, file in enumerate(files):
            self.event(f'{phase} · frame {index + 1} / {len(files)}', phase, index, len(files))
            with Image.open(file) as image:
                rgb = np.asarray(image.convert('RGB'))
            yield index, file, rgb
        self.event(f'{phase} · {len(files)} frames complete', phase, len(files), len(files))

    def run(self) -> Path:
        s = self.s
        source = Path(s.video).expanduser().resolve()
        if source.suffix.lower() not in ('.mp4', '.mov', '.mkv', '.m4v', '.avi', '.webm') or not source.is_file():
            raise ValueError('Choose an existing MP4, MOV, or other supported video.')
        if not (1 <= s.steps <= 50 and 128 <= s.processing_size <= 1024 and 0 <= s.temporal <= .8):
            raise ValueError('Invalid inference settings.')
        if s.basecolor not in ('Source colors', 'AI albedo'):
            raise ValueError('Choose Source colors or AI albedo for base color.')
        if s.materials not in ('Uniform values', 'AI estimates', 'SuperMat estimates'):
            raise ValueError('Choose a supported material backend.')
        if not all(0 <= value <= 1 for value in (s.roughness, s.metallic, s.specular)):
            raise ValueError('Material values must be between 0 and 1.')
        import torch
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if s.quality == 'AI materials + normals' and self.device != 'cuda':
            raise RuntimeError('AI materials mode requires an NVIDIA GPU. Select Fast draft for CPU processing.')
        self.event(f'Using {torch.cuda.get_device_name(0) if self.device == "cuda" else "CPU"}.')
        info = probe(source)
        fps = Fraction(s.fps or info['fps']).limit_denominator(100000)
        if not (0 < float(fps) <= 240):
            raise ValueError('FPS must be between 0 and 240.')
        stem = re.sub(r'[^\w .-]', '_', source.stem)[:72]
        target = Path(s.output).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        self.root = target / f'{stem}_{datetime.now():%Y%m%d_%H%M%S_%f}.beeble'
        self.root.mkdir()
        work = self.root / '_work'
        work.mkdir()
        for name in PASSES:
            (self.root / name).mkdir()
        status = self.root / 'INCOMPLETE.txt'
        status.write_text('Processing is not complete. Do not import this folder yet.', encoding='utf-8')
        try:
            files = extract(source, self.root / 'source', info, s.max_size, fps, s.max_frames,
                            self.cancel, lambda t: self.event(t, 'Decode'))
            with Image.open(files[0]) as first:
                width, height = first.size
            self.make_alpha(files, info, work, fps)
            self.make_depth(files, work)
            if s.quality == 'AI materials + normals':
                self.make_normals(files)
                self.make_materials(files)
            else:
                self.make_draft(files)
            self.event('Writing Blender metadata and validating every pass …', 'Export')
            metadata = camera_metadata(width, height, fps, len(files))
            (self.root / 'Camera.json').write_text(json.dumps(metadata), encoding='utf-8')
            provenance = dict(application='VFX Pass Studio', version='0.1.0', settings=asdict(s),
                source_info=info, output_fps=str(fps), frames=len(files),
                normal_convention='camera/screen space: X right, Y up, Z toward viewer, RGB = N * .5 + .5',
                depth_convention='relative depth normalized over shot: 0 near, 1 far; synthetic 1.0–1.4 scale',
                camera='Static synthetic camera; no recovered camera tracking or hidden/backside geometry.',
                basecolor=('Source RGB in sRGB; retains baked lighting.' if s.basecolor == 'Source colors'
                           or s.quality == 'Fast draft' else 'AI estimated albedo in sRGB.'),
                materials=('User-set uniform roughness and metallic; not recovered materials.'
                           if s.materials == 'Uniform values' or s.quality == 'Fast draft'
                           else 'AI estimated roughness and metallic.'),
                material_preprocessing=('Fixed-size crop follows subject translation; 512 px square input with gray alpha composite.'
                                        if s.materials == 'SuperMat estimates' else 'Full-frame inference.'),
                models={'depth': 'depth-anything/Depth-Anything-V2-Small-hf',
                        'normals': 'prs-eth/marigold-normals-v1-1' if s.quality.startswith('AI') else 'derived from depth',
                        'materials': ('oyiya/SuperMat' if s.quality.startswith('AI') and s.materials == 'SuperMat estimates'
                                      else 'prs-eth/marigold-iid-appearance-v1-1' if s.quality.startswith('AI')
                                      and (s.basecolor == 'AI albedo' or s.materials == 'AI estimates')
                                      else 'source color + user constants'),
                        'alpha': s.alpha},
                limitations=['Independent per-frame estimates with motion-compensated filtering; flicker may remain.',
                             'Specular is a user-set dielectric intensity, not a learned specular pass.',
                             'Not SwitchLight; materials and anime silhouettes can be inaccurate.'])
            (self.root / 'manifest.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
            validate_package(self.root)
            shutil.rmtree(work)
            status.unlink()
            if s.zip_output:
                self.event('Packing Blender-ready ZIP …', 'Export')
                part = self.root.with_suffix('.zip.partial')
                with zipfile.ZipFile(part, 'w', compression=zipfile.ZIP_STORED) as archive:
                    for file in sorted(self.root.rglob('*')):
                        self.check()
                        if file.is_file():
                            archive.write(file, str(Path(self.root.name) / file.relative_to(self.root)))
                part.replace(self.root.with_suffix('.zip'))
            self.event('Ready to import in Blender.', 'Complete', len(files), len(files),
                       str(self.root / 'normal' / '000000.png'))
            return self.root
        except BaseException as exc:
            status.write_text(f'Incomplete export: {type(exc).__name__}: {exc}', encoding='utf-8')
            raise

    def make_alpha(self, files, info, work, fps):
        mode = self.s.alpha
        session = None
        if mode in ('Anime subject', 'General subject'):
            self.event('Loading foreground model (first use downloads weights) …', 'Alpha')
            from rembg import new_session
            session = new_session('isnet-anime' if mode == 'Anime subject' else 'u2net',
                                  providers=['CPUExecutionProvider'])
        masks = None
        if mode == 'External matte':
            if not Path(self.s.mask_video).is_file():
                raise ValueError('Choose a black-and-white matte video.')
            mask_dir = work / 'matte'
            mask_dir.mkdir()
            mask_info = probe(Path(self.s.mask_video))
            masks = extract(Path(self.s.mask_video), mask_dir, mask_info, 0, fps, len(files),
                            self.cancel, lambda t: self.event(t, 'Alpha'))
            if len(masks) != len(files):
                raise ValueError('The matte video must cover every source frame.')
        if mode == 'Source alpha' and not info['has_alpha']:
            raise ValueError('This video does not contain an alpha channel. Choose an AI matte or Full frame.')
        smooth = TemporalFilter(self.s.temporal)
        for i, file, rgb in self.each('Alpha', files):
            if mode == 'Source alpha':
                with Image.open(file) as image:
                    alpha = np.asarray(image.getchannel('A'), np.float32) / 255
            elif masks:
                with Image.open(masks[i]) as image:
                    alpha = np.asarray(image.convert('L').resize((rgb.shape[1], rgb.shape[0])), np.float32) / 255
            elif session:
                from rembg import remove
                matte = remove(Image.fromarray(rgb), session=session, only_mask=True)
                alpha = np.asarray(matte.convert('L'), np.float32) / 255
                alpha = smooth(rgb, alpha)
            else:
                alpha = np.ones(rgb.shape[:2], np.float32)
            save_png(self.root / 'alpha' / file.name, alpha)
            Image.fromarray(rgb).save(file)  # Store straight RGB; opacity is its own pass.
        del session
        release()

    def make_depth(self, files, work):
        self.event('Loading depth model (first use downloads weights) …', 'Depth')
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        model_id = 'depth-anything/Depth-Anything-V2-Small-hf'
        processor = AutoImageProcessor.from_pretrained(model_id)
        model = AutoModelForDepthEstimation.from_pretrained(model_id, use_safetensors=True).to(self.device).eval()
        smooth = TemporalFilter(self.s.temporal)
        lows, highs = [], []
        for i, file, rgb in self.each('Depth', files):
            image = Image.fromarray(rgb)
            image.thumbnail((self.s.processing_size, self.s.processing_size))
            inputs = processor(images=image, return_tensors='pt').to(self.device)
            with torch.inference_mode():
                inverse = model(**inputs).predicted_depth[0].float().cpu().numpy()
            inverse = smooth(rgb, resize(inverse, rgb.shape))
            np.save(work / f'{i:06d}.npy', inverse)
            lows.append(float(np.percentile(inverse, 1)))
            highs.append(float(np.percentile(inverse, 99)))
        del model, processor, inputs
        release()
        low, high = min(lows), max(highs)
        for i, file, rgb in self.each('Depth export', files):
            inverse = np.load(work / f'{i:06d}.npy')
            depth = 1 - np.clip((inverse - low) / max(high - low, 1e-6), 0, 1)
            np.save(work / f'{i:06d}.npy', depth)
            save_depth(self.root / 'depth' / f'{i:06d}.exr', depth)

    def load_marigold(self, kind):
        import torch
        import diffusers
        ids = {'normals': 'prs-eth/marigold-normals-v1-1',
               'materials': 'prs-eth/marigold-iid-appearance-v1-1'}
        cls = diffusers.MarigoldNormalsPipeline if kind == 'normals' else diffusers.MarigoldIntrinsicsPipeline
        self.event(f'Loading AI {kind} model (first use downloads weights) …', kind.title())
        pipe = cls.from_pretrained(ids[kind], variant='fp16', torch_dtype=torch.float16,
                                   use_safetensors=True).to(self.device)
        pipe.set_progress_bar_config(disable=True)
        pipe.vae.enable_slicing()
        return pipe

    def predict(self, pipe, rgb):
        import torch
        # Same seeded noise for each frame reduces random variation; it is not a video model.
        rng = torch.Generator(device=self.device).manual_seed(1234)
        with torch.inference_mode():
            return pipe(Image.fromarray(rgb), num_inference_steps=self.s.steps, ensemble_size=1,
                        processing_resolution=self.s.processing_size, match_input_resolution=True,
                        generator=rng, output_type='np').prediction

    def make_normals(self, files):
        pipe = self.load_marigold('normals')
        smooth = TemporalFilter(self.s.temporal)
        for i, file, rgb in self.each('Normals', files):
            normal = self.predict(pipe, rgb)[0]
            normal = smooth(rgb, normal)
            normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-6)
            with Image.open(self.root / 'alpha' / file.name) as matte:
                background = np.asarray(matte) < 2
            normal[background] = (0, 0, 1)
            save_png(self.root / 'normal' / file.name, normal * .5 + .5)
        del pipe
        release()

    def make_materials(self, files):
        if self.s.materials == 'SuperMat estimates':
            return self.make_supermat(files)
        needs_ai = self.s.basecolor == 'AI albedo' or self.s.materials == 'AI estimates'
        pipe = self.load_marigold('materials') if needs_ai else None
        filters = [TemporalFilter(self.s.temporal) for _ in range(3)]
        for i, file, rgb in self.each('Materials', files):
            packed = {}
            if pipe is not None:
                predictions = self.predict(pipe, rgb)
                packed = dict(zip(pipe.target_properties['target_names'], predictions))
            # Do not let a generative material estimate rewrite the artwork by default.
            # Source colors intentionally retain baked lighting; they are not unlit albedo.
            if self.s.basecolor == 'Source colors':
                Image.fromarray(rgb).save(self.root / 'basecolor' / file.name)
            else:
                save_png(self.root / 'basecolor' / file.name, filters[0](rgb, packed['albedo']))
            if self.s.materials == 'AI estimates':
                channels = pipe.target_properties['material']['sub_target_names']
                material = packed['material']
                roughness = material[..., channels.index('roughness')]
                metallic = material[..., channels.index('metallicity')]
                roughness = filters[1](rgb, roughness)
                metallic = filters[2](rgb, metallic)
            else:
                roughness = np.full(rgb.shape[:2], self.s.roughness)
                metallic = np.full(rgb.shape[:2], self.s.metallic)
            roughness, metallic = self.material_background(file, roughness, metallic)
            for name, value in (('roughness', roughness), ('metallic', metallic)):
                save_png(self.root / name / file.name, value)
            save_png(self.root / 'specular' / file.name, np.full(rgb.shape[:2], self.s.specular))
        del pipe
        release()

    def make_supermat(self, files):
        from supermat_backend import SuperMatBackend, tracked_boxes
        self.event('Loading SuperMat local material model …', 'Materials')
        boxes = tracked_boxes([self.root / 'alpha' / file.name for file in files])
        backend = SuperMatBackend(self.device)
        filters = [TemporalFilter(self.s.temporal) for _ in range(3)]
        for i, file, rgb in self.each('SuperMat materials', files):
            with Image.open(self.root / 'alpha' / file.name) as image:
                alpha = np.asarray(image.convert('L'))
            albedo, roughness, metallic = backend.predict(rgb, alpha, boxes[file.name])
            if self.s.basecolor == 'Source colors':
                Image.fromarray(rgb).save(self.root / 'basecolor' / file.name)
            else:
                albedo = filters[0](rgb, albedo)
                albedo[alpha < 2] = 0
                save_png(self.root / 'basecolor' / file.name, albedo)
            roughness, metallic = self.material_background(file,
                filters[1](rgb, roughness), filters[2](rgb, metallic))
            save_png(self.root / 'roughness' / file.name, roughness)
            save_png(self.root / 'metallic' / file.name, metallic)
            save_png(self.root / 'specular' / file.name, np.full(rgb.shape[:2], self.s.specular))
        del backend
        release()

    def material_background(self, file, roughness, metallic):
        # Opacity is a separate pass. Neutralize only fully masked pixels, without
        # multiplying soft-edge material values by alpha a second time in Blender.
        with Image.open(self.root / 'alpha' / file.name) as image:
            background = np.asarray(image.convert('L')) < 2
        return np.where(background, 1., roughness), np.where(background, 0., metallic)

    def make_draft(self, files):
        for i, file, rgb in self.each('Draft materials', files):
            depth = np.load(self.root / '_work' / f'{i:06d}.npy')
            save_png(self.root / 'normal' / file.name, depth_normals(depth, self.s.normal_strength) * .5 + .5)
            Image.fromarray(rgb).save(self.root / 'basecolor' / file.name)
            roughness, metallic = self.material_background(file,
                np.full(rgb.shape[:2], self.s.roughness), np.full(rgb.shape[:2], self.s.metallic))
            for name, value in (('roughness', roughness), ('metallic', metallic),
                                ('specular', np.full(rgb.shape[:2], self.s.specular))):
                save_png(self.root / name / file.name, value)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate local VFX passes for the Beeble Blender add-on.')
    parser.add_argument('video')
    parser.add_argument('--output', default=str(ROOT / 'outputs'))
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--size', type=int, default=1080)
    parser.add_argument('--processing-size', type=int, default=512)
    parser.add_argument('--steps', type=int, default=4)
    parser.add_argument('--fps', default='')
    parser.add_argument('--draft', action='store_true')
    parser.add_argument('--basecolor', choices=['Source colors', 'AI albedo'], default='Source colors')
    parser.add_argument('--materials', choices=['Uniform values', 'AI estimates', 'SuperMat estimates'], default='SuperMat estimates')
    parser.add_argument('--alpha', choices=['Anime subject', 'General subject', 'Full frame', 'Source alpha', 'External matte'], default='Anime subject')
    parser.add_argument('--matte', default='')
    args = parser.parse_args()
    result = Generator(Settings(args.video, args.output, max_frames=args.frames, max_size=args.size,
                                processing_size=args.processing_size, steps=args.steps, fps=args.fps,
                                quality='Fast draft' if args.draft else 'AI materials + normals',
                                basecolor=args.basecolor,
                                materials=args.materials,
                                alpha=args.alpha, mask_video=args.matte)).run()
    print(result)
