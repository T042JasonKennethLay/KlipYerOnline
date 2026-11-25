"""Satu perintah: link video -> beberapa clip 9:16 dengan caption.

    python -m src.pipeline "<url>" --top 3
    python -m src.pipeline "<url>" --top 3 --quick    # hanya puncak sinyal, lebih cepat

Video tidak diunduh: ffmpeg membaca potongan langsung dari stream YouTube (HLS) dan audio dari
file audio lokal. Semua tahap pakai cache di work/<id>/, jadi kalau ada yang gagal tinggal jalankan ulang.
"""
import argparse
import json
import subprocess
import time
import warnings

from src.boundaries import words_in
from src.captions import build_ass
from src.ingest import (StreamSource, download_audio, download_section, grab_probe, load_or_fetch_metadata,
                        stream_source)
from src.paths import out_dir, work_dir
from src.reframe import preset_or_detect
from src.refine import providers, refine
from src.render import render_vertical
from src.scan import build_candidates, scan, transcribe_full
from src.score import find_candidates
from src.transcribe import transcribe_candidate

MIN_WORDS_PER_SEC = 0.25         # kata/detik di sekitar puncak; di bawah ini = momen hening (butuh VLM, belum ada)
CAPTION_Y = {"cam": 790, "center": 1180}
TITLE_Y = {"cam": 60, "center": 260}
STREAM_TRIES = 3


