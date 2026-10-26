# Third-party notices

Original VFX Pass Studio code is MIT licensed. Third-party code, runtimes,
models and their outputs retain their own licenses and terms.

- **SuperMat**: MIT, Copyright (c) 2026 Hong Yijia. Full notice and upstream
  revision: `vendor/supermat/LICENSE` and `UPSTREAM.json`.
- **Lucide**: ISC; full notice in `ui/vendor/LUCIDE-LICENSE.txt`.
- **Depth Anything V2 Small configuration**: Apache-2.0; the original JSON
  configuration, full license and pinned upstream revision are included in
  `vendor/depth_anything/`. Model weights still download separately.
- **Python 3.11.9**: installer includes the official Python NuGet runtime.
  Complete notices are installed as `runtime/LICENSE.txt`.
  Source: https://www.python.org/downloads/release/python-3119/
- Python dependencies download from PyPI and PyTorch's official index during
  setup. Their distributions include their respective notices.
- FFmpeg downloads directly from Gyan during setup, rather than being included
  in our installer. Its license and documentation remain in `tools/ffmpeg/`.
  Provider: https://www.gyan.dev/ffmpeg/builds/
- Microsoft WebView2 downloads from Microsoft if absent and retains Microsoft's terms.

Model weights are not redistributed. First use downloads selected models:
SuperMat (MIT), Depth Anything V2 Small (Apache-2.0), Marigold normals/appearance
(CreativeML Open RAIL++-M), SD2.1 components (their model license), and rembg's
foreground models (individual terms). See model cards linked in README.
The MIT license does not replace these model terms.

Beeble's proprietary add-on, templates, reference exports, and model/service code
are not distributed. The optional Blender bridge calls a separately installed
Beeble importer. VFX Pass Studio has no affiliation with Beeble.
