import functools
import os
import subprocess
import sys
from pathlib import Path

from src.paths import ROOT

W, H = 1080, 1920
CAM_H = 640
GAME_H = H - CAM_H
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


def game_crop_x(src_w: int, src_h: int, cam_box: tuple[int, int, int, int]) -> int:
    """Potongan gameplay di tengah, tapi digeser menjauhi facecam supaya kamera tidak dobel."""
    gw = int(src_h * W / GAME_H) // 2 * 2
    x = (src_w - gw) // 2
    cx, _, cw, _ = cam_box
    if cx + cw / 2 > src_w / 2:
        x = min(x, cx - gw)
    else:
        x = max(x, cx + cw)
    return max(0, min(x, src_w - gw)) // 2 * 2


def build_filter(ass: Path | None = None, cwd: Path | None = None,
                 cam_box: tuple[int, int, int, int] | None = None, src_size: tuple[int, int] | None = None) -> str:
    if cam_box and src_size:
        x, y, w, h = cam_box
        gx = game_crop_x(*src_size, cam_box)
        fc = (f"[0:v]split=2[a][b];"
              f"[a]crop={w}:{h}:{x}:{y},scale={W}:{CAM_H},setsar=1[cam];"
              f"[b]crop=ih*{W}/{GAME_H}:ih:{gx}:0,scale={W}:{GAME_H},setsar=1[game];"
              f"[cam][game]vstack=inputs=2[stack]")
    else:
        fc = f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1[stack]"
    if ass:
        fc += f";[stack]ass={rel(ass, cwd)}:fontsdir={rel(FONTS, cwd)}[out]"
    else:
        fc += ";[stack]null[out]"
    return fc


def video_size(src: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True, check=True).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def render_vertical(src: Path, out: Path, ass: Path | None = None,
                    cam_box: tuple[int, int, int, int] | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cwd = (ass or src).resolve().parent
    fc = build_filter(ass.resolve() if ass else None, cwd, cam_box, video_size(src) if cam_box else None)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src.resolve()),
           "-filter_complex", fc,
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
