# KlipYerOnline

AI auto-clipper: kasih link video YouTube, keluar clip vertikal 9:16 yang siap upload, lengkap dengan layout facecam + gameplay dan caption kata per kata.

## Fitur

- Cari momen dari seluruh video: LLM membaca transkrip penuh, ditambah heatmap "Most Replayed" dan lonjakan suara sebagai petunjuk
- LLM (Claude atau Gemini) menyaring kandidat yang membosankan, memotong dari hook sampai punchline, dan membuat judul
- Video tidak diunduh: ffmpeg baca potongan langsung dari stream YouTube
- Transkrip per kata (faster-whisper, GPU) untuk caption karaoke
- Panjang clip mengikuti isi (reaksi cepat sekitar 10 detik, cerita sampai 60 detik)
- Efek gaya clipper: boom + zoom di punchline, judul hook, lagu latar yang mengecil saat streamer ngomong
- Deteksi facecam otomatis (YuNet) + preset per channel
- Render 9:16: facecam di atas, gameplay di bawah, atau center crop kalau tidak ada facecam

## Tech stack

- Python 3.12, yt-dlp, numpy, scipy
- Claude API atau Gemini API untuk memilih dan memotong clip
- faster-whisper (large-v3-turbo), OpenCV
- ffmpeg (NVENC kalau ada GPU NVIDIA)

## Cara pakai

Butuh Python 3.12, ffmpeg, dan Node.js (dipakai yt-dlp untuk YouTube).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m src.pipeline "https://www.youtube.com/watch?v=<id>" --top 3
```

Hasilnya ada di `out/<id>/` beserta `clips.json`.

Opsi:

- `--effects all|sfx|none`: semua efek (default), tanpa lagu, atau polos
- `--pool N`: jumlah puncak sinyal yang dipakai (default top x 3)
- `--quick`: hanya puncak sinyal, tanpa transkrip dan scan seluruh video (lebih cepat, tapi momen yang tidak keras bisa terlewat)
- `--upload private|unlisted|public`: langsung upload ke YouTube kamu setelah render

Supaya clip dipilih LLM, salin `.env.example` jadi `.env` lalu isi `ANTHROPIC_API_KEY` (Claude, berbayar) atau `GEMINI_API_KEY` (Gemini, ada free tier). Kalau Claude gagal, misalnya saldo habis, otomatis pindah ke Gemini. Tanpa key, pipeline tetap jalan dengan pemilihan heuristik.

Gaya judul mengikuti Shorts clip streamer yang sedang ramai (humor Gen Z, 💀 dan 🥀). Contohnya disimpan di `data/trends/shorts.json`; perbarui dengan `python -m src.trends` supaya ikut tren terbaru.

Lagu dan SFX sendiri ditaruh di `assets/`, lihat [assets/README.md](assets/README.md).

Model whisper di-download otomatis saat pertama jalan. Kalau download dari Hugging Face macet, taruh model manual di `models/faster-whisper-large-v3-turbo/`.

### Upload ke YouTube

Persiapan sekali:

1. Buka [Google Cloud Console](https://console.cloud.google.com/), buat project baru.
2. APIs & Services, Library, aktifkan **YouTube Data API v3**.
3. OAuth consent screen: tipe External, isi nama app dan email, lalu tambahkan email Google kamu di **Test users**.
4. Credentials, Create credentials, OAuth client ID, tipe **Desktop app**. Download JSON-nya dan simpan sebagai `.secrets/client_secret.json` (folder ini tidak di-commit).

Lalu:

```powershell
python -m src.upload <id> --dry-run              # cek judul dan deskripsi dulu
python -m src.upload <id>                        # upload semua clip sebagai private
python -m src.upload <id> --only 1 --privacy public
```

Login pertama membuka browser untuk memilih channel. Clip yang sudah ter-upload dicatat di `clips.json`, jadi tidak di-upload dua kali.

Catatan:

- Project Google yang belum lolos audit YouTube hanya bisa upload sebagai **private**. Setelah ter-upload, ubah ke public dari YouTube Studio, atau ajukan audit di Google Cloud.
- Kuota gratis API sekitar 10.000 unit per hari, satu upload sekitar 1.600 unit, jadi kira-kira 6 clip per hari.
- Clip dari video orang lain bisa kena klaim hak cipta. Paling aman dipakai untuk channel sendiri atau streamer yang sudah kasih izin.

## Dokumen

- [Design doc](AI_Auto_Clipper_Design_Doc.md)
- [Step by step testing](STEPS.md)
- [Pembagian tugas](TEAM.md)

## Status

MVP Phase 1 selesai (Step 0 sampai 11), ditambah LLM refine, render dari stream, dan efek. Berikutnya: chat Twitch, eval.
