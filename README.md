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

Supaya clip dipilih LLM, salin `.env.example` jadi `.env` lalu isi `ANTHROPIC_API_KEY` (Claude, berbayar) atau `GEMINI_API_KEY` (Gemini, ada free tier). Kalau Claude gagal, misalnya saldo habis, otomatis pindah ke Gemini. Tanpa key, pipeline tetap jalan dengan pemilihan heuristik.

Lagu dan SFX sendiri ditaruh di `assets/`, lihat [assets/README.md](assets/README.md).

Model whisper di-download otomatis saat pertama jalan. Kalau download dari Hugging Face macet, taruh model manual di `models/faster-whisper-large-v3-turbo/`.

## Dokumen

- [Design doc](AI_Auto_Clipper_Design_Doc.md)
- [Step by step testing](STEPS.md)
- [Pembagian tugas](TEAM.md)

## Status

MVP Phase 1 selesai (Step 0 sampai 11), ditambah LLM refine, render dari stream, dan efek. Berikutnya: chat Twitch, eval.
