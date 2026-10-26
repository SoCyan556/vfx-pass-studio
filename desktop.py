"""Animated desktop shell backed by the existing local inference pipeline."""
from __future__ import annotations
import base64
from collections import deque
from functools import lru_cache
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import sys
import threading
from PIL import Image
import webview

ROOT = Path(__file__).resolve().parent
logging.basicConfig(filename=ROOT / 'app.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
if sys.stdout is None or sys.stderr is None:
    _stream = (ROOT / 'model-downloads.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stdout or _stream
    sys.stderr = sys.stderr or _stream
PASS_NAMES = ('normal', 'basecolor', 'roughness', 'specular', 'metallic', 'depth', 'alpha', 'source')
DEFAULTS = dict(video='', output=str(ROOT / 'outputs'), alpha='Anime subject', matte='',
                quality='AI materials + normals', size='1080', fps='', steps=4, processing=512,
                temporal=.6, specular=.5, roughness=.65, metallic=0., basecolor='Source colors', materials='SuperMat estimates', last_export='')

class DesktopAPI:
    def __init__(self):
        self._window = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._settings_lock = threading.Lock()
        self._events = deque(maxlen=2000)
        self._busy = False
        self._export_busy = False
        self._staging = ROOT / 'cache' / 'generations'
        self._package = None
        self._sequence = 0
        self._config = dict(DEFAULTS)
        try:
            stored = json.loads((ROOT / 'app_settings.json').read_text(encoding='utf-8'))
            self._config.update({key: stored[key] for key in DEFAULTS if key in stored})
        except (OSError, ValueError):
            pass
        if self._config['last_export']:
            try:
                self._load(Path(self._config['last_export']))
            except Exception:
                logging.exception('Could not restore last export')

    def _persist(self):
        with self._settings_lock:
            temporary = ROOT / 'app_settings.json.tmp'
            temporary.write_text(json.dumps(self._config, indent=2), encoding='utf-8')
            temporary.replace(ROOT / 'app_settings.json')

    def _emit(self, event):
        with self._lock:
            self._sequence += 1
            self._events.append(dict(event, sequence=self._sequence))

    def _load(self, path):
        from media import validate_package
        path = path.resolve()
        if (path / 'INCOMPLETE.txt').exists():
            raise ValueError('This export is incomplete. Finish generation before loading it.')
        data = validate_package(path)
        self._package = path
        self._config['last_export'] = str(path)
        self._frame_data.cache_clear()
        return dict(name=path.stem, path=str(path), count=data['frame_count'],
                    fps=data['frame_rate'], width=data['resolution'][0], height=data['resolution'][1],
                    demo=path.name.startswith('Demo'))

    def bootstrap(self):
        package = self._load(self._package) if self._package else None
        video = None
        if self._config['video'] and Path(self._config['video']).is_file():
            try:
                video = self._video_info(self._config['video'])
            except Exception:
                pass
        return dict(settings=dict(self._config), package=package, video=video, busy=self._busy,
                    exporting=self._export_busy, model='SuperMat · Marigold · Depth Anything', version='0.4.2')

    def poll(self):
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return dict(events=events, busy=self._busy, exporting=self._export_busy)

    def _video_info(self, path):
        from media import probe
        return dict(probe(Path(path)), path=str(path), name=Path(path).name)

    def select_video(self, path):
        if self._busy:
            return dict(error='Wait for generation to finish before changing the source.')
        try:
            path = Path(path).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.mp4', '.mov', '.mkv', '.m4v', '.avi', '.webm'):
                raise ValueError('Choose an MP4, MOV, or another supported video file.')
            info = self._video_info(path)
            self._config['video'] = str(path)
            if info['has_alpha']:
                self._config['alpha'] = 'Source alpha'
            self._persist()
            return dict(video=info, alpha=self._config['alpha'])
        except Exception as exc:
            return dict(error=str(exc))

    def browse_video(self):
        files = self._window.create_file_dialog(webview.FileDialog.OPEN,
                    file_types=('Video files (*.mp4;*.mov;*.mkv;*.m4v;*.avi;*.webm)', 'All files (*.*)'))
        return self.select_video(files[0]) if files else None

    def choose_folder(self, kind='output'):
        if self._busy:
            return dict(error='Wait for generation to finish.')
        folders = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=self._config['output'])
        if not folders:
            return None
        try:
            if kind == 'export':
                data = self._load(Path(folders[0]))
                self._persist()
                return dict(package=data)
            self._config['output'] = folders[0]
            self._persist()
            return dict(path=folders[0])
        except Exception as exc:
            return dict(error=str(exc))

    def choose_matte(self):
        files = self._window.create_file_dialog(webview.FileDialog.OPEN,
                    file_types=('Video files (*.mp4;*.mov;*.mkv;*.avi)', 'All files (*.*)'))
        if not files:
            return None
        self._config['matte'] = files[0]
        self._config['alpha'] = 'External matte'
        self._persist()
        return dict(path=files[0])

    def save_settings(self, settings):
        if not self._busy:
            self._config.update({key: value for key, value in settings.items()
                                if key in DEFAULTS and key not in ('video', 'last_export')})
            self._persist()
        return dict(ok=True)

    @lru_cache(maxsize=64)
    def _frame_data(self, package, name, index, width):
        path = Path(package) / name / f'{index:06d}{".exr" if name == "depth" else ".png"}'
        if name == 'depth':
            import numpy as np
            import OpenEXR
            with OpenEXR.File(str(path), separate_channels=True) as file:
                values = file.channels()['R'].pixels
            image = Image.fromarray(np.uint8(np.clip(values, 0, 1) * 255)).convert('RGB')
        else:
            with Image.open(path) as file:
                image = file.convert('RGB')
        image.thumbnail((width, width), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')

    def frame(self, name, index=0, width=1400):
        if not self._package or name not in PASS_NAMES:
            return None
        try:
            count = len(list((self._package / 'source').glob('*.png')))
            return self._frame_data(str(self._package), name,
                                    min(count - 1, max(0, int(index))), min(1800, max(100, int(width))))
        except Exception:
            logging.exception('Preview loading failed')
            return None

    def start(self, settings, preview=False):
        with self._lock:
            if self._busy or self._export_busy:
                return dict(error='A clip is already being processed.')
            self._busy = True
        try:
            from pipeline import Generator, Settings
            self._config.update({key: value for key, value in settings.items()
                                if key in DEFAULTS and key not in ('video', 'last_export')})
            c = self._config
            source = Path(c['video'])
            if not c['video'] or not source.is_file():
                raise ValueError('Drop a video or choose Browse File first.')
            if c['alpha'] == 'External matte' and not Path(c['matte']).is_file():
                raise ValueError('Choose an external matte in Settings first.')
            s = Settings(str(source), str(self._staging), max_size=int(c['size']), fps=c['fps'].strip(),
                         max_frames=8 if preview else 0, alpha=c['alpha'], mask_video=c['matte'],
                         quality=c['quality'], steps=int(c['steps']), processing_size=int(c['processing']),
                         basecolor=c['basecolor'],
                         materials=c['materials'],
                         temporal=float(c['temporal']), specular=float(c['specular']),
                         roughness=float(c['roughness']), metallic=float(c['metallic']), zip_output=False)
            self._persist()
            self._cancel.clear()
            def worker():
                try:
                    path = Generator(s, self._emit, self._cancel).run()
                    package = self._load(path)
                    self._persist()
                    self._emit(dict(type='complete', package=package))
                except Exception as exc:
                    logging.exception('Generation ended')
                    self._emit(dict(type='cancelled' if self._cancel.is_set() else 'error', message=str(exc) or type(exc).__name__))
                finally:
                    with self._lock:
                        self._busy = False
            threading.Thread(target=worker, daemon=True).start()
            return dict(ok=True)
        except Exception as exc:
            with self._lock:
                self._busy = False
            return dict(error=str(exc))

    def stop(self):
        self._cancel.set()
        return dict(ok=True)

    def export_passes(self):
        with self._lock:
            if self._busy or self._export_busy:
                return dict(error='Wait for the current operation to finish.')
            if not self._package:
                return dict(error='Generate or load passes before exporting.')
            self._export_busy = True
        try:
            files = self._window.create_file_dialog(webview.FileDialog.SAVE,
                directory=self._config['output'], save_filename=self._package.stem + '.zip',
                file_types=('Blender pass archive (*.zip)',))
            if not files:
                self._export_busy = False
                return dict(cancelled=True)
            destination = Path(files[0])
            if destination.suffix.lower() != '.zip':
                destination = destination.with_name(destination.name + '.zip')
            package = self._package
            def worker():
                try:
                    from media import export_zip
                    def progress(current, total):
                        self._emit(dict(type='export_progress', current=current, total=total,
                                        progress=current / max(total, 1)))
                    export_zip(package, destination, progress)
                    self._config['output'] = str(destination.parent)
                    self._persist()
                    self._emit(dict(type='export_complete', path=str(destination)))
                except Exception as exc:
                    logging.exception('Export failed')
                    self._emit(dict(type='export_error', message=str(exc)))
                finally:
                    self._export_busy = False
            threading.Thread(target=worker, daemon=True).start()
            return dict(ok=True)
        except Exception as exc:
            self._export_busy = False
            return dict(error=str(exc))

    def open_output(self):
        path = self._package.parent if self._package else Path(self._config['output'])
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def window_action(self, action):
        if action == 'minimize':
            self._window.minimize()
        elif action == 'maximize':
            if getattr(self, '_maximized', False):
                self._window.restore()
                self._maximized = False
            else:
                self._window.maximize()
                self._maximized = True
        elif action == 'close':
            self._cancel.set()
            self._window.destroy()

def main():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SoCyan.VFXPassStudio')
    api = DesktopAPI()
    window = webview.create_window('VFX Pass Studio', str(ROOT / 'ui' / 'index.html'),
                    js_api=api, width=1460, height=960, min_size=(1080, 740), frameless=True,
                    easy_drag=False, shadow=True, background_color='#050505', text_select=False)
    api._window = window
    def bind():
        from webview.dom import DOMEventHandler
        def drop(event):
            files = event.get('dataTransfer', {}).get('files', [])
            if files and files[0].get('pywebviewFullPath'):
                result = api.select_video(files[0]['pywebviewFullPath'])
                window.evaluate_js(f'window.studio.receiveVideo({json.dumps(result)})')
        window.dom.document.events.drop += DOMEventHandler(drop, prevent_default=True)
    window.events.loaded += bind
    window.events.closing += lambda: api._cancel.set()
    webview.start(gui='edgechromium', debug='--debug' in sys.argv, private_mode=True,
                  icon=str(ROOT / 'ui' / 'assets' / 'vfx-pass-studio.ico'))

if __name__ == '__main__':
    main()
