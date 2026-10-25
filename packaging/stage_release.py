"""Stage only explicitly published source; never sweep up local user data."""
from pathlib import Path
import shutil
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_distribution import source_files

stage = ROOT / 'build' / 'stage'
if stage.exists():
    if stage.resolve() != ROOT.resolve() / 'build' / 'stage':
        raise RuntimeError('Refusing to clear a staging directory outside this project.')
    shutil.rmtree(stage)
stage.mkdir(parents=True, exist_ok=True)
for source in source_files():
    target = stage / source.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
with zipfile.ZipFile(ROOT / 'build' / 'python-3.11.9.nupkg') as archive:
    for member in archive.infolist():
        if not member.filename.startswith('tools/') or member.is_dir():
            continue
        target = stage / 'runtime' / member.filename.removeprefix('tools/')
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, target.open('wb') as dst:
            shutil.copyfileobj(src, dst)
print(f'Staged {len(list(stage.rglob("*")))} files and directories.')
