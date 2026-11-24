import json
import sys

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

from src.ingest import download_audio, load_or_fetch_metadata
from src.paths import work_dir
from src.signals import heatmap_per_second, load_or_compute_loudness, loudness_spike

WEIGHTS = {"heatmap": 0.6, "audio": 0.4}
EDGE_SKIP = 60


def smooth(x: np.ndarray, win: int = 5) -> np.ndarray:
    return np.convolve(x, np.ones(win) / win, mode="same")


def zscore(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-9)


def detrend_heatmap(heat: np.ndarray, base: int = 900) -> np.ndarray:
    """Penonton paling banyak nonton bagian awal, jadi heatmap condong tinggi di depan.
    Kurangi baseline lokal 15 menit supaya yang tersisa benar-benar bagian yang menonjol."""
    baseline = median_filter(heat, size=base, mode="nearest")
    return np.maximum(heat - baseline, 0)


def combined_score(signals: dict[str, np.ndarray | None], weights: dict[str, float]) -> np.ndarray:
    available = {k: v for k, v in signals.items() if v is not None and len(v) and np.std(v) > 0}
    n = max(len(v) for v in available.values())
    total, used = np.zeros(n), 0.0
    for name, v in available.items():
        v = np.pad(np.asarray(v, dtype=float), (0, n - len(v)))
        total += weights[name] * zscore(smooth(v))
        used += weights[name]
    return total / max(used, 1e-9)


def top_moments(score: np.ndarray, k: int = 5, min_gap: int = 90) -> list[int]:
    s = score.copy()
    s[:EDGE_SKIP] = s[-EDGE_SKIP:] = s.min()
    peaks, _ = find_peaks(s, distance=min_gap)
    best = peaks[np.argsort(s[peaks])[::-1][:k]]
    return sorted(int(p) for p in best)


def build_signals(meta: dict) -> dict[str, np.ndarray | None]:
    audio = download_audio(meta["url"], meta["id"])
    loud = load_or_compute_loudness(audio)
    heat = None
    if meta["heatmap"]:
        heat = detrend_heatmap(heatmap_per_second(meta["heatmap"], meta["duration"]))
    return {"heatmap": heat, "audio": loudness_spike(loud)}


def find_candidates(meta: dict, k: int = 5) -> list[dict]:
    signals = build_signals(meta)
    score = combined_score(signals, WEIGHTS)
    peaks = top_moments(score, k=k)
    cands = [{"t": p, "score": round(float(score[p]), 3)} for p in peaks]
    out = work_dir(meta["id"]) / "candidates.json"
    out.write_text(json.dumps({"signals": [k for k, v in signals.items() if v is not None],
                               "candidates": cands}, indent=2))
    return cands


def fmt(s: int) -> str:
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.score <url> [k]")
        sys.exit(1)
    meta = load_or_fetch_metadata(argv[1])
    k = int(argv[2]) if len(argv) > 2 else 5
    cands = find_candidates(meta, k)
    print(f"sinyal    : {'heatmap + audio' if meta['heatmap'] else 'audio saja'}")
    print(f"top {k} kandidat:")
    for i, c in enumerate(sorted(cands, key=lambda c: -c["score"]), 1):
        print(f"  {i}. {fmt(c['t'])}  skor {c['score']:+.2f}  https://youtu.be/{meta['id']}?t={max(c['t'] - 15, 0)}")
    print(f"saved     : work/{meta['id']}/candidates.json")


if __name__ == "__main__":
    main(sys.argv)
