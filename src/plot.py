import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.ingest import download_audio, load_or_fetch_metadata
from src.paths import work_dir
from src.signals import heatmap_per_second, load_or_compute_loudness, loudness_spike

EDGE_SKIP = 60


def smooth(x: np.ndarray, win: int) -> np.ndarray:
    return np.convolve(x, np.ones(win) / win, mode="same")


def pick_peaks(x: np.ndarray, k: int = 5, gap: int = 120) -> list[int]:
    order = np.argsort(x)[::-1]
    picked: list[int] = []
    for s in order:
        if s < EDGE_SKIP or s > len(x) - EDGE_SKIP:
            continue
        if all(abs(s - p) > gap for p in picked):
            picked.append(int(s))
        if len(picked) == k:
            break
    return sorted(picked)


def plot_signals(video_id: str, loud: np.ndarray, spike: np.ndarray, heat: np.ndarray | None, title: str):
    t = np.arange(len(loud)) / 60
    rows = 3 if heat is not None else 2
    fig, axes = plt.subplots(rows, 1, figsize=(16, 2.8 * rows), sharex=True)
    ax = axes[0]
    ax.plot(t, loud, color="#c9c9c9", lw=0.4, label="per detik")
    ax.plot(t, smooth(loud, 15), color="#3b6fb6", lw=1.0, label="rata-rata 15 detik")
    ax.set_ylabel("loudness (dB)")
    ax.set_ylim(-70, loud.max() + 3)
    ax.legend(loc="lower right", fontsize=8)
    ax = axes[1]
    ax.plot(t, spike, color="#c0504d", lw=0.7)
    ax.set_ylabel("lonjakan (dB)")
    if heat is not None:
        ax = axes[2]
        th = np.arange(len(heat)) / 60
        ax.fill_between(th, heat, color="#e8a33d", alpha=0.6)
        ax.set_ylabel("heatmap")
    axes[-1].set_xlabel("menit")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    out = work_dir(video_id) / "signals.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def fmt(s: int) -> str:
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.plot <url>")
        sys.exit(1)
    meta = load_or_fetch_metadata(argv[1])
    audio = download_audio(meta["url"], meta["id"])
    loud = load_or_compute_loudness(audio)
    spike = loudness_spike(loud)
    heat = heatmap_per_second(meta["heatmap"], meta["duration"]) if meta["heatmap"] else None
    out = plot_signals(meta["id"], loud, spike, heat, meta["title"])
    print(f"loudness  : {len(loud)} detik")
    peaks = pick_peaks(spike)
    print("puncak lonjakan loudness:")
    for s in peaks:
        print(f"  {fmt(s)}  +{spike[s]:.1f} dB  https://youtu.be/{meta['id']}?t={s}")
    if heat is not None:
        print("puncak heatmap:")
        for s in pick_peaks(heat, k=3, gap=300):
            print(f"  {fmt(s)}  {heat[s]:.2f}  https://youtu.be/{meta['id']}?t={s}")
    (work_dir(meta["id"]) / "loudness_peaks.json").write_text(json.dumps(peaks))
    print(f"saved     : work/{meta['id']}/signals.png")


if __name__ == "__main__":
    main(sys.argv)
