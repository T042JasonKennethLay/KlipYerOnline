import json
import sys

import yt_dlp

from src.paths import work_dir

YDL_BASE = {"quiet": True, "no_warnings": True}


def fetch_metadata(url: str) -> dict:
    with yt_dlp.YoutubeDL({**YDL_BASE, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "id": info["id"],
        "url": info.get("webpage_url") or url,
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "extractor": info.get("extractor_key"),
        "heatmap": info.get("heatmap") or [],
    }


def load_or_fetch_metadata(url: str) -> dict:
    meta = fetch_metadata(url)
    path = work_dir(meta["id"]) / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.ingest <url>")
        sys.exit(1)
    meta = load_or_fetch_metadata(argv[1])
    print(f"id        : {meta['id']}")
    print(f"title     : {meta['title']}")
    print(f"channel   : {meta['channel']}")
    print(f"duration  : {meta['duration']} s")
    print(f"extractor : {meta['extractor']}")
    print(f"heatmap   : {len(meta['heatmap'])} titik")
    print(f"saved     : work/{meta['id']}/meta.json")


if __name__ == "__main__":
    main(sys.argv)
