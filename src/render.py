import functools
import os
import subprocess
import sys
from pathlib import Path

from src.paths import ROOT

W, H = 1080, 1920
FONTS = ROOT / "fonts"


@functools.cache
def video_encoder() -> list[str]:
    """Pakai NVENC (GPU NVIDIA) kalau ada, kalau tidak fallback ke libx264."""
    test = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
            "-c:v", "h264_nvenc", "-f", "null", "-"]
    if subprocess.run(test, capture_output=True).returncode == 0:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def rel(path: Path, cwd: Path) -> str:
    """Path relatif dengan slash biasa. Filter ffmpeg rewel dengan 'D:\' di Windows."""
    return os.path.relpath(path, cwd).replace("\\", "/")


def build_filter(ass: Path | None = None, cwd: Path | None = None) -> str:
    fc = f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1[stack]"
    if ass:
        fc += f";[stack]ass={rel(ass, cwd)}:fontsdir={rel(FONTS, cwd)}[out]"
    else:
        fc += ";[stack]null[out]"
    return fc


def render_vertical(src: Path, out: Path, ass: Path | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cwd = (ass or src).resolve().parent
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src.resolve()),
           "-filter_complex", build_filter(ass.resolve() if ass else None, cwd),
           "-map", "[out]", "-map", "0:a?", *video_encoder(), "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out.resolve())]
    subprocess.run(cmd, check=True, cwd=cwd)
    return out


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        print("usage: python -m src.render <src.mp4> <out.mp4> [captions.ass]")
        sys.exit(1)
    ass = Path(argv[3]) if len(argv) > 3 else None
    out = render_vertical(Path(argv[1]), Path(argv[2]), ass)
    print(f"saved : {out}")


if __name__ == "__main__":
    main(sys.argv)