def fmt(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def peak_candidates(meta: dict, audio, pool: int) -> list[dict]:
    """Mode cepat: hanya puncak sinyal, transkrip 2 menit di sekitar masing-masing."""
    cands = sorted(find_candidates(meta, k=pool), key=lambda c: -c["score"])
    log(f"{len(cands)} kandidat dari sinyal, transkrip satu per satu")
    voiced = []
    for c in cands:
        segs = transcribe_candidate(meta["id"], audio, c["t"])
        n = len(words_in(segs, c["t"] - 30, c["t"] + 30))
        status = "ok" if n / 60 >= MIN_WORDS_PER_SEC else "hening"
        log(f"  {fmt(c['t'])} skor {c['score']:+.2f} ({n} kata di sekitar puncak) {status}")
        if status == "ok":
            voiced.append({**c, "segments": segs})
    return voiced


def scan_candidates(meta: dict, audio, pool: int) -> list[dict]:
    """Mode penuh: transkrip seluruh video, LLM membaca semuanya, puncak sinyal jadi petunjuk."""
    log("transkrip seluruh video")
    segs = transcribe_full(meta["id"], audio, meta["duration"], log)
    peaks = find_candidates(meta, k=pool)
    moments = scan(meta, segs, [p["t"] for p in peaks], log)
    if not moments:
        return []
    cands = build_candidates(segs, moments, peaks)
    n_scan = sum(c["src"] == "scan" for c in cands)
    log(f"{len(cands)} kandidat ({n_scan} dari scan LLM, {len(cands) - n_scan} dari sinyal)")
    return cands


def plan_clips(meta: dict, top: int, pool: int | None = None, quick: bool = False) -> list[dict]:
    """Kumpulkan kandidat (scan penuh kalau ada LLM, kalau tidak puncak sinyal), lalu refine."""
    audio = download_audio(meta["url"], meta["id"])
    pool = pool or top * 3
    cands = [] if quick or not providers() else scan_candidates(meta, audio, pool)
    if not cands:
        cands = peak_candidates(meta, audio, pool)
    clips, mode = refine(meta["id"], cands, context=f"Video: {meta['title']} by {meta['channel']}")
    log(f"refine ({mode}): {len(clips)} dari {len(cands)} kandidat layak")
    plans = []
    for c in clips[:top]:
        words = words_in(c["segments"], c["start"], c["end"])
        text = " ".join(w["word"] for w in words)
        log(f"  {fmt(c['start'])}-{fmt(c['end'])} ({c['end'] - c['start']:.0f}s) {c['title']!r} {c['reason']}")
        plans.append({k: v for k, v in c.items() if k != "segments"} | {"words": words, "text": text})
    return plans


def facecam(meta: dict, src, s: float, cam_cache: dict):
    """Deteksi sekali per video dari potongan 20 detik. Preset channel dipakai kalau wajahnya cocok."""
    if "box" not in cam_cache:
        if isinstance(src, StreamSource):
            probe = grab_probe(src, s, work_dir(meta["id"]) / f"probe_{int(s)}.mp4")
        else:
            probe = src
        cam_cache["box"], cam_cache["src"] = preset_or_detect(probe, meta["channel"])
        log(f"facecam: {cam_cache['box']} ({cam_cache['src']})")
    return cam_cache["box"]


def render_clip(meta: dict, plan: dict, idx: int, cam_cache: dict, audio, effects: str = "all") -> dict:
    """effects: "all" (SFX + zoom + lagu), "sfx" (tanpa lagu), atau "none"."""
    vid = meta["id"]
    s, e = plan["start"], plan["end"]
    out = out_dir(vid) / f"clip_{idx:02d}_{int(s)}.mp4"
    cap = work_dir(vid) / f"cap_{int(s * 100)}.ass"

    def render(src, offset: float) -> None:
        box = facecam(meta, src, s, cam_cache)
        layout = "cam" if box else "center"
        build_ass(plan["words"], s, e, cap, pos=(540, CAPTION_Y[layout]), title=plan.get("title", ""),
                  title_y=TITLE_Y[layout])
        punch = plan.get("punchline")
        fx = None if effects == "none" else {
            "punch": punch - s if punch is not None and s <= punch <= e else None,
            "seed": int(s), "music": effects == "all"}
        if isinstance(src, StreamSource):
            render_vertical(src, out, cap, box, s, e, fx=fx)
        else:
            render_vertical(src, out, cap, box, fx=fx)

    for attempt in range(STREAM_TRIES):
        try:
            render(stream_source(meta["url"], audio, refresh=attempt > 0), s)
            how = "stream"
            break
        except subprocess.CalledProcessError:
            log(f"  stream gagal (percobaan {attempt + 1}/{STREAM_TRIES}), ambil link baru")
    else:
        log("  fallback: download potongan dulu")
        render(download_section(meta["url"], vid, s, e, f"raw_{int(s * 100)}_{int(e * 100)}"), 0)
        how = "download"
    layout = "cam" if cam_cache.get("box") else "center"
    return {"file": str(out.name), "start": s, "end": e, "duration": round(e - s, 2), "score": plan["score"],
            "layout": layout, "title": plan["title"], "punchline": plan["punchline"], "reason": plan["reason"],
            "source": how, "link": f"https://youtu.be/{vid}?t={int(s)}", "text": plan["text"]}


def run(url: str, top: int = 3, pool: int | None = None, effects: str = "all",
        quick: bool = False) -> list[dict]:
    t0 = time.time()
    meta = load_or_fetch_metadata(url)
    log(f"{meta['title']} ({meta['channel']}, {fmt(meta['duration'])})")
    plans = plan_clips(meta, top, pool, quick)
    audio = download_audio(meta["url"], meta["id"])
    cam_cache: dict = {}
    clips = []
    for i, p in enumerate(plans, 1):
        t = time.time()
        clips.append(render_clip(meta, p, i, cam_cache, audio, effects))
        log(f"render clip {i}/{len(plans)}: {fmt(p['start'])}-{fmt(p['end'])} "
            f"via {clips[-1]['source']} ({time.time() - t:.0f} s)")
    summary = out_dir(meta["id"]) / "clips.json"
    summary.write_text(json.dumps({"video": meta["id"], "title": meta["title"], "clips": clips},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"selesai: {len(clips)} clip di out/{meta['id']}/ ({time.time() - t0:.0f} s)")
    return clips


def main() -> None:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description="Link video -> clip 9:16 dengan caption")
    ap.add_argument("url")
    ap.add_argument("--top", type=int, default=3, help="jumlah clip (default 3)")
    ap.add_argument("--pool", type=int, help="jumlah kandidat yang ditranskrip (default top x 3)")
    ap.add_argument("--effects", choices=["all", "sfx", "none"], default="all",
                    help="all = SFX + zoom + lagu (default), sfx = tanpa lagu, none = polos")
    ap.add_argument("--quick", action="store_true",
                    help="hanya puncak sinyal, tanpa transkrip dan scan LLM seluruh video (lebih cepat)")
    args = ap.parse_args()
    for c in run(args.url, args.top, args.pool, args.effects, args.quick):
        print(f"  {c['file']}  {c['duration']:.0f}s  {c['layout']:<6}  {c['link']}  {c['title']}")
        print(f"      {c['text'][:110]}")


if __name__ == "__main__":
    main()
