from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
PUBLISH_FILES = (
    'app.py', 'desktop.py', 'pipeline.py', 'media.py', 'requirements.txt', 'setup.ps1',
    'Launch VFX Pass Studio.vbs', 'README.md', 'VALIDATION.md', '.gitignore',
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CONTRIBUTING.md',
    'vfx_blender_bridge/__init__.py', 'test_contract.py', 'make_test_clip.py',
    'blender_smoke_test.py', 'build_distribution.py', 'test_ui.cjs',
    'test_desktop_integration.py', 'repair_basecolor.py', 'supermat_backend.py',
    'test_packaging.py',
)

def source_files():
    files = [ROOT / name for name in PUBLISH_FILES]
    for directory in ('ui', 'vendor/supermat', 'packaging', '.github'):
        files += [p for p in (ROOT / directory).rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'
                  and not p.name.endswith('.edit.txt') and p.name != 'fangs.png']
    return sorted(files)

def main():
    with zipfile.ZipFile(ROOT / 'vfx_blender_bridge.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'vfx_blender_bridge/__init__.py', 'vfx_blender_bridge/__init__.py')
    with zipfile.ZipFile(ROOT / 'VFX-Pass-Studio-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            archive.write(path, f'VFX Pass Studio/{path.relative_to(ROOT).as_posix()}')
    print('Built source archive and Blender bridge, excluding local data and model weights.')

if __name__ == '__main__':
    main()
