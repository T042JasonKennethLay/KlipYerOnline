"""Sinyal penonton: bagian video mana yang paling banyak ditonton / ditonton ulang.

KONTRAK (jangan ubah signature tanpa diskusi, dipakai oleh src/score.py):

    get_viewer_signal(meta: dict) -> ViewerSignal | None

- `meta` adalah hasil `src.ingest.fetch_metadata` (punya key id, url, duration, heatmap, ...).
- Return None kalau tidak ada data penonton sama sekali.
- `per_second` panjangnya `int(duration) + 1`, nilainya 0..1 (1 = paling ramai ditonton).
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class ViewerSignal:
    source: str               # "heatmap" | "analytics" | sumber lain
    per_second: np.ndarray    # float, panjang int(duration) + 1, nilai 0..1
    points: list[dict]        # data mentah [{"start", "end", "value"}] buat debug / plot


def get_viewer_signal(meta: dict) -> ViewerSignal | None:
    """Versi awal: heatmap publik "Most Replayed" dari yt-dlp. Silakan dikembangkan."""
    heatmap = meta.get("heatmap") or []
    if not heatmap:
        return None
    per_second = np.zeros(int(meta["duration"]) + 1)
    for h in heatmap:
        per_second[int(h["start_time"]):int(h["end_time"]) + 1] = h["value"]
    points = [{"start": h["start_time"], "end": h["end_time"], "value": h["value"]} for h in heatmap]
    return ViewerSignal(source="heatmap", per_second=per_second, points=points)
