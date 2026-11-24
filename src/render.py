import functools
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920


@functools.cache
def video_encoder() -> list[str]:
    """Pakai NVENC (GPU NVIDIA) kalau ada, kalau tidak fallback ke libx264."""
    test = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
            "-c:v", "h264_nvenc", "-f", "null", "-"]
    if subprocess.run(test, capture_output=True).returncode == 0:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def build_filter() -> str:
    return f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1[out]"


def render_vertical(src: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", build_filter(),
           "-map", "[out]", "-map", "0:a?", *video_encoder(), "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return out


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        print("usage: python -m src.render <src.mp4> <out.mp4>")
        sys.exit(1)
    out = render_vertical(Path(argv[1]), Path(argv[2]))
    print(f"saved : {out}")


if __name__ == "__main__":
    main(sys.argv)
