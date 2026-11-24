"""Satu perintah: link video -> beberapa clip 9:16 dengan caption.

    python -m src.pipeline "<url>" --top 3

Semua tahap pakai cache di work/<id>/, jadi kalau ada yang gagal tinggal jalankan ulang.
"""
import argparse
import json
import time
import warnings

from src.boundaries import words_in
from src.captions import build_ass
from src.ingest import download_audio, download_section, load_or_fetch_metadata
from src.paths import out_dir, work_dir
from src.reframe import preset_or_detect
from src.refine import refine
from src.render import render_vertical
from src.score import find_candidates
from src.transcribe import transcribe_candidate

MIN_WORDS_PER_SEC = 0.25         # kata/detik di sekitar puncak; di bawah ini = momen hening (butuh VLM, belum ada)
CAPTION_Y = {"cam": 790, "center": 1180}


def fmt(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def plan_clips(meta: dict, top: int, pool: int | None = None) -> list[dict]:
    """Ambil kandidat lebih banyak dari yang dibutuhkan, transkrip, buang yang hening, lalu refine."""
    audio = download_audio(meta["url"], meta["id"])
    pool = pool or top * 3
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
    clips, mode = refine(meta["id"], voiced)
    log(f"refine ({mode}): {len(clips)} dari {len(voiced)} kandidat layak")
    plans = []
    for c in clips[:top]:
        words = words_in(c["segments"], c["start"], c["end"])
        text = " ".join(w["word"] for w in words)
        log(f"  {fmt(c['start'])}-{fmt(c['end'])} ({c['end'] - c['start']:.0f}s) {c['title']!r} {c['reason']}")
        plans.append({k: v for k, v in c.items() if k != "segments"} | {"words": words, "text": text})
    return plans


def render_clip(meta: dict, plan: dict, idx: int, cam_cache: dict) -> dict:
    vid = meta["id"]
    s, e = plan["start"], plan["end"]
    raw = download_section(meta["url"], vid, s, e, f"raw_{int(s * 100)}_{int(e * 100)}")
    if "box" not in cam_cache:
        cam_cache["box"], cam_cache["src"] = preset_or_detect(raw, meta["channel"])
        log(f"facecam: {cam_cache['box']} ({cam_cache['src']})")
    box = cam_cache["box"]
    layout = "cam" if box else "center"
    ass = build_ass(plan["words"], s, e, work_dir(vid) / f"cap_{int(s * 100)}.ass", pos=(540, CAPTION_Y[layout]))
    out = out_dir(vid) / f"clip_{idx:02d}_{int(s)}.mp4"
    render_vertical(raw, out, ass, box)
    return {"file": str(out.name), "start": s, "end": e, "duration": round(e - s, 2), "score": plan["score"],
            "layout": layout, "title": plan["title"], "punchline": plan["punchline"], "reason": plan["reason"],
            "link": f"https://youtu.be/{vid}?t={int(s)}", "text": plan["text"]}


def run(url: str, top: int = 3, pool: int | None = None) -> list[dict]:
    t0 = time.time()
    meta = load_or_fetch_metadata(url)
    log(f"{meta['title']} ({meta['channel']}, {fmt(meta['duration'])})")
    plans = plan_clips(meta, top, pool)
    cam_cache: dict = {}
    clips = []
    for i, p in enumerate(plans, 1):
        log(f"render clip {i}/{len(plans)}: {fmt(p['start'])}-{fmt(p['end'])}")
        clips.append(render_clip(meta, p, i, cam_cache))
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
    args = ap.parse_args()
    for c in run(args.url, args.top, args.pool):
        print(f"  {c['file']}  {c['duration']:.0f}s  {c['layout']:<6}  {c['link']}  {c['title']}")
        print(f"      {c['text'][:110]}")


if __name__ == "__main__":
    main()
