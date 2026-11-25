"""Cari momen dari SELURUH video, bukan hanya dari puncak suara.

Puncak suara hanya menangkap momen yang keras. Banyak momen bagus (roast datar, jawaban lucu,
cerita singkat) tidak keras sama sekali. Jadi:
    1. Transkrip seluruh audio (GPU, di-cache per 10 menit).
    2. LLM membaca transkrip per bagian 30 menit. Baris yang keras dan puncak sinyal ditandai
       sebagai petunjuk, lalu LLM mengusulkan momen terbaik di bagian itu.
    3. Usulan + puncak sinyal digabung jadi kandidat untuk refine (yang membandingkan semuanya).

    python -m src.scan <url>
"""
import hashlib
import json
import sys

import numpy as np

from src.ingest import download_audio, load_or_fetch_metadata
from src.paths import work_dir
from src.refine import ask_json
from src.signals import load_or_compute_loudness, loudness_spike
from src.transcribe import cut_audio, transcribe_window

CHUNK = 600            # detik per potongan transkrip
SECTION = 1800         # detik per bagian yang dibaca LLM sekaligus
OVERLAP = 60           # bagian saling tumpang 1 menit supaya momen di perbatasan tidak hilang
PER_SECTION = 5        # usulan maksimal per bagian
LOUD_DB = 6.0          # dB di atas sekitarnya = ditandai [LOUD]
CONTEXT = 25           # detik transkrip tambahan di kiri-kanan usulan untuk refine

SYSTEM = """You scout livestream and video transcripts for moments that would work as vertical
short clips (TikTok, YouTube Shorts). You read one section of the transcript at a time.

A great moment is self-contained: a stranger understands it without earlier context and gets a
payoff within seconds. Look for jokes, roasts, rage, fails, surprising or quotable lines, hype
reactions, funny interactions with chat or other people, and short stories with a punchline.
Quiet delivery can still be very funny, so do not rely only on [LOUD] marks; they are hints.
Skip sponsor reads, ads, idle chatter, reading donations or names, menus and loading, and
anything that needs earlier context.

For each moment give start (the setup line that hooks the viewer), end (right after the payoff and
reaction), score 0 to 10 (how likely a stranger watches to the end), and a short reason. Moments
are usually 10 to 45 seconds. Return fewer moments if the section is weak; return none if nothing
is good. Use only times that appear in the transcript."""

SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["moments"],
    "additionalProperties": False,
}


def transcribe_full(video_id: str, audio, duration: float, log=print) -> list[dict]:
    segs = []
    for start in range(0, int(duration) + 1, CHUNK):
        cache = work_dir(video_id) / f"full_{start}_{CHUNK}.json"
        if cache.exists():
            part = json.loads(cache.read_text(encoding="utf-8"))
        else:
            log(f"  transkrip {start // 60}-{min(start + CHUNK, int(duration)) // 60} menit")
            win = cut_audio(audio, start, start + CHUNK, work_dir(video_id) / "win.wav")
            part = transcribe_window(win, offset=start)
            cache.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
        segs += part
    return segs


def annotate(segs: list[dict], spike: np.ndarray) -> str:
    lines = []
    for s in segs:
        a, b = int(s["start"]), max(int(s["end"]), int(s["start"]) + 1)
        loud = spike[a:b].max() >= LOUD_DB if a < len(spike) else False
        lines.append(f"[{s['start']:.1f}] {s['text'].strip()}" + (" [LOUD]" if loud else ""))
    return "\n".join(lines)


def sections(duration: float):
    t = 0
    while t < duration:
        yield t, min(t + SECTION, duration)
        t += SECTION - OVERLAP


def scan(meta: dict, segs: list[dict], hints: list[int], log=print) -> list[dict]:
    """Return usulan momen [{"start", "end", "score", "reason"}] dari seluruh video."""
    vid = meta["id"]
    spike = loudness_spike(load_or_compute_loudness(download_audio(meta["url"], vid)))
    found = []
    for a, b in sections(meta["duration"]):
        part = [s for s in segs if a <= s["start"] < b]
        if len(part) < 5:
            continue
        marks = [h for h in hints if a <= h < b]
        prompt = (f"Video: {meta['title']} by {meta['channel']}\n"
                  f"Section {a // 60:.0f} to {b // 60:.0f} minutes. Times are absolute seconds.\n"
                  + (f"Signal peaks (audience replays or loud audio) at seconds: {marks}\n" if marks else "")
                  + f"\n<transcript>\n{annotate(part, spike)}\n</transcript>\n\n"
                  f"Return at most {PER_SECTION} moments.")
        key = hashlib.sha1(prompt.encode()).hexdigest()[:10]
        answer, name = ask_json(SYSTEM, prompt, SCHEMA, work_dir(vid) / f"scan_{int(a)}_{key}.json")
        if answer is None:
            log(f"  scan {a // 60:.0f}-{b // 60:.0f} menit: LLM gagal, bagian ini dilewati")
            continue
        good = [m for m in answer["moments"] if a - 5 <= m["start"] < m["end"] <= b + 5]
        log(f"  scan {a // 60:.0f}-{b // 60:.0f} menit ({name}): {len(good)} momen")
        found += good
    return found


def build_candidates(segs: list[dict], moments: list[dict], peaks: list[dict],
                     max_cands: int = 20) -> list[dict]:
    """Gabungkan usulan LLM dan puncak sinyal jadi kandidat refine, tanpa duplikat."""
    items = [{"t": round((m["start"] + m["end"]) / 2), "a": m["start"], "b": m["end"],
              "score": float(m["score"]), "src": "scan"} for m in moments]
    items.sort(key=lambda c: -c["score"])
    for p in peaks:
        if all(not (c["a"] - 10 <= p["t"] <= c["b"] + 10) for c in items):
            items.append({"t": p["t"], "a": p["t"] - 20, "b": p["t"] + 10, "score": float(p["score"]),
                          "src": "sinyal"})
    cands, taken = [], []
    for c in items:
        if any(min(c["b"], b) - max(c["a"], a) > 0.5 * (c["b"] - c["a"]) for a, b in taken):
            continue
        part = [s for s in segs if s["end"] > c["a"] - CONTEXT and s["start"] < c["b"] + CONTEXT]
        if not part:
            continue
        taken.append((c["a"], c["b"]))
        cands.append({"t": c["t"], "score": c["score"], "src": c["src"], "segments": part})
        if len(cands) >= max_cands:
            break
    return cands


def main(argv: list[str]) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    if len(argv) < 2:
        print("usage: python -m src.scan <url>")
        sys.exit(1)
    meta = load_or_fetch_metadata(argv[1])
    audio = download_audio(meta["url"], meta["id"])
    segs = transcribe_full(meta["id"], audio, meta["duration"])
    moments = scan(meta, segs, [])
    for m in sorted(moments, key=lambda m: -m["score"]):
        print(f"  {m['start']:>8.1f}-{m['end']:<8.1f} skor {m['score']}  {m['reason']}")


if __name__ == "__main__":
    main(sys.argv)
