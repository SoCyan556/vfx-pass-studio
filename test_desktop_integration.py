"""Real desktop API → local inference → export check, without opening or altering a UI."""
from pathlib import Path
import time
import tempfile
import zipfile
from unittest.mock import Mock, patch
from desktop import DesktopAPI, ROOT

api = DesktopAPI()
api._persist = lambda: None  # Keep the user's preferences untouched by the test.
api._staging = ROOT / 'test-artifacts' / 'desktop-staging'
assert all(name.startswith('_') or callable(getattr(api, name)) for name in vars(api))
assert api.frame('../outside') is None
assert 'error' in api.select_video(str(ROOT / 'README.md'))
source = ROOT / 'test-artifacts' / 'alpha-test.mov'
assert api.select_video(str(source))['video']['has_alpha']
result = api.start(dict(quality='Fast draft', alpha='Source alpha', size='384',
                         fps='24000/1001', processing=256, steps=1,
                         output=str(ROOT / 'test-artifacts' / 'desktop-exports')), preview=True)
assert result.get('ok'), result
assert api.start({}, True).get('error')
deadline = time.monotonic() + 120
events = []
while api._busy and time.monotonic() < deadline:
    events += api.poll()['events']
    time.sleep(.1)
events += api.poll()['events']
assert not api._busy, 'Worker did not finish'
done = next((event for event in events if event.get('type') == 'complete'), None)
assert done, events[-5:]
assert done['package']['count'] == 3
assert abs(done['package']['fps'] - 24000/1001) < 1e-8
assert not Path(done['package']['path']).with_suffix('.zip').exists(), 'Generation must not silently export a ZIP'
assert api.frame('normal', 2, 256).startswith('data:image/png;base64,')
assert api.frame('depth', 1, 256).startswith('data:image/png;base64,')
progress = [event['progress'] for event in events if 'progress' in event]
assert progress == sorted(progress)
assert progress[-1] == 1
with tempfile.TemporaryDirectory() as temp:
    target = Path(temp) / 'Chosen destination.zip'
    api._window = Mock()
    api._window.create_file_dialog.return_value = None
    assert api.export_passes().get('cancelled')
    assert not api._export_busy
    api._window.create_file_dialog.return_value = [str(target)]
    assert api.export_passes().get('ok')
    deadline = time.monotonic() + 15
    while api._export_busy and time.monotonic() < deadline:
        time.sleep(.05)
    assert target.is_file()
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert any(n.endswith('/Camera.json') for n in z.namelist())
    from media import export_zip
    original = target.read_bytes()
    with patch('media.zipfile.ZipFile.write', side_effect=OSError('Simulated write failure')):
        try:
            export_zip(Path(done['package']['path']), target)
            raise AssertionError('Expected export error')
        except OSError:
            pass
    assert target.read_bytes() == original, 'Failed export must preserve existing destination'
    assert not list(Path(temp).glob('*.partial'))
print('DESKTOP_API_PASS: real worker, monotonic progress, generation cache, explicit ZIP save/cancel, atomic overwrite, PNG and EXR previews.')
