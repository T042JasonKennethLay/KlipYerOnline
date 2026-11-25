"""Jump cut: buang jeda dan bagian diam di dalam clip supaya tempo cepat.

Jeda dicari dari timestamp per kata. Jeda yang berisi suara lebih keras dari omongan streamer
(teriakan, ledakan game yang tidak tertranskrip) atau berisi punchline tidak dipotong.
Semua waktu di sini relatif ke awal clip (detik).
"""
import subprocess
from pathlib import Path

import numpy as np

MIN_GAP = 0.5        # jeda lebih dari ini dipotong
PAD = 0.12           # napas yang disisakan sebelum dan sesudah kata
MIN_CUT = 0.25       # potongan lebih pendek dari ini tidak sepadan
LOUD_OVER = 2.0      # dB di atas level omongan = ada kejadian penting, jangan dipotong
HOP = 0.05           # resolusi analisis suara (detik)


def loudness_track(audio: Path, start: float, dur: float, sr: int = 16000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(audio),
                          "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = int(sr * HOP)
    frames = x[: len(x) // n * n].reshape(-1, n) if len(x) >= n else np.zeros((1, n))
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-6)


EVENT_PAD = 0.3      # detik yang disimpan di sekitar suara keras di dalam jeda


def quiet_parts(a: float, b: float, db: np.ndarray | None, speech: float | None) -> list[tuple[float, float]]:
    """Bagian jeda [a, b] yang boleh dipotong: semua kecuali sekitar suara yang lebih keras dari
    omongan (teriakan, ledakan, reaksi game). Jeda panjang berisi aksi jadi tinggal intinya."""
    if db is None or speech is None:
        return [(a, b)]
    loud = [i * HOP for i in range(int(a / HOP), min(int(b / HOP) + 1, len(db))) if db[i] > speech + LOUD_OVER]
    if not loud:
        return [(a, b)]
    keep, cur = [], [loud[0] - EVENT_PAD, loud[0] + EVENT_PAD]
    for t in loud[1:]:
        if t - EVENT_PAD <= cur[1]:
            cur[1] = t + EVENT_PAD
        else:
            keep.append(cur)
            cur = [t - EVENT_PAD, t + EVENT_PAD]
    keep.append(cur)
    out, t = [], a
    for ka, kb in keep:
        if ka - t >= MIN_CUT:
            out.append((t, ka))
        t = max(t, kb)
    if b - t >= MIN_CUT:
        out.append((t, b))
    return out


def plan_keep(words: list[dict], start: float, end: float, audio: Path | None = None,
              punch: float | None = None) -> list[tuple[float, float]]:
    """Return potongan yang DISIMPAN [(a, b)] relatif ke awal clip. Satu potongan = tanpa cut."""
    dur = end - start
    ws = sorted(((w["start"] - start, w["end"] - start) for w in words
                 if w["end"] > start and w["start"] < end), key=lambda w: w[0])
    if len(ws) < 2:
        return [(0.0, dur)]
    db = loudness_track(audio, start, dur) if audio else None
    speech = None
    if db is not None:
        idx = [i for a, b in ws for i in range(int(a / HOP), min(int(b / HOP) + 1, len(db)))]
        speech = float(np.median(db[idx])) if idx else None

    cuts = []
    for (_, prev_end), (nxt_start, _) in zip(ws, ws[1:]):
        if nxt_start - prev_end <= MIN_GAP:
            continue
        a, b = prev_end + PAD, nxt_start - PAD
        if b - a < MIN_CUT:
            continue
        if punch is not None and a <= punch - start <= b:
            continue
        cuts += quiet_parts(a, b, db, speech)

    keep, t = [], 0.0
    for a, b in cuts:
        keep.append((t, a))
        t = b
    keep.append((t, dur))
    return [(round(a, 3), round(b, 3)) for a, b in keep if b - a > 0.05]


def remap(t: float, keep: list[tuple[float, float]]) -> float:
    """Waktu di clip asli -> waktu di clip setelah dipotong."""
    out = 0.0
    for a, b in keep:
        if t < a:
            return out
        if t <= b:
            return out + t - a
        out += b - a
    return out


def total(keep: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in keep)


def select_expr(keep: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)


def remap_words(words: list[dict], start: float, keep: list[tuple[float, float]]) -> list[dict]:
    """Geser timestamp kata ke timeline baru (tetap dalam detik absolut supaya build_ass tidak berubah)."""
    return [{**w, "start": start + remap(w["start"] - start, keep), "end": start + remap(w["end"] - start, keep)}
            for w in words]
