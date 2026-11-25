"""Jump cut: buang jeda dan bagian diam di dalam clip supaya tempo cepat, tapi tetap enak ditonton.

Aturan supaya cut tidak terasa acak:
- hanya jeda yang benar-benar kosong (lebih dari MIN_GAP) yang dipotong, dengan napas PAD;
- di dalam jeda yang ada suara keras (teriakan, aksi game) hanya bagian sepi yang panjang dipotong;
- potongan yang disimpan minimal MIN_SEG detik, potongan kecil digabung (tidak ada kedipan);
- dari sedikit sebelum punchline sampai akhir clip tidak pernah dipotong (reaksi dan ending utuh);
- jumlah cut dibatasi, yang dipilih jeda paling panjang.
Saat render, tiap potongan bergantian sedikit zoom (punch-in) dan audio diberi fade pendek, jadi cut
terlihat disengaja dan tidak ada bunyi klik. Semua waktu di sini relatif ke awal clip (detik).
"""
import subprocess
from pathlib import Path

import numpy as np

MIN_GAP = 0.8        # jeda lebih dari ini dipotong
PAD = 0.2            # napas yang disisakan sebelum dan sesudah kata
MIN_CUT = 0.4        # potongan lebih pendek dari ini tidak sepadan
QUIET_MIN = 1.0      # di jeda yang ada suara keras, bagian sepi minimal segini baru dipotong
MIN_SEG = 1.2        # potongan yang disimpan minimal segini, kalau kurang digabung
END_GUARD = 1.0      # mulai (punchline - 1 s) sampai akhir clip tidak dipotong
CUTS_PER_SEC = 1 / 5  # paling banyak satu cut per 5 detik clip
LOUD_OVER = 2.0      # dB di atas level omongan = ada kejadian penting
EVENT_PAD = 0.3      # detik yang disimpan di sekitar suara keras di dalam jeda
HOP = 0.05           # resolusi analisis suara (detik)
FADE = 0.02          # fade audio di tiap sambungan supaya tidak klik


def loudness_track(audio: Path, start: float, dur: float, sr: int = 16000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(start, 0):.3f}", "-t", f"{dur:.3f}", "-i", str(audio),
                          "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = int(sr * HOP)
    frames = x[: len(x) // n * n].reshape(-1, n) if len(x) >= n else np.zeros((1, n))
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-6)


def speech_level(db: np.ndarray, ws: list[tuple[float, float]]) -> float | None:
    idx = [i for a, b in ws for i in range(int(a / HOP), min(int(b / HOP) + 1, len(db)))]
    return float(np.median(db[idx])) if idx else None


def quiet_parts(a: float, b: float, db: np.ndarray | None, speech: float | None) -> list[tuple[float, float]]:
    """Bagian jeda [a, b] yang boleh dipotong. Jeda tanpa suara keras dipotong utuh; jeda berisi aksi
    hanya dipotong di bagian sepi yang panjang (QUIET_MIN), sekitar suara keras tetap disimpan."""
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
        if ka - t >= QUIET_MIN:
            out.append((t, ka))
        t = max(t, kb)
    if b - t >= QUIET_MIN:
        out.append((t, b))
    return out


def to_keep(cuts: list[tuple[float, float]], dur: float) -> list[tuple[float, float]]:
    keep, t = [], 0.0
    for a, b in sorted(cuts):
        keep.append((t, a))
        t = b
    keep.append((t, dur))
    return keep


def merge_short(cuts: list[tuple[float, float]], dur: float) -> list[tuple[float, float]]:
    """Buang cut yang membuat potongan tersimpan lebih pendek dari MIN_SEG (pilih cut yang lebih kecil)."""
    cuts = sorted(cuts)
    while cuts:
        keep = to_keep(cuts, dur)
        short = [i for i, (a, b) in enumerate(keep) if b - a < MIN_SEG]
        if not short:
            break
        i = short[0]
        left = i - 1 if i > 0 else None             # cut sebelum potongan i
        right = i if i < len(cuts) else None         # cut sesudah potongan i
        options = [j for j in (left, right) if j is not None]
        j = min(options, key=lambda k: cuts[k][1] - cuts[k][0])
        cuts.pop(j)
    return cuts


