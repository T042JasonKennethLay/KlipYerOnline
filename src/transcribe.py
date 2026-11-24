import functools
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import numpy as np

from src.paths import ROOT, work_dir

MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
LOCAL_MODEL = ROOT / "models" / f"faster-whisper-{MODEL}"


def _add_cuda_dlls() -> None:
    """Di Windows, DLL cuBLAS/cuDNN dari paket pip nvidia-* harus didaftarkan manual."""
    if os.name != "nt":
        return
    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    for sub in ("cublas", "cudnn"):
        d = nvidia / sub / "bin"
        if d.exists():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]


@functools.cache
def load_model():
    _add_cuda_dlls()
    from faster_whisper import WhisperModel

    model = str(LOCAL_MODEL) if (LOCAL_MODEL / "model.bin").exists() else MODEL
    try:
        return WhisperModel(model, device="cuda", compute_type="int8_float16")
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe] GPU gagal ({e}), pakai CPU model small")
        return WhisperModel("small", device="cpu", compute_type="int8")


def cut_audio(src: Path, start: float, end: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-to", str(end), "-i", str(src),
                    "-ac", "1", "-ar", "16000", str(out)], check=True)
    return out


def load_pcm(audio: Path, sr: int = 16000) -> np.ndarray:
    """Decode audio pakai ffmpeg jadi float32 mono 16 kHz (tidak bergantung ke PyAV)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def transcribe_window(audio: Path, offset: float) -> list[dict]:
    """Transkrip satu window audio. Semua timestamp digeser ke waktu absolut video."""
    segments, _ = load_model().transcribe(load_pcm(audio), word_timestamps=True, vad_filter=True,
                                          condition_on_previous_text=False)
    out = []
    for s in segments:
        out.append({
            "start": round(s.start + offset, 2),
            "end": round(s.end + offset, 2),
            "text": s.text.strip(),
            "words": [{"word": w.word.strip(), "start": round(w.start + offset, 2),
                       "end": round(w.end + offset, 2), "prob": round(w.probability, 2)}
                      for w in (s.words or [])],
        })
    return out


def transcribe_candidate(video_id: str, audio: Path, t: int, pad: int = 60) -> list[dict]:
    cache = work_dir(video_id) / f"transcript_{t}_{pad}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    start = max(t - pad, 0)
    win = cut_audio(audio, start, t + pad, work_dir(video_id) / "win.wav")
    segs = transcribe_window(win, offset=start)
    cache.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
    return segs


def main(argv: list[str]) -> None:
    import time

    from src.ingest import find_audio

    if len(argv) < 3:
        print("usage: python -m src.transcribe <video_id> <detik>")
        sys.exit(1)
    video_id, t = argv[1], int(argv[2])
    t0 = time.time()
    segs = transcribe_candidate(video_id, find_audio(video_id), t)
    words = [w for s in segs for w in s["words"]]
    print(f"waktu     : {time.time() - t0:.1f} s")
    print(f"segmen    : {len(segs)}, kata: {len(words)}")
    for w in words[:20]:
        print(f"  {w['start']:>9.2f} - {w['end']:>9.2f}  {w['word']}")


if __name__ == "__main__":
    main(sys.argv)
