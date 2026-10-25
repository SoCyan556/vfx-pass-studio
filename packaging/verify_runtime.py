"""Check first-launch dependencies before marking installation complete."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
import cv2
import numpy
import PIL
import webview
import diffusers
import transformers
import rembg
import OpenEXR
from media import binary
print(binary('ffmpeg'))
print(binary('ffprobe'))
print('Runtime ready; CUDA:', torch.cuda.is_available())
