# VFX Pass Studio

A local Windows video-to-pass generator for the user's existing Beeble Blender add-on 1.11.0. Accepts MP4, MOV and FFmpeg-supported video. This is independent software, not SwitchLight or a Beeble service client. Your footage is processed locally. Public model weights download on first use.

## Start

**0.4.2:** improves AI mask, depth and normal consistency with shared forward/backward
motion and a five-frame window. Depth is aligned on reliable overlapping foreground,
and filtering resets at detected cuts. **Settings → Temporal stabilization → 60%**
is the new default; upgrades preserve your existing setting, so adjust it explicitly.
Regenerate passes to apply the change. Source alpha and external mattes are preserved.
This is motion-aware post-processing, not a temporally trained model; fast motion,
occlusions and incorrect segmentation can still fail. Lower the strength if motion
detail becomes too soft, or use an external matte for reliable subject boundaries.

**0.4.1:** fixes Depth Anything image-processor initialization on new PCs by
bundling the verified processor and architecture configuration. Close the app
before installing the update over 0.4.0. Settings, model caches and generated
passes are preserved. Model weights still download on first use.

Download the Windows installer from [Releases](https://github.com/SoCyan556/vfx-pass-studio/releases/latest), install it, then open **VFX Pass Studio** from Start or its optional desktop shortcut. The first launch installs the AI runtime and FFmpeg, and installs Microsoft WebView2 if missing. Internet and several GB of free disk space are needed. Model weights download when first used; footage stays local.

The installer includes a private Python 3.11 runtime, the fang taskbar/shortcut icon, and an uninstaller. No administrator account or system Python is required. Windows 10/11 x64 is supported. NVIDIA GPU acceleration is recommended; the full AI material mode requires an NVIDIA GPU. The installer is unsigned. Windows may show a publisher warning.

Choose a clip, foreground mode, output size and export folder. Try **Test 8 frames**, inspect the passes, then generate the full clip. Use **Repair runtime** in Start if initial setup was interrupted. Uninstall preserves generated passes, models and preferences; remove the remaining install folder manually if you also want to delete that data.

For a source checkout, run `setup.ps1`, then open **Launch VFX Pass Studio.vbs**. Build instructions are in [CONTRIBUTING.md](CONTRIBUTING.md).

### Black and red desktop interface

The supplied fang logo anchors a deep black interface with red gradients and animated hover feedback. Icons are bundled from [Lucide](https://lucide.dev); no CDN is required.

1. **Import and configure:** the app opens on a large drag-and-drop area with model, generation and base-color controls. Settings, size/FPS, an eight-frame test and Generate sit along the bottom. Previous result resumes the cached clip.
2. **Generate:** a dimmed, blurred overlay shows an animated progress bar, phase, completed frames, elapsed time and cancellation. Percentage comes from completed backend phases and frames, stays still during unknown-duration loading and never advances on a timer. It measures work completion, not estimated remaining time.
3. **Preview and export:** the setup controls give way to a large viewer and eight map/source cards along the bottom. The red **Export passes** button opens a native Save dialog for a Blender-ready ZIP. Canceling the dialog leaves the result available.

Desktop generation writes a working package under `cache/generations/`; it does not silently export a ZIP. ZIP export reports bytes packed and replaces the chosen destination atomically, preserving an existing file if packing fails. The command-line pipeline still writes its normal output folder and optional ZIP. Older exports remain loadable through the folder button on the setup screen.

Hover highlights, card tilt, sliding map selection, image crossfades and screen transitions respond to input. Reduced-motion preferences are respected. Space plays/pauses, arrows step frames, 1–8 select passes, F expands the viewer and Escape closes menus or dialogs. Keyboard playback shortcuts apply in preview with the work surface focused. Lucide's license is included in `ui/vendor/LUCIDE-LICENSE.txt`.

- **AI materials + normals**: Depth Anything V2 Small depth, Marigold normals, Marigold normals with Depth Anything depth and SuperMat spatial roughness/metallic estimates. Base color can preserve source RGB or use the selected backend's estimated albedo. Uniform material values and legacy Marigold estimates remain optional. Requires an NVIDIA GPU; tested with the local CUDA runtime. Specular is an adjustable constant.
- **Fast draft**: AI depth, depth-gradient normals, original source as base color, user-set material constants. These are explicitly a draft, not learned PBR decomposition.
- **Anime subject / General subject**: foreground estimation using rembg isnet-anime / U2Net. Can choose the wrong foreground; use an external matte for reliable subject isolation.
- **Source alpha**: preserve a video's existing alpha, e.g. ProRes 4444.
- **External matte**: synchronized video with white foreground / black background. The same output FPS is applied to source and matte; align their starting frames before use.
- **Full frame**: opaque alpha for every pixel, useful for scenes and testing.
- **Output long edge 0**: preserve source resolution. AI resolution controls the actual inference size; large output sizes do not create extra inferred detail.

## Blender

Keep your existing Beeble add-on installed and enabled. Use its **Import VFX Passes** button and select the exported ZIP, then **Edit & Render**. Its material, alpha erosion, depth, 2D↔3D, normal strength, shadows and camera controls remain available because this tool supplies its input format.

Recommended: install **vfx_blender_bridge.zip** via Preferences → Add-ons → Install from Disk, then enable **Local VFX Pass Import**. Use File → Import → Local VFX Passes and choose the export ZIP or `Camera.json`. This bridge calls the existing Beeble importer, preserves fractional FPS and restores exact image resolution after its aspect-ratio presets. It preserves the add-on's zero-numbered sequence convention. It does not include Beeble source or template assets. Extracted passes remain in Blender's user data folder because image sequences must remain on disk.

### Export contract

Each completed clip has a `.beeble` directory and matching `.zip`:

```
Camera.json
manifest.json
source/000000.png ...
alpha/000000.png ...
normal/000000.png ...
basecolor/000000.png ...
roughness/000000.png ...
specular/000000.png ...
metallic/000000.png ...
depth/000000.exr ...
```

All passes share frame numbering, resolution and FPS. Color passes are sRGB; data maps are Non-Color. Depth is an RGB half-float EXR with identical channels, 0 near / 1 far. The synthetic static camera sets a relative 1.0–1.4 depth range. It is **not camera tracking or metric reconstruction**. Blender's 3D control creates a view-dependent surface rather than a complete object. Cancelled/failed packages retain `INCOMPLETE.txt` and must not be imported. Only complete packages are zipped.

## Image quality

**Material response → SuperMat** selects the local SuperMat material decomposition model. It predicts albedo, roughness and metallic from alpha-isolated subjects against neutral gray at its recommended 512×512 resolution. A fixed-size crop follows subject translation, preserving aspect ratio and crop scale without enclosing the entire motion path. Predictions are restored to the source coordinates, with motion-aware temporal filtering. This is a single-image model with post-filtering, not a native video model. It does not predict specular. Downloads include the official ~3.54 GB SuperMat checkpoint plus SD2.1 VAE/text components; no footage is uploaded. The loader uses memory-mapped weights and avoids allocating duplicate initialized UNets.

**Marigold** retains the earlier material model for comparison. **Uniform values** explicitly uses chosen constants (roughness 0.65, metallic 0.0 by default), not recovered materials. Fully masked background is roughness 1 and metallic 0. Soft edge pixels retain their material values without a second alpha multiplication.

Models infer each frame separately. Fixed noise plus motion-compensated filtering reduces flicker, but this is not a temporally trained video model. Fast motion, cuts, occlusions, anime shading and small details can fail. Check a preview before full processing. Base color defaults to **Source colors**, preserving the decoded palette and linework without AI repainting or temporal blending. This includes baked lighting; it is not recovered unlit albedo. **Settings → Base Color → AI albedo** uses the selected material model for experimental de-lighting, which can wash out colors and lose details, especially on anime. Existing exports are unchanged. To create a repaired copy with source colors, run `.venv\Scripts\python.exe repair_basecolor.py "path\to\export.beeble"`; it preserves the original and writes a new folder and ZIP. Specular is always a chosen dielectric intensity, not a predicted pass. No model or output-quality equivalence to Beeble is claimed.

## Setup on another Windows machine

The installer handles Python, FFmpeg and WebView2. Install a recent NVIDIA driver separately. For source development, install Python 3.11 and run `setup.ps1`. It installs a private `.venv`, pywebview, CUDA-enabled PyTorch and media prerequisites; no system Python packages are changed. `setup.ps1 -Cpu` installs CPU PyTorch for draft/development use. Models are cached under `models/`. Model weights are not bundled in the installer or source archive.

Command line:

```
.venv\Scripts\python.exe pipeline.py "C:\clips\shot.mov" --output "C:\passes" --frames 8
```

## Model sources and terms

- [SuperMat source](https://github.com/hyj542682306/SuperMat) and [official weights](https://huggingface.co/oyiya/SuperMat) — MIT; vendored source, upstream revision and license in `vendor/supermat/`. Base [SD2.1 components](https://huggingface.co/sd2-community/stable-diffusion-2-1) retain their model terms.

- [Depth Anything V2 Small](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf) — Apache 2.0.
- [Marigold normals](https://huggingface.co/prs-eth/marigold-normals-v1-1) and [Marigold appearance](https://huggingface.co/prs-eth/marigold-iid-appearance-v1-1) — CreativeML Open RAIL++-M model terms.
- [rembg](https://github.com/danielgatis/rembg) — MIT library; individual model terms also apply.
- [Marigold integration reference](https://huggingface.co/docs/diffusers/api/pipelines/marigold).

The separately supplied Beeble add-on belongs to its authors and is not redistributed here.

## License

Original application code is open source under the [MIT license](LICENSE). Third-party components and models retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Panel taglines, explanatory footnotes, setup helper descriptions and persistent footer status text have been removed. Operational controls, file metadata and live generation counters remain; activity and Blender help are available from the header.
