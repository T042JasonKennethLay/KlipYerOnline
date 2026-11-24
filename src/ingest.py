import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import download_range_func

from src.paths import work_dir

YDL_BASE = {"quiet": True, "no_warnings": True, "js_runtimes": {"node": {}, "deno": {}}}
# Audio penuh dipakai untuk analisis DAN untuk suara clip, jadi tetap kualitas bagus.
AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
URL_TTL = 3 * 3600      # link stream YouTube kedaluwarsa sekitar 6 jam, ambil ulang lebih awal


def video_format(max_height: int) -> str:
    return (f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/bv*[height<={max_height}]+ba/"
            f"b[height<={max_height}]")


def stream_format(max_height: int) -> str:
    """Video saja, utamakan HLS + H.264. Link HTTPS biasa sering kena 403 kalau dibaca ffmpeg,
    HLS stabil, dan H.264 jauh lebih ringan di-decode daripada AV1/VP9."""
    h = max_height
    return (f"bv*[height<={h}][protocol=m3u8_native][vcodec^=avc1]/bv*[height<={h}][protocol=m3u8_native]/"
            f"bv*[height<={h}][vcodec^=avc1]/bv*[height<={h}]/b[height<={h}]")


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


def find_audio(video_id: str):
    for p in work_dir(video_id).glob("audio.*"):
        if p.suffix not in (".part", ".ytdl"):
            return p
    return None


def download_audio(url: str, video_id: str):
    cached = find_audio(video_id)
    if cached:
        return cached
    opts = {
        **YDL_BASE,
        "format": AUDIO_FORMAT,
        "outtmpl": str(work_dir(video_id) / "audio.%(ext)s"),
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return find_audio(video_id)


def download_section(url: str, video_id: str, start: float, end: float, name: str, max_height: int = 1080):
    """Download HANYA potongan [start, end] detik, bukan full video."""
    out = work_dir(video_id) / f"{name}.mp4"
    if out.exists():
        return out
    opts = {
        **YDL_BASE,
        "format": video_format(max_height),
        "outtmpl": str(work_dir(video_id) / f"{name}.%(ext)s"),
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "merge_output_format": "mp4",
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out


@dataclass
class StreamSource:
    """Video dibaca langsung dari stream YouTube, audio dari file audio lokal (sudah diunduh untuk
    analisis). Tidak ada file video perantara dan tidak ada encode dua kali."""
    video: str
    audio: Path | None
    headers: str
    width: int
    height: int
    fetched: float

    def video_args(self, start: float, dur: float) -> list[str]:
        net = ["-reconnect", "1", "-reconnect_delay_max", "5"] if self.video.startswith("http") else []
        hdr = ["-headers", self.headers] if self.headers else []
        return [*net, *hdr, "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", self.video]

    def input_args(self, start: float, dur: float) -> list[str]:
        """Input 0 = video. Kalau ada audio lokal, input 1 = audio."""
        args = self.video_args(start, dur)
        if self.audio:
            args += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(self.audio)]
        return args

    @property
    def audio_label(self) -> str:
        return "1:a" if self.audio else "0:a"


_STREAMS: dict[tuple[str, int], StreamSource] = {}


def stream_source(url: str, audio: Path | None = None, max_height: int = 1080,
                  refresh: bool = False) -> StreamSource:
    key = (url, max_height)
    cached = _STREAMS.get(key)
    if cached and not refresh and time.time() - cached.fetched < URL_TTL:
        cached.audio = audio
        return cached
    with yt_dlp.YoutubeDL({**YDL_BASE, "format": stream_format(max_height)}) as ydl:
        info = ydl.extract_info(url, download=False)
    v = (info.get("requested_formats") or [info])[0]
    headers = "".join(f"{k}: {val}\r\n" for k, val in (v.get("http_headers") or {}).items())
    src = StreamSource(v["url"], audio, headers, v["width"], v["height"], time.time())
    _STREAMS[key] = src
    return src


def grab_probe(src: StreamSource, start: float, out: Path, dur: float = 20) -> Path:
    """Potongan video pendek tanpa encode ulang, cukup untuk deteksi facecam."""
    if not out.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", *src.video_args(start, dur), "-an", "-c", "copy", str(out)],
                       check=True)
    return out


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.ingest <url> [--audio]")
        sys.exit(1)
    meta = load_or_fetch_metadata(argv[1])
    if "--audio" in argv:
        audio = download_audio(meta["url"], meta["id"])
        size_mb = audio.stat().st_size / 1024 / 1024
        print(f"audio     : {audio.name} ({size_mb:.1f} MB)")
    print(f"id        : {meta['id']}")
    print(f"title     : {meta['title']}")
    print(f"channel   : {meta['channel']}")
    print(f"duration  : {meta['duration']} s")
    print(f"extractor : {meta['extractor']}")
    print(f"heatmap   : {len(meta['heatmap'])} titik")
    print(f"saved     : work/{meta['id']}/meta.json")


if __name__ == "__main__":
    main(sys.argv)
