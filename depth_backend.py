"""Pinned Depth Anything configuration, independent of AutoImageProcessor lookup."""
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / 'vendor' / 'depth_anything'
MODEL_ID = 'depth-anything/Depth-Anything-V2-Small-hf'
REVISION = '5426e4f0f36572d16453bbda7a8389317b1bef99'


def load_processor():
    from transformers import DPTImageProcessor
    config = json.loads((ASSETS / 'preprocessor_config.json').read_text(encoding='utf-8'))
    return DPTImageProcessor.from_dict(config)


def load_model(device, check=lambda: None, notify=lambda message: None):
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from transformers import DepthAnythingConfig, DepthAnythingForDepthEstimation
    check()
    arguments = dict(repo_id=MODEL_ID, filename='model.safetensors', revision=REVISION)
    try:
        weights = hf_hub_download(**arguments, local_files_only=True)
    except LocalEntryNotFoundError:
        notify('Downloading Depth Anything weights (first use) …')
        check()
        try:
            # Explicit known filename and revision avoid auto-discovery and negative metadata caches.
            weights = hf_hub_download(**arguments, force_download=True)
        except Exception as exc:
            raise RuntimeError(
                'Could not download Depth Anything weights from Hugging Face. '
                'Check this PC\'s Python internet/proxy/certificate settings and retry. '
                f'Details: {type(exc).__name__}: {exc}'
            ) from exc
    check()
    config = DepthAnythingConfig.from_dict(json.loads((ASSETS / 'config.json').read_text(encoding='utf-8')))
    return DepthAnythingForDepthEstimation.from_pretrained(
        str(Path(weights).parent), config=config, local_files_only=True,
        use_safetensors=True).to(device).eval()
