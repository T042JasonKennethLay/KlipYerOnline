from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
OUT = ROOT / "out"


def work_dir(video_id: str) -> Path:
    d = WORK / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def out_dir(video_id: str) -> Path:
    d = OUT / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d
