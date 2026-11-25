"""Bedakan suara streamer dari suara lain (dialog game, cutscene, video yang ditonton, tamu).

Whisper mentranskrip semua suara. Tanpa ini LLM mengira dialog karakter game adalah omongan
streamer, lalu memilih cutscene biasa sebagai momen lucu. Caranya:
    1. Sidik suara (embedding 256 dimensi, WeSpeaker ResNet34 ONNX) untuk tiap segmen transkrip.
    2. Suara streamer = suara yang paling dominan sepanjang video (pusat yang dicari berulang).
    3. Segmen yang mirip pusat itu = "streamer", sisanya = "other".

    python -m src.speaker <video_id>     # tandai transkrip penuh dan tampilkan contoh
"""
import functools
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from src.paths import ROOT, work_dir

MODEL = ROOT / "models" / "wespeaker" / "voxceleb_resnet34_LM.onnx"
REPO, FILE = "Wespeaker/wespeaker-voxceleb-resnet34-LM", "voxceleb_resnet34_LM.onnx"
SR = 16000
MIN_SEG = 0.8          # segmen lebih pendek dari ini tidak dinilai (terlalu sedikit suara)
MAX_SEG = 8.0          # ambil maksimal 8 detik di tengah segmen
CHUNK = 600
THRESHOLD = 0.45       # kemiripan kosinus minimal ke suara streamer


@functools.cache
def session():
    import onnxruntime as ort

    if not MODEL.exists():
        from huggingface_hub import hf_hub_download
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        hf_hub_download(REPO, FILE, local_dir=str(MODEL.parent))
    return ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])


