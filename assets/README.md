# Aset audio

Taruh file sendiri di sini. Isinya tidak ikut di-commit karena lisensi tiap file berbeda.

| Folder | Nama file | Dipakai untuk |
|---|---|---|
| `sfx/` | `boom*.mp3` / `.wav` | Bunyi di punchline, misalnya vine boom |
| `sfx/` | `whoosh*.mp3` / `.wav` | Transisi di awal clip |
| `music/` | bebas | Lagu latar, dipilih acak per clip |

Kalau `sfx/` kosong, pipeline membuat boom dan whoosh sendiri pakai ffmpeg (`sfx/_gen/`).
Kalau `music/` kosong, clip dibuat tanpa lagu.

Pakai hanya lagu dan SFX bebas royalti supaya clip tidak kena copyright claim:

- YouTube Audio Library: studio.youtube.com, menu Audio Library (lagu dan efek suara)
- Pixabay Music dan Sound Effects: pixabay.com/music, pixabay.com/sound-effects (cari "phonk", "vine boom")
- Mixkit: mixkit.co/free-sound-effects

Lagu phonk atau lagu viral dari artis terkenal hampir pasti kena claim, jangan dipakai.

Cek aset yang terbaca: `python -m src.fx`
