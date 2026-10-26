# Validation

## 0.4.2 temporal stabilization

- 20 unit/regression checks pass, including isolated AI mask dropouts, motion
  translation, affine depth drift, shot-cut rejection, zero strength and single frames.
- A real eight-frame clip completed anime foreground extraction, learned depth,
  Marigold normals and stabilized export. Export validation and monotonic progress passed.
- The desktop API integration test completed real draft inference and atomic ZIP
  export while preserving preferences and source alpha input.
- Synthetic dropout tests measure over 70% reduction in adjacent mask variation;
  this is a controlled regression result, not a quality guarantee for arbitrary footage.

## 0.4.1 depth initialization fix

- 15 tests pass, including the reported empty AutoImageProcessor lookup as a
  regression scenario. The bundled processor initializes with network blocked
  and produces exactly the same input tensors as the upstream configuration.
- Configurations and weights share pinned revision
  `5426e4f0f36572d16453bbda7a8389317b1bef99`; Apache-2.0 notices are included.
- Download failures retain their underlying exception rather than replacing it
  with the generic image-processor message.

Release 0.4.0 is validated on Windows with Python 3.11 and Blender 4.2 LTS.

## Automated checks

Run `python -m unittest test_contract test_packaging` after installing dependencies.
The 12 checks cover pass metadata, fractional FPS, EXR depth precision, frame
validation, normal direction, temporal cut rejection, source-color preservation,
material channels, subject crop restoration, source release boundaries, icon sizes
and alpha, and private FFmpeg resolution. No weights or user footage are required.

`pip check` validates the development environment's dependency consistency.
The optional GitHub Actions recipe is in `packaging/checks.workflow.yml`; copy it
to `.github/workflows/checks.yml` using an account with workflow permission to enable it.

## Windows distribution

The bundled official Python 3.11.9 runtime was tested creating an isolated venv
and running pip. FFmpeg download and checksum validation were exercised. The
installer is built from an explicit source allowlist; model weights, local
settings, footage, generated passes, test fixtures and proprietary add-on files
are excluded. Model terms and third-party notices remain separate from MIT.

## Pipeline and UI

Earlier local validation exercised real MP4 and ProRes MOV decoding, alpha,
all exported maps, ZIP export, cancellation, and import into a separately installed
Beeble add-on in a factory-startup Blender. Desktop/UI fixtures are not shipped.
`test_desktop_integration.py` expects a generated three-frame ProRes fixture;
`test_ui.cjs` expects a local UI fixture and Playwright. These are optional
integration checks rather than the model-free CI suite.

Material estimates can lose detail or flicker. Specular is a user-set constant.
Source base color retains baked lighting. Native video consistency and output
quality parity with commercial services are not established.
