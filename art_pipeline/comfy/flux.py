"""
本機 ComfyUI 的 Flux 2 Klein 產圖：一張參考圖加一段提示詞，出一張 1024 的圖。
城鎮貼圖、建築概念圖、NPC 立牌都走這一支，參考圖決定畫風，見 docs/城鎮建築產線.md。
ComfyUI 要先開著，桌面版只開啟動器不會開伺服器，開法見 docs/美術產線接手紀錄.md
"""
import hashlib
import io
import json
import os
import time
import urllib.request
import uuid

from PIL import Image

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
## 使用者 2026-09-25 給的 Stylized Fantasy Provencal 截圖，城鎮的畫風都照它
STYLE_REF = os.path.join(PROJECT_ROOT, "art_source", "textures", "reference", "provencal_4.webp")


def post(path, data, content_type="application/json"):
    req = urllib.request.Request(HOST + path, data=data, headers={"Content-Type": content_type})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def upload(path):
    raw = open(path, "rb").read()
    name = "ref_%s%s" % (hashlib.md5(raw).hexdigest()[:10], os.path.splitext(path)[1])
    boundary = uuid.uuid4().hex
    body = (("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
             % (boundary, name)).encode() + raw + ("\r\n--%s--\r\n" % boundary).encode())
    post("/upload/image", body, "multipart/form-data; boundary=" + boundary)
    return name


def graph(prompt, ref_name, seed, size=1024):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b-fp8.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "10": {"class_type": "LoadImage", "inputs": {"image": ref_name}},
        "20": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["10", 0], "upscale_method": "lanczos",
                                                                   "megapixels": 1.0, "resolution_steps": 1}},
        "30": {"class_type": "VAEEncode", "inputs": {"pixels": ["20", 0], "vae": ["3", 0]}},
        "40": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["4", 0], "latent": ["30", 0]}},
        "50": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["5", 0], "latent": ["30", 0]}},
        "60": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": size, "height": size, "batch_size": 1}},
        "61": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": size, "height": size}},
        "62": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "63": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "64": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["40", 0], "negative": ["50", 0], "cfg": 1}},
        "65": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["63", 0], "guider": ["64", 0], "sampler": ["62", 0],
                                                                 "sigmas": ["61", 0], "latent_image": ["60", 0]}},
        "66": {"class_type": "VAEDecode", "inputs": {"samples": ["65", 0], "vae": ["3", 0]}},
        "67": {"class_type": "SaveImage", "inputs": {"images": ["66", 0], "filename_prefix": "rof/flux"}},
    }


def run(g):
    r = post("/prompt", json.dumps({"prompt": g}).encode())
    if r.get("node_errors"):
        raise SystemExit("node_errors %s" % r["node_errors"])
    pid = r["prompt_id"]
    while True:
        h = json.loads(urllib.request.urlopen(HOST + "/history/" + pid, timeout=30).read())
        if pid in h:
            break
        time.sleep(1.5)
    status = h[pid].get("status", {})
    if status.get("status_str") == "error":
        raise SystemExit("error %s" % json.dumps(status)[:800])
    info = h[pid]["outputs"]["67"]["images"][0]
    q = "filename=%s&subfolder=%s&type=output" % (info["filename"], info["subfolder"])
    return Image.open(io.BytesIO(urllib.request.urlopen(HOST + "/view?" + q, timeout=60).read())).convert("RGB")
