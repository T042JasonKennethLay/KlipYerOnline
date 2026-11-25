"""Efek gaya clipper: SFX di punchline, zoom punch, lagu latar yang mengecil saat streamer ngomong.

File sendiri (opsional, tidak di-commit):
    assets/sfx/boom*.mp3|wav     dipakai di punchline (kalau kosong: vine boom buatan ffmpeg)
    assets/sfx/whoosh*.mp3|wav   dipakai di awal clip (kalau kosong: whoosh buatan ffmpeg)
    assets/music/*.mp3|wav       lagu latar, dipilih acak (kalau kosong: tanpa lagu)

Pakai hanya lagu dan SFX yang bebas royalti (YouTube Audio Library, Pixabay, Mixkit), supaya
clip tidak kena copyright claim.

    python -m src.fx     # bikin SFX bawaan dan tampilkan aset yang ketemu
"""
import random
import subprocess
from pathlib import Path

from src.paths import ROOT

ASSETS = ROOT / "assets"
SFX_DIR = ASSETS / "sfx"
MUSIC_DIR = ASSETS / "music"
GEN_DIR = SFX_DIR / "_gen"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

MUSIC_VOL = 0.14      # sekitar -17 dB di bawah suara streamer, lalu ditekan lagi saat ada suara
BOOM_VOL = 0.75
WHOOSH_VOL = 0.25
LOUDNESS = -14     # LUFS, target YouTube. Semua clip volumenya sama
GEN_VERSION = 2    # naikkan kalau resep SFX buatan berubah (file lama tidak dipakai lagi)
ZOOM = 0.14           # zoom punch 14 persen, lalu kembali dalam sekitar 0.3 detik

# Sintesis sederhana: sinus yang nadanya turun + transien noise + saturasi + sedikit gema.
GENERATED = {
    "boom": ("aevalsrc='0.9*exp(-3.2*t)*(sin(2*PI*(42*t+10*(1-exp(-7*t))))"
             "+0.35*sin(4*PI*(42*t+10*(1-exp(-7*t)))))+0.5*exp(-60*t)*(random(0)*2-1)':s=48000:d=1.4",
             "asoftclip=type=tanh:threshold=0.6,lowpass=f=900,aecho=0.8:0.5:60|120:0.3|0.2,"
             "loudnorm=I=-14:TP=-1.5"),
    "whoosh": ("aevalsrc='(random(0)*2-1)*exp(-pow((t-0.32)/0.13,2))':s=48000:d=0.65",
               "highpass=f=300,lowpass=f=2500,afade=t=in:d=0.15,afade=t=out:st=0.4:d=0.25,"
               "loudnorm=I=-22:TP=-4"),
}


def generate(kind: str) -> Path:
    out = GEN_DIR / f"{kind}_v{GEN_VERSION}.wav"
    if not out.exists():
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        src, af = GENERATED[kind]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-af", af,
                        "-ar", "48000", "-ac", "2", str(out)], check=True)
    return out


def user_files(folder: Path, prefix: str = "") -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_EXT and p.stem.lower().startswith(prefix))


def pick_sfx(kind: str, rng: random.Random) -> Path:
    own = user_files(SFX_DIR, kind)
    return rng.choice(own) if own else generate(kind)


def pick_music(rng: random.Random) -> Path | None:
    own = user_files(MUSIC_DIR)
    return rng.choice(own) if own else None


def zoom_filter(punch: float | None) -> str:
    """Zoom punch di detik `punch` (relatif ke awal clip). Dipasang sebelum caption."""
    if punch is None:
        return ""
    z = f"1+{ZOOM}*gte(it,{punch:.2f})*exp(-10*max(0,it-{punch:.2f}))"
    return (f",zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30")


def audio_plan(voice: str, first: int, punch: float | None, duration: float, seed: int,
               music: bool = True) -> tuple[list[str], str]:
    """Return (argumen input ffmpeg tambahan, filter audio yang berakhir di [aout]).

    voice: label audio streamer (misal "1:a"), first: nomor input pertama untuk aset tambahan.
    """
    rng = random.Random(seed)
    inputs: list[str] = []
    # Mic streamer sering pecah waktu teriak (clipping di stream aslinya): perbaiki dulu.
    clean = "adeclip,aresample=48000"
    chains = [f"[{voice}]{clean},asplit=2[voice][sc]"]
    mix = ["[voice]"]
    idx = first

    track = pick_music(rng) if music else None
    if track:
        inputs += ["-stream_loop", "-1", "-i", str(track)]
        chains.append(f"[{idx}:a]aresample=48000,volume={MUSIC_VOL},atrim=0:{duration:.2f},"
                      f"afade=t=in:d=0.5,afade=t=out:st={max(duration - 1, 0):.2f}:d=1[mus]")
        chains.append("[mus][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[duck]")
        mix.append("[duck]")
        idx += 1
    else:
        chains[0] = f"[{voice}]{clean}[voice]"

    inputs += ["-i", str(pick_sfx("whoosh", rng))]
    chains.append(f"[{idx}:a]aresample=48000,volume={WHOOSH_VOL}[wh]")
    mix.append("[wh]")
    idx += 1

    if punch is not None:
        ms = int(max(punch, 0) * 1000)
        inputs += ["-i", str(pick_sfx("boom", rng))]
        chains.append(f"[{idx}:a]aresample=48000,adelay={ms}:all=1,volume={BOOM_VOL}[boom]")
        mix.append("[boom]")
        idx += 1

    chains.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,"
                  f"loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.89[aout]")
    return inputs, ";".join(chains)


def main() -> None:
    for kind in GENERATED:
        print(f"{kind:<7} -> {pick_sfx(kind, random.Random(0))}")
    music = user_files(MUSIC_DIR)
    print(f"music   -> {len(music)} file di {MUSIC_DIR}" + ("" if music else " (kosong, clip tanpa lagu)"))


if __name__ == "__main__":
    main()
