# KlipYerOnline

AI auto-clipper: kasih link video YouTube, keluar clip vertikal 9:16 yang siap upload, lengkap dengan layout facecam + gameplay dan caption kata per kata.

## Fitur

- Cari momen menarik dari heatmap "Most Replayed" dan lonjakan suara
- Download hanya potongan video yang dipakai, bukan full video
- Transkrip per kata (faster-whisper, GPU) untuk caption karaoke
- Batas clip di-snap ke awal dan akhir kalimat
- Deteksi facecam otomatis (YuNet) + preset per channel
- Render 9:16: facecam di atas, gameplay di bawah, atau center crop kalau tidak ada facecam

## Tech stack

- Python 3.12, yt-dlp, numpy, scipy
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

Model whisper di-download otomatis saat pertama jalan. Kalau download dari Hugging Face macet, taruh model manual di `models/faster-whisper-large-v3-turbo/`.

## Dokumen

- [Design doc](AI_Auto_Clipper_Design_Doc.md)
- [Step by step testing](STEPS.md)
- [Pembagian tugas](TEAM.md)

## Status

MVP Phase 1 selesai (Step 0 sampai 11). Berikutnya: LLM refine, chat Twitch, eval.
