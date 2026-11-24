"""Caption gaya clipper: 3 kata per layar, kata yang sedang diucapkan berwarna kuning."""
import re
from pathlib import Path

FONT = "Montserrat ExtraBold"

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Clip,{FONT},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Title,{FONT},62,&H00000000,&H00000000,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,3,14,0,8,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = "&H00FFFF&"   # ASS pakai BGR, jadi ini kuning
WHITE = "&HFFFFFF&"
MAX_GAP = 1.0             # jeda lebih dari ini = chunk caption baru
TITLE_SECS = 3.0          # judul tampil di awal clip, lalu hilang supaya tidak menutupi wajah


def ass_time(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def clean(word: str) -> str:
    w = re.sub(r"[{}\\]", "", word).strip().upper()
    return w.strip(",.?!") if len(w) > 1 else w


def chunk_words(words: list[dict], size: int) -> list[list[dict]]:
    """Pecah per `size` kata, tapi mulai chunk baru kalau ada jeda panjang."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) == size or w["start"] - cur[-1]["end"] > MAX_GAP):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def title_event(title: str, y: int) -> str:
    """Judul hitam di kotak putih (gaya clipper), muncul dengan pop lalu fade out."""
    txt = re.sub(r"[{}\\]", "", title).strip().upper()
    tags = f"{{\\an8\\q0\\pos(540,{y})\\fscx90\\fscy90\\t(0,120,\\fscx100\\fscy100)\\fad(0,250)}}"
    return f"Dialogue: 1,{ass_time(0)},{ass_time(TITLE_SECS)},Title,,0,0,0,,{tags}{txt}"


def build_ass(words: list[dict], clip_start: float, clip_end: float, out_path: Path,
              chunk: int = 3, pos: tuple[int, int] = (540, 1180), title: str = "",
              title_y: int = 70) -> Path:
    """words: [{"word","start","end"}] dalam waktu absolut video."""
    words = [w for w in words if w["end"] > clip_start and w["start"] < clip_end and clean(w["word"])]
    events = [title_event(title, title_y)] if title.strip() else []
    for group in chunk_words(words, chunk):
        for j, w in enumerate(group):
            st = max(w["start"], clip_start) - clip_start
            nxt = group[j + 1]["start"] if j + 1 < len(group) else w["end"]
            en = min(nxt, clip_end) - clip_start
            if en <= st:
                continue
            parts = []
            for k, g in enumerate(group):
                txt = clean(g["word"])
                parts.append(f"{{\\c{HIGHLIGHT}}}{txt}{{\\c{WHITE}}}" if k == j else txt)
            pop = "\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)" if j == 0 else ""
            tags = f"{{\\an5\\pos({pos[0]},{pos[1]}){pop}}}"
            events.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Clip,,0,0,0,,{tags}{' '.join(parts)}")
    out_path.write_text(ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
