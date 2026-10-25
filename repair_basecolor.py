"""Create a corrected export using source RGB, leaving the original package intact."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image
from media import validate_package


def repair(source: Path) -> Path:
    source = source.resolve()
    if (source / 'INCOMPLETE.txt').exists():
        raise ValueError('Cannot repair an incomplete export.')
    validate_package(source)
    target = source.with_name(source.stem + f'_color-fixed_{datetime.now():%H%M%S_%f}.beeble')
    shutil.copytree(source, target)
    marker = target / 'INCOMPLETE.txt'
    marker.write_text('Repair in progress', encoding='utf-8')
    for frame in sorted((target / 'source').glob('*.png')):
        with Image.open(frame) as image:
            image.convert('RGB').save(target / 'basecolor' / frame.name)
    manifest_path = target / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.setdefault('settings', {})['basecolor'] = 'Source colors'
    manifest['basecolor'] = 'Source RGB in sRGB; retains baked lighting.'
    manifest['repair'] = dict(original_export=str(source), changed_passes=['basecolor'])
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    validate_package(target)
    marker.unlink()
    temporary = target.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
        for file in sorted(target.rglob('*')):
            if file.is_file():
                archive.write(file, str(Path(target.name) / file.relative_to(target)))
    temporary.replace(target.with_suffix('.zip'))
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(repair(parser.parse_args().package))