def plan_keep(words: list[dict], start: float, end: float, audio: Path | None = None,
              punch: float | None = None) -> list[tuple[float, float]]:
    """Return potongan yang DISIMPAN [(a, b)] relatif ke awal clip. Satu potongan = tanpa cut."""
    dur = end - start
    ws = sorted(((w["start"] - start, w["end"] - start) for w in words
                 if w["end"] > start and w["start"] < end), key=lambda w: w[0])
    if len(ws) < 2:
        return [(0.0, dur)]
    db = loudness_track(audio, start, dur) if audio else None
    speech = speech_level(db, ws) if db is not None else None
    guard = (punch - start - END_GUARD) if punch is not None else dur - 3.0

    cuts = []
    for (_, prev_end), (nxt_start, _) in zip(ws, ws[1:]):
        if nxt_start - prev_end <= MIN_GAP:
            continue
        a, b = prev_end + PAD, min(nxt_start - PAD, guard)
        if b - a < MIN_CUT:
            continue
        cuts += [(x, y) for x, y in quiet_parts(a, b, db, speech) if y - x >= MIN_CUT]

    limit = max(1, int(dur * CUTS_PER_SEC))
    cuts = sorted(cuts, key=lambda c: c[0] - c[1])[:limit]     # simpan jeda paling panjang
    cuts = merge_short(cuts, dur)
    return [(round(a, 3), round(b, 3)) for a, b in to_keep(cuts, dur) if b - a > 0.05]


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


def new_segments(keep: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Batas tiap potongan di timeline baru (untuk zoom bergantian)."""
    out, t = [], 0.0
    for a, b in keep:
        out.append((t, t + b - a))
        t += b - a
    return out


def audio_cut_filter(label: str, keep: list[tuple[float, float]], out: str) -> str:
    """Potong audio per segmen dengan fade pendek di sambungan, lalu sambung (tidak ada bunyi klik)."""
    n = len(keep)
    parts = [f"[{label}]asplit={n}" + "".join(f"[ac{i}]" for i in range(n))]
    for i, (a, b) in enumerate(keep):
        d = b - a
        fi = f",afade=t=in:d={FADE}" if i > 0 else ""
        fo = f",afade=t=out:st={max(d - FADE, 0):.3f}:d={FADE}" if i < n - 1 else ""
        parts.append(f"[ac{i}]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS{fi}{fo}[as{i}]")
    parts.append("".join(f"[as{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[{out}]")
    return ";".join(parts)


def remap_words(words: list[dict], start: float, keep: list[tuple[float, float]]) -> list[dict]:
    """Geser timestamp kata ke timeline baru (tetap dalam detik absolut supaya build_ass tidak berubah)."""
    return [{**w, "start": start + remap(w["start"] - start, keep), "end": start + remap(w["end"] - start, keep)}
            for w in words]


def extend_end(audio: Path, start: float, end: float, max_ext: float = 2.5, tail: float = 0.6) -> float:
    """Jangan potong reaksi: setelah kata terakhir, lanjutkan selama suara masih seramai omongan
    (tawa, teriakan) sampai max_ext detik, lalu sisakan `tail` detik."""
    look = 3.0
    db = loudness_track(audio, end - look, look + max_ext)
    ref = float(np.percentile(db[: int(look / HOP)], 60)) if len(db) > int(look / HOP) else None
    if ref is None:
        return end + tail
    after = db[int(look / HOP):]
    quiet_run, ext = 0, 0.0
    for i, v in enumerate(after):
        if v < ref - 8:
            quiet_run += 1
            if quiet_run * HOP >= 0.4:
                ext = max(0.0, (i - quiet_run + 1) * HOP)
                break
        else:
            quiet_run = 0
            ext = (i + 1) * HOP
    return round(end + min(ext, max_ext) + tail, 2)
