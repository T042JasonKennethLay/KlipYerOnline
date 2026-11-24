import subprocess
from pathlib import Path

import numpy as np

SR = 16000


def heatmap_per_second(heatmap: list[dict], duration: float) -> np.ndarray:
    arr = np.zeros(int(duration) + 1)
    for h in heatmap:
        arr[int(h["start_time"]):int(h["end_time"]) + 1] = h["value"]
    return arr


def loudness_per_second(audio_path: Path, sr: int = SR) -> np.ndarray:
    """RMS dalam dB per detik, dibaca streaming lewat ffmpeg supaya hemat RAM."""
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(audio_path), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out = []
    chunk = sr * 2
    while True:
        buf = proc.stdout.read(chunk)
        if not buf:
            break
        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768
        out.append(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))
    proc.wait()
    return np.array(out)


def loudness_spike(loud_db: np.ndarray, floor: float = -60.0, short: int = 5, base: int = 300,
                   silence_db: float = -50.0, margin: float = 6.0) -> np.ndarray:
    """Seberapa keras detik ini dibanding `base` detik di sekitarnya (dB di atas median lokal).

    Stream gaming hampir selalu keras, jadi yang dicari lonjakan relatif, bukan volume absolut.
    Detik hening (break, mute) tidak ikut menghitung baseline. Kalau ikut, baseline jadi rendah
    dan obrolan biasa setelah hening terlihat seperti lonjakan besar.
    """
    from scipy.ndimage import median_filter, uniform_filter1d

    x = np.maximum(loud_db, floor)
    voiced = x > silence_db
    ref = float(np.median(x[voiced])) if voiced.any() else float(np.median(x))
    filled = np.where(voiced, x, ref)
    short_avg = uniform_filter1d(x, size=short, mode="nearest")
    baseline = np.maximum(median_filter(filled, size=base, mode="nearest"), ref - margin)
    return np.maximum(short_avg - baseline, 0)


def load_or_compute_loudness(audio_path: Path) -> np.ndarray:
    cache = audio_path.with_name("loudness.npy")
    if cache.exists():
        return np.load(cache)
    loud = loudness_per_second(audio_path)
    np.save(cache, loud)
    return loud
