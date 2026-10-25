"""Local SuperMat inference; upstream source and attribution live in vendor/supermat."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent


def tracked_boxes(alpha_files):
    """Follow subject translation at one fixed scale rather than enclosing its entire path."""
    samples = []
    for path in alpha_files:
        with Image.open(path) as image:
            width, height = image.size
            box = image.convert('L').point(lambda x: 255 if x > 128 else 0).getbbox()
        samples.append((path.name, width, height, box))
    size = max((max(b[2]-b[0], b[3]-b[1]) for _, _, _, b in samples if b), default=512)
    size += max(32, round(size*.12))
    result = {}
    for name, width, height, box in samples:
        cx, cy = ((box[0]+box[2])/2, (box[1]+box[3])/2) if box else (width/2, height/2)
        w, h = min(size, width), min(size, height)
        left = max(0, min(width-w, round(cx-w/2)))
        top = max(0, min(height-h, round(cy-h/2)))
        result[name] = (left, top, left+w, top+h)
    return result


def shot_box(alpha_files):
    """Use one crop for the whole shot so crop scale cannot pump between frames."""
    boxes = []
    width = height = 0
    for path in alpha_files:
        with Image.open(path) as image:
            width, height = image.size
            box = image.convert('L').point(lambda x: 255 if x > 128 else 0).getbbox()
        if box:
            boxes.append(box)
    if not boxes:
        return 0, 0, width, height
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
    pad = max(16, round(max(right-left, bottom-top) * .06))
    return max(0, left-pad), max(0, top-pad), min(width, right+pad), min(height, bottom+pad)


def prepare(rgb, alpha, box, size=512):
    left, top, right, bottom = box
    crop = rgb[top:bottom, left:right].astype(np.float32) / 255
    mask = alpha[top:bottom, left:right].astype(np.float32) / 255
    crop = crop * mask[..., None] + .5 * (1-mask[..., None])
    height, width = crop.shape[:2]
    side = max(height, width)
    x, y = (side-width)//2, (side-height)//2
    square = np.full((side, side, 3), .5, np.float32)
    square[y:y+height, x:x+width] = crop
    return cv2.resize(square, (size, size), interpolation=cv2.INTER_LINEAR), (x, y, width, height, side)


def restore(value, layout, box, shape, background):
    x, y, width, height, side = layout
    square = cv2.resize(value, (side, side), interpolation=cv2.INTER_LINEAR)
    result = np.full(shape[:2] + value.shape[2:], background, np.float32)
    left, top, right, bottom = box
    result[top:bottom, left:right] = square[y:y+height, x:x+width]
    return result


class SuperMatBackend:
    def __init__(self, device='cuda'):
        import torch
        from accelerate import init_empty_weights
        from huggingface_hub import hf_hub_download, snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        from diffusers import DDIMScheduler
        from vendor.supermat.src.models.supermat_unet_2d_condition import SuperMatUNet2DConditionModel
        from vendor.supermat.src.pipelines.pipeline_supermat_stable_diffusion import SuperMatStableDiffusionPipeline
        self.device = device
        try:
            checkpoint = hf_hub_download('oyiya/SuperMat', 'supermat.pth', local_files_only=True)
        except LocalEntryNotFoundError:
            checkpoint = hf_hub_download('oyiya/SuperMat', 'supermat.pth')
        patterns = [
            'model_index.json', 'scheduler/*', 'tokenizer/*', 'unet/config.json',
            'text_encoder/config.json', 'text_encoder/model.fp16.safetensors',
            'vae/config.json', 'vae/diffusion_pytorch_model.fp16.safetensors']
        try:
            base = snapshot_download('sd2-community/stable-diffusion-2-1', local_files_only=True)
            required = ['unet/config.json', 'text_encoder/model.fp16.safetensors',
                        'vae/diffusion_pytorch_model.fp16.safetensors', 'tokenizer/vocab.json',
                        'scheduler/scheduler_config.json']
            if not all((Path(base)/name).is_file() for name in required):
                raise LocalEntryNotFoundError('Some SuperMat base components are not cached.')
        except LocalEntryNotFoundError:
            base = snapshot_download('sd2-community/stable-diffusion-2-1', allow_patterns=patterns)
        config = json.loads((Path(base)/'unet'/'config.json').read_text())
        with init_empty_weights():
            unet = SuperMatUNet2DConditionModel.from_config(config)
            unet.replicate(replicate_num=2, shared_blocks_lora=False)
        state = torch.load(checkpoint, map_location='cpu', weights_only=True, mmap=True)
        unet.load_state_dict(state, strict=True, assign=True)
        del state
        self.pipe = SuperMatStableDiffusionPipeline.from_pretrained(base, unet=unet,
            safety_checker=None, feature_extractor=None, requires_safety_checker=False,
            variant='fp16', torch_dtype=torch.float16)
        self.pipe.scheduler = DDIMScheduler.from_config(self.pipe.scheduler.config, timestep_spacing='trailing')
        self.pipe = self.pipe.to(device=device, dtype=torch.float32)
        self.pipe.set_progress_bar_config(disable=True)

    def predict(self, rgb, alpha, box):
        import torch
        image, layout = prepare(rgb, alpha, box)
        tensor = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            output = self.pipe(prompt='', num_inference_steps=1, source_image=tensor, output_type='pt')
        values = [a[0].permute(1, 2, 0).float().cpu().numpy() for a in output]
        albedo = restore(values[0], layout, box, rgb.shape, 0)
        roughness = restore(values[1][..., 1], layout, box, rgb.shape, 1)
        metallic = restore(values[1][..., 2], layout, box, rgb.shape, 0)
        return albedo, roughness, metallic