@functools.cache
def mel_banks(n_fft: int = 512, n_mels: int = 80, low: float = 20.0, high: float = SR / 2) -> np.ndarray:
    mel = lambda f: 1127.0 * np.log(1.0 + f / 700.0)                      # noqa: E731
    bins = np.arange(n_fft // 2) * SR / n_fft
    lo, hi = mel(low), mel(high)
    centers = np.linspace(lo, hi, n_mels + 2)
    m = mel(bins)
    banks = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        l, c, r = centers[i], centers[i + 1], centers[i + 2]
        up = (m - l) / (c - l)
        down = (r - m) / (r - c)
        banks[i, :-1] = np.maximum(0, np.minimum(up, down))
    return banks


def fbank(wav: np.ndarray) -> np.ndarray:
    """Fbank 80 dimensi gaya Kaldi (25 ms, geser 10 ms, jendela povey), lalu dikurangi rata-ratanya."""
    x = wav * 32768.0
    flen, shift, n_fft = 400, 160, 512
    if len(x) < flen:
        return np.zeros((0, 80), dtype=np.float32)
    n = 1 + (len(x) - flen) // shift
    idx = np.arange(flen)[None, :] + shift * np.arange(n)[:, None]
    fr = x[idx].astype(np.float32)
    fr -= fr.mean(axis=1, keepdims=True)
    fr = np.concatenate([fr[:, :1] - 0.97 * fr[:, :1], fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(flen) / (flen - 1))) ** 0.85
    spec = np.abs(np.fft.rfft(fr * win, n=n_fft)) ** 2
    feats = np.log(np.maximum(spec @ mel_banks().T, 1.19e-7)).astype(np.float32)
    return feats - feats.mean(axis=0, keepdims=True)


def load_pcm(audio: Path, start: float, dur: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(audio),
                          "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def embed(wav: np.ndarray) -> np.ndarray | None:
    feats = fbank(wav)
    if len(feats) < 50:
        return None
    e = session().run(None, {"feats": feats[None]})[0][0]
    return e / (np.linalg.norm(e) + 1e-9)


def segment_embeddings(video_id: str, audio: Path, segs: list[dict], log=print) -> np.ndarray:
    """Embedding per segmen (baris nol = tidak dinilai). Di-cache di work/<id>/speaker_emb.npy."""
    cache = work_dir(video_id) / "speaker_emb.npy"
    if cache.exists():
        arr = np.load(cache)
        if len(arr) == len(segs):
            return arr
    out = np.zeros((len(segs), 256), dtype=np.float32)
    by_chunk: dict[int, list[int]] = {}
    for i, s in enumerate(segs):
        if s["end"] - s["start"] >= MIN_SEG:
            by_chunk.setdefault(int(s["start"] // CHUNK), []).append(i)
    parts = work_dir(video_id) / "speaker_parts"      # per bagian, supaya bisa lanjut kalau terputus
    parts.mkdir(exist_ok=True)
    for n, (c, ids) in enumerate(sorted(by_chunk.items()), 1):
        part = parts / f"{c}_{len(ids)}.npy"
        if part.exists():
            out[ids] = np.load(part)
            continue
        base = c * CHUNK
        wav = load_pcm(audio, base, CHUNK + 60)
        for i in ids:
            s = segs[i]
            a, b = s["start"], s["end"]
            if b - a > MAX_SEG:
                mid = (a + b) / 2
                a, b = mid - MAX_SEG / 2, mid + MAX_SEG / 2
            e = embed(wav[int((a - base) * SR): int((b - base) * SR)])
            if e is not None:
                out[i] = e
        np.save(part, out[ids])
        if n % 6 == 0 or n == len(by_chunk):
            log(f"  sidik suara {n}/{len(by_chunk)} bagian")
    np.save(cache, out)
    return out


SEED = re.compile(r"\bchat\b", re.I)    # streamer terus menyapa chat; karakter game tidak


def streamer_centroid(emb: np.ndarray, segs: list[dict], rounds: int = 3) -> tuple[np.ndarray, float]:
    """Pusat suara streamer + ambang kemiripan.

    Patokan awal: segmen yang menyebut "chat" (hampir pasti streamer). Kalau terlalu sedikit, pakai
    suara yang paling dominan. Lalu diperhalus beberapa kali dengan segmen yang paling mirip."""
    ok = np.linalg.norm(emb, axis=1) > 0
    seeds = [i for i, s in enumerate(segs) if ok[i] and SEED.search(s.get("text", ""))]
    if len(seeds) >= 15:
        c = emb[seeds].mean(axis=0)
    else:
        c = emb[ok].mean(axis=0)
    for _ in range(rounds):
        c /= np.linalg.norm(c) + 1e-9
        sim = emb @ c
        ref = sim[seeds] if len(seeds) >= 15 else sim[ok]
        cut = np.quantile(ref, 0.5)
        c = emb[ok & (sim >= cut)].mean(axis=0)
    c /= np.linalg.norm(c) + 1e-9
    sim = emb @ c
    ref = sim[seeds] if len(seeds) >= 15 else sim[ok]
    thr = float(min(THRESHOLD, np.quantile(ref, 0.1)))    # 90% segmen "chat" dianggap streamer
    return c, thr


LOUD_DB = 6.0          # lonjakan suara (dB di atas sekitarnya) yang dianggap teriakan atau reaksi keras


def loud_spike(video_id: str) -> np.ndarray | None:
    p = work_dir(video_id) / "loudness.npy"
    if not p.exists():
        return None
    from src.signals import loudness_spike
    return loudness_spike(np.load(p))


def is_loud(spike: np.ndarray | None, s: dict) -> bool:
    if spike is None:
        return False
    a, b = int(s["start"]), max(int(s["end"]), int(s["start"]) + 1)
    return a < len(spike) and float(spike[a:b].max()) >= LOUD_DB


def label_segments(video_id: str, audio: Path, segs: list[dict], log=print) -> list[dict]:
    """Tambahkan "speaker": "streamer" | "other" | None (terlalu pendek untuk dinilai) dan "spk_sim"."""
    emb = segment_embeddings(video_id, audio, segs, log)
    c, thr = streamer_centroid(emb, segs)
    sims = emb @ c
    spike = loud_spike(video_id)
    out = []
    for s, e, sim in zip(segs, emb, sims):
        if not e.any():
            label = None
        elif sim >= thr or SEED.search(s.get("text", "")):
            label = "streamer"
        elif is_loud(spike, s):
            label = None          # teriakan mengubah warna suara: jangan dicap suara lain, biarkan tidak yakin
        else:
            label = "other"
        out.append({**s, "speaker": label, "spk_sim": round(float(sim), 3) if e.any() else None})
    n = sum(1 for s in out if s["speaker"] == "other")
    m = sum(1 for s in out if s["speaker"] is not None)
    log(f"  suara lain (game, cutscene, orang lain): {n} dari {m} segmen")
    return out


def main(argv: list[str]) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    from src.ingest import find_audio, load_or_fetch_metadata
    from src.scan import transcribe_full

    vid = argv[1]
    meta = json.loads((work_dir(vid) / "meta.json").read_text(encoding="utf-8")) if (work_dir(vid) / "meta.json").exists() \
        else load_or_fetch_metadata(f"https://youtu.be/{vid}")
    audio = find_audio(vid)
    segs = label_segments(vid, audio, transcribe_full(vid, audio, meta["duration"], log=lambda *a: None))
    for s in segs[:: max(1, len(segs) // 40)]:
        print(f"  {s['start']:>8.1f} {str(s['speaker']):<9} {s['spk_sim']}  {s['text'][:70]}")


if __name__ == "__main__":
    main(sys.argv)
