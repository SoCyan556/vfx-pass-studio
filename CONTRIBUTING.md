# Contributing

Use Python 3.11 on Windows. Run `setup.ps1`, then `.venv\Scripts\python.exe app.py`.
Run `.venv\Scripts\python.exe -m unittest test_contract test_packaging test_depth_loading test_temporal` before submitting.
Do not commit footage, generated passes, weights, local settings, credentials,
or proprietary Beeble files. `.gitignore` excludes runtime data.

Install Inno Setup, then build the Windows installer:

```powershell
packaging\build_windows.ps1 -InnoCompiler "C:\path\to\ISCC.exe"
```

The build fetches a checksum-pinned official Python runtime, stages an explicit
source allowlist, compiles the native launcher with Windows' .NET Framework compiler,
and builds the per-user installer. AI dependencies and FFmpeg download on first
launch; models download on first use. Keep third-party notices and licenses.
Contributions are under the project's MIT license.
