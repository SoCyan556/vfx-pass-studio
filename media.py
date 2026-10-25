"""Video decoding and the on-disk interchange contract for Beeble 1.11.0."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
PASSES = ('source', 'alpha', 'normal', 'basecolor', 'roughness', 'specular', 'metallic', 'depth')


class Cancelled(Exception):
    pass


def export_zip(root: Path, destination: Path, progress=None):
    """Write an explicit user export atomically; preserve an existing file on failure."""
    root, destination = root.resolve(), destination.resolve()
    if (root / 'INCOMPLETE.txt').exists():
        raise ValueError('This generation is incomplete.')
    validate_package(root)
    if destination.is_relative_to(root):
        raise ValueError('Choose a destination outside the generated package folder.')
    files = sorted(p for p in root.rglob('*') if p.is_file())
    total = sum(p.stat().st_size for p in files)
    done = 0
    temporary = destination.with_name(f'.{destination.name}.{uuid.uuid4().hex}.partial')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
            for file in files:
                archive.write(file, str(Path(root.name) / file.relative_to(root)))
                done += file.stat().st_size
                if progress:
                    progress(done, total)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def binary(name: str) -> str:
    bundled = Path(__file__).resolve().parent / 'tools' / 'ffmpeg' / 'bin' / f'{name}.exe'
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    candidate = Path.home() / 'ffmpeg' / 'bin' / f'{name}.exe'
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(f'{name} was not found. Install FFmpeg and add its bin folder to PATH.')


def probe(path: Path) -> dict:
    result = subprocess.run(
        [binary('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_streams',
         '-show_format', '-of', 'json', str(path)], capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW, check=True)
    data = json.loads(result.stdout)
    if not data.get('streams'):
        raise ValueError('This file has no video stream.')
    stream = data['streams'][0]
    rate = stream.get('avg_frame_rate') or stream.get('r_frame_rate') or '0/1'
    fps = Fraction(rate)
    if fps <= 0:
        raise ValueError('Could not determine the video frame rate. Convert the clip to constant frame rate first.')
    width, height = int(stream['width']), int(stream['height'])
    for side in stream.get('side_data_list', []):
        if abs(int(side.get('rotation', 0))) % 180 == 90:
            width, height = height, width
    pix = stream.get('pix_fmt', '')
    return dict(width=width, height=height, fps=str(fps),
                duration=float(stream.get('duration') or data.get('format', {}).get('duration') or 0),
                has_alpha=('a' in pix and (pix.startswith(('yuva', 'gbrap')) or pix in ('rgba', 'bgra', 'argb', 'abgr'))),
                pixel_format=pix)


def extract(path: Path, output: Path, info: dict, max_size: int, fps: Fraction,
            max_frames: int, cancel, log) -> list[Path]:
    width, height = info['width'], info['height']
    factor = min(1, max_size / max(width, height)) if max_size else 1
    width, height = max(2, round(width * factor)), max(2, round(height * factor))
    command = [binary('ffmpeg'), '-hide_banner', '-v', 'error', '-nostdin', '-i', str(path),
               '-map', '0:v:0', '-an', '-vf', f'fps={fps},scale={width}:{height}:flags=lanczos',
               '-pix_fmt', 'rgba', '-start_number', '0']
    if max_frames:
        command += ['-frames:v', str(max_frames)]
    command += [str(output / '%06d.png')]
    log(f'Decoding {path.name} at {float(fps):.3f} fps, {width} × {height} …')
    with (output.parent / 'decode.log').open('w', encoding='utf-8') as error_file:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_file,
                                   creationflags=CREATE_NO_WINDOW)
        while process.poll() is None:
            if cancel.is_set():
                process.terminate()
                process.wait()
                raise Cancelled()
            time.sleep(.1)
    if process.returncode:
        raise RuntimeError((output.parent / 'decode.log').read_text(encoding='utf-8')[-4000:])
    frames = sorted(output.glob('*.png'))
    if not frames:
        raise ValueError('FFmpeg decoded no frames.')
    return frames


def save_png(path: Path, array: np.ndarray):
    array = np.nan_to_num(array, nan=0., posinf=1., neginf=0.)
    Image.fromarray(np.uint8(np.clip(array, 0, 1) * 255 + .5)).save(path)


def save_depth(path: Path, depth: np.ndarray):
    import OpenEXR
    channel = np.ascontiguousarray(depth, dtype=np.float16)
    # RGB channels are intentional: the add-on samples the image Color socket.
    OpenEXR.File({'compression': OpenEXR.ZIP_COMPRESSION},
                 {'R': channel, 'G': channel, 'B': channel}).write(str(path))


def camera_metadata(width: int, height: int, fps: Fraction, count: int) -> dict:
    portrait = height > width
    transform = ([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1], [0, 0, 0, 1]] if portrait else
                 [[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 1], [0, 0, 0, 1]])
    frame = dict(focal_length=24. if portrait else 28., transform=transform,
                 camera_given=False, position_median=[0, 0, -1.2],
                 position_foot=[0, 0, -1.2], depth_min=1., depth_max=1.4)
    return dict(resolution=[width, height], frame_count=count, frame_rate=float(fps),
                fps_numerator=fps.numerator, fps_denominator=fps.denominator,
                orientation=1 if portrait else 3, sensor_height=36. if portrait else 24.,
                scale=1., studio={'transform': [[1, 0, 0, 0], [0, 0, 1, 0],
                                               [0, -1, 0, 0], [0, 0, 0, 1]]},
                frames=[dict(frame) for _ in range(count)])


def validate_package(root: Path) -> dict:
    data = json.loads((root / 'Camera.json').read_text(encoding='utf-8'))
    count = data['frame_count']
    if count < 1 or len(data['frames']) != count:
        raise ValueError('Camera frame count is inconsistent.')
    width, height = data['resolution']
    for name in PASSES:
        ext = '.exr' if name == 'depth' else '.png'
        expected = {f'{n:06d}{ext}' for n in range(count)}
        actual = {p.name for p in (root / name).glob(f'*{ext}')}
        if expected != actual:
            raise ValueError(f'{name}: missing or unexpected frames.')
        if name != 'depth':
            with Image.open(root / name / f'000000{ext}') as image:
                if image.size != (width, height):
                    raise ValueError(f'{name}: incorrect resolution.')
    return data
