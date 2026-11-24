"""Cari posisi facecam di video 16:9 supaya bisa ditaruh di atas layout 9:16.

Urutan: preset per channel (paling stabil) → auto-detect wajah pakai YuNet → None (center crop).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np

from src.paths import ROOT

PRESETS = ROOT / "presets"
YUNET = ROOT / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
CAM_ASPECT = 1080 / 640


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def load_preset(channel: str):
    p = PRESETS / f"{slug(channel)}.json"
    if p.exists():
        return tuple(json.loads(p.read_text())["cam_box"])
    return None


def save_preset(channel: str, box: tuple[int, int, int, int], source: str) -> Path:
    PRESETS.mkdir(exist_ok=True)
    p = PRESETS / f"{slug(channel)}.json"
    p.write_text(json.dumps({"channel": channel, "cam_box": list(box), "source": source}, indent=2))
    return p


def ensure_yunet() -> Path:
    if not YUNET.exists():
        YUNET.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, YUNET)
    return YUNET


def detect_faces(video: Path, samples: int = 30) -> tuple[list[np.ndarray], int, int]:
    import cv2

    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    det = cv2.FaceDetectorYN.create(str(ensure_yunet()), "", (W, H), score_threshold=0.7)
    boxes = []
    for i in np.linspace(0, max(n - 1, 0), samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        _, faces = det.detect(frame)
        if faces is not None and len(faces):
            boxes.append(max(faces, key=lambda f: f[2] * f[3])[:4])
    cap.release()
    return boxes, W, H


def cam_box_from_face(face: np.ndarray, W: int, H: int, expand: float = 1.6,
                      face_y: float = 0.45) -> tuple[int, int, int, int]:
    """Kotak 1080:640 di sekitar wajah. Tinggi = expand x tinggi wajah, wajah di 45% dari atas."""
    x, y, w, h = face
    cx, cy = x + w / 2, y + h / 2
    ch = min(h * expand, H)
    cw = min(ch * CAM_ASPECT, W)
    ch = cw / CAM_ASPECT
    x0 = int(np.clip(cx - cw / 2, 0, W - cw)) // 2 * 2
    y0 = int(np.clip(cy - ch * face_y, 0, H - ch)) // 2 * 2
    return x0, y0, int(cw) // 2 * 2, int(ch) // 2 * 2


def detect_facecam(video: Path, samples: int = 30, min_hit: float = 0.5):
    """Return (x, y, w, h) area facecam, atau None kalau tidak ada wajah yang konsisten."""
    boxes, W, H = detect_faces(video, samples)
    if len(boxes) < samples * min_hit:
        return None
    arr = np.array(boxes)
    med = np.median(arr, axis=0)
    spread = np.median(np.abs(arr[:, :2] - med[:2]), axis=0)
    if (spread > med[2:] * 0.5).any():
        return None    # wajah pindah-pindah, berarti bukan facecam tetap
    return cam_box_from_face(med, W, H)


def preset_or_detect(video: Path, channel: str):
    box = load_preset(channel)
    if box:
        return box, "preset"
    box = detect_facecam(video)
    if box:
        save_preset(channel, box, "auto")
        return box, "auto"
    return None, "none"


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.reframe <video.mp4> [channel]")
        sys.exit(1)
    video = Path(argv[1])
    if len(argv) > 2:
        box, src = preset_or_detect(video, argv[2])
    else:
        box, src = detect_facecam(video), "auto"
    print(f"facecam : {box} ({src})")


if __name__ == "__main__":
    main(sys.argv)
