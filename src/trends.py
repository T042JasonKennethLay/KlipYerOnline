"""Kumpulkan contoh judul dan deskripsi Shorts clip streamer yang sedang ramai.

Hasilnya (data/trends/shorts.json) dipakai refine sebagai contoh gaya judul dan dipakai upload
untuk hashtag. Jalankan ulang sesekali (atau lewat CI) supaya ikut tren terbaru.

    python -m src.trends                 # cari channel clipper, ambil Shorts teratas
    python -m src.trends --show          # tampilkan contoh yang tersimpan
"""
import argparse
import collections
import json
import re
import time

import yt_dlp

from src.paths import ROOT

OUT = ROOT / "data" / "trends" / "shorts.json"
STREAMERS = ["ishowspeed", "kai cenat", "jynxzi", "xqc", "caseoh", "adin ross", "duke dennis", "sketch",
             "kai cenat stream", "streamer"]
QUERY = "{} clip #shorts"
PER_QUERY = 50
PER_CHANNEL_TAB = 60
PER_CHANNEL_KEEP = 12      # batasi per channel supaya contoh tidak didominasi satu gaya
MAX_SAMPLES = 80
DETAIL = 40                # ambil deskripsi + tag untuk sekian teratas
YDL = {"quiet": True, "no_warnings": True, "extract_flat": True, "ignoreerrors": True}


def discover_channels(log=print) -> dict[str, str]:
    """Channel yang muncul di hasil pencarian clip pendek (<= 90 detik)."""
    found: dict[str, str] = {}
    with yt_dlp.YoutubeDL(YDL) as ydl:
        for s in STREAMERS:
            res = ydl.extract_info(f"ytsearch{PER_QUERY}:{QUERY.format(s)}", download=False) or {}
            for e in res.get("entries") or []:
                cid = e and (e.get("channel_id") or (e.get("channel_url") or "").rsplit("/", 1)[-1])
                if cid and cid.startswith("UC") and (e.get("duration") or 999) <= 90:
                    found.setdefault(cid, e.get("channel") or "")
            log(f"  cari '{s}': {len(found)} channel")
    return found


def channel_shorts(channels: dict[str, str], log=print) -> list[dict]:
    rows = []
    with yt_dlp.YoutubeDL({**YDL, "playlistend": PER_CHANNEL_TAB}) as ydl:
        for cid, name in channels.items():
            res = ydl.extract_info(f"https://www.youtube.com/channel/{cid}/shorts", download=False) or {}
            got = [{"id": e["id"], "title": e["title"], "views": e["view_count"], "channel": name}
                   for e in res.get("entries") or [] if e and e.get("title") and e.get("view_count")]
            got.sort(key=lambda r: -r["views"])
            rows += got[:PER_CHANNEL_KEEP]
            if got:
                log(f"  {name}: {len(got)} shorts")
    return rows


def add_details(rows: list[dict], log=print) -> None:
    with yt_dlp.YoutubeDL({**YDL, "extract_flat": False, "skip_download": True}) as ydl:
        for r in rows[:DETAIL]:
            info = ydl.extract_info(f"https://www.youtube.com/shorts/{r['id']}", download=False) or {}
            r["description"] = (info.get("description") or "")[:600]
            r["tags"] = (info.get("tags") or [])[:15]
            r["duration"] = info.get("duration")
    log(f"  detail {min(len(rows), DETAIL)} shorts teratas")


def hashtags(rows: list[dict], top: int = 15) -> list[tuple[str, int]]:
    c = collections.Counter()
    for r in rows:
        for h in set(re.findall(r"#\w+", (r.get("title") or "") + " " + (r.get("description") or ""))):
            c[h.lower()] += 1
    return c.most_common(top)


def collect(log=print) -> dict:
    channels = discover_channels(log)
    rows = sorted(channel_shorts(channels, log), key=lambda r: -r["views"])[:MAX_SAMPLES]
    add_details(rows, log)
    data = {"fetched": time.strftime("%Y-%m-%d"), "samples": rows, "hashtags": hashtags(rows)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"tersimpan {len(rows)} contoh dari {len({r['channel'] for r in rows})} channel di {OUT.relative_to(ROOT)}")
    return data


def load() -> dict | None:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None


def title_examples(n: int = 30) -> list[str]:
    """Judul Shorts teratas, maksimal 3 per channel, untuk contoh gaya di prompt."""
    data = load()
    if not data:
        return []
    per = collections.Counter()
    out = []
    for r in data["samples"]:
        if per[r["channel"]] < 3:
            per[r["channel"]] += 1
            out.append(r["title"])
        if len(out) >= n:
            break
    return out


def top_hashtags(n: int = 5, skip: tuple = ("#shorts",)) -> list[str]:
    data = load()
    return [h for h, _ in (data or {}).get("hashtags", []) if h not in skip][:n]


def main() -> None:
    ap = argparse.ArgumentParser(description="Contoh judul Shorts clip streamer yang sedang ramai")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    data = load() if args.show else collect()
    if not data:
        print("Belum ada data. Jalankan: python -m src.trends")
        return
    print(f"diambil {data['fetched']}, {len(data['samples'])} contoh")
    for r in data["samples"][:40]:
        print(f"  {r['views']:>10,}  {r['channel'][:18]:<18}  {r['title']}")
    print("hashtag:", " ".join(f"{h}({n})" for h, n in data["hashtags"]))


if __name__ == "__main__":
    main()
