# KlipYerOnline: Step by Step Testing

> Prinsip: **satu step = satu hal kecil yang bisa dites sendiri.** Jangan lanjut ke step berikutnya sebelum step sekarang lulus.
> Tiap step menghasilkan file output di folder `work/` atau `out/`, jadi kita bisa cek hasilnya pakai mata sendiri.

Target akhir bagian ini (Phase 0–1): **link YouTube → 3 clip MP4 9:16 dengan caption**, jalan di laptop sendiri.
Hal yang lebih berat (Twitch chat, LLM, VLM, Rust, K8s) baru disentuh **setelah ini jalan**.

---

## Progress

| # | Step | Status |
|---|---|---|
| 0 | Setup environment | ✅ |
| 1 | Ambil metadata + heatmap dari link | ✅ |
| 2 | Download audio saja | ✅ |
| 3 | Loudness per detik + grafik | ✅ |
| 4 | Gabung sinyal → top momen | ✅ |
| 5 | Download potongan video (section) | ✅ |
| 6 | Render 9:16 (center crop) | ✅ |
| 7 | Transkrip kandidat (timestamp per kata) | ✅ |
| 8 | Snap ke batas kalimat | ✅ |
| 9 | Caption karaoke (.ass) + render | ✅ |
| 10 | Layout facecam + gameplay | ✅ |
| 11 | `pipeline.py`: semua jadi satu perintah | ✅ |

Status: ⬜ belum · 🟨 lagi dikerjain · ✅ lulus

---

## Step 0: Setup environment

**Tujuan:** semua tools dasar terpasang dan bisa dipanggil.

**Yang dibuat:**
- Virtual env Python (`.venv`)
- `requirements.txt` awal: `yt-dlp`, `numpy`, `scipy`, `matplotlib`
- Folder: `src/`, `work/`, `out/`
- ffmpeg terpasang dan ada di PATH

**Cara test:**
```powershell
python --version
ffmpeg -version
yt-dlp --version
```

**Lulus kalau:** ketiga perintah keluar versinya tanpa error.

---

## Step 1: Ambil metadata + heatmap dari link

**Tujuan:** buktikan kita bisa "membaca" video **tanpa download videonya**.

**Yang dibuat:** `src/ingest.py` → fungsi `fetch_metadata(url)`, simpan hasilnya ke `work/<id>/meta.json`.

**Cara test:**
```powershell
python -m src.ingest "<link youtube populer>"
```
Coba 3 video: 1 video populer (views jutaan), 1 video kecil, 1 VOD/stream panjang.

**Lulus kalau:**
- Keluar `title`, `duration`, dan jumlah titik heatmap
- Video populer punya heatmap (~100 titik), video kecil boleh kosong (itu normal)

**Yang dipelajari:** video mana saja yang punya heatmap. Ini nentuin sinyal kita nanti.

---

## Step 2: Download audio saja

**Tujuan:** ambil bahan untuk sinyal suara, tapi tetap hemat (audio jauh lebih kecil dari video).

**Yang dibuat:** `download_audio(url)` di `src/ingest.py` → `work/<id>/audio.m4a` (atau `.webm`).

**Cara test:** jalankan di 1 video, lalu cek:
```powershell
ffprobe work/<id>/audio.m4a
```

**Lulus kalau:** durasi audio ≈ durasi di `meta.json`, dan ukuran file jauh lebih kecil dari videonya.

---

## Step 3: Loudness per detik + grafik

**Tujuan:** ubah audio jadi angka per detik, lalu **lihat sendiri** apakah puncaknya masuk akal.

**Yang dibuat:**
- `src/signals.py` → `loudness_per_second(audio_path)` dan `heatmap_per_second(heatmap, duration)`
- `src/plot.py` → gambar 2 garis (heatmap + loudness) di 1 grafik → `work/<id>/signals.png`

**Cara test:** buka `signals.png`, lalu buka video di YouTube di detik yang puncak (`?t=<detik>`).

**Lulus kalau:** grafik keluar, dan minimal beberapa puncak memang momen ramai (teriak, ketawa, dll).

> Ini step paling penting di awal. Kalau puncaknya ngaco, kita perbaiki di sini dulu, belum perlu AI apa-apa.

---

## Step 4: Gabung sinyal → top momen

**Tujuan:** dari sinyal-sinyal tadi, keluarkan **daftar 5 timestamp kandidat**.

**Yang dibuat:** `src/score.py` → `smooth`, `zscore`, `combined_score`, `top_moments` (jarak antar momen minimal ~90 detik).
Output: `work/<id>/candidates.json`.

**Cara test:** script print 5 link langsung, contoh `https://youtu.be/<id>?t=1234`. Klik satu per satu.

**Lulus kalau:** dari 5 kandidat, **minimal 2–3 terasa "layak clip"**. Catat hasilnya (kena / tidak) di tabel kecil. Ini jadi eval manual pertama kita.

---

## Step 5: Download potongan video (section)

**Tujuan:** download video **cuma bagian kandidat** (misal 40 detik), bukan full video.

**Yang dibuat:** `download_section(url, start, end, out)` di `src/ingest.py` → `work/<id>/raw_0.mp4`.

**Cara test:** buka `raw_0.mp4`, cek mulai dan selesainya.

**Lulus kalau:** durasi sesuai (±1 detik), gambar dan suara normal, tidak ada frame hitam di awal.

---

## Step 6: Render 9:16 (center crop)

**Tujuan:** clip vertikal pertama, versi paling simpel dulu (tanpa facecam, tanpa caption).

**Yang dibuat:** `src/render.py` → `render_vertical(src, out)` dengan center crop → `out/clip_0.mp4`.

**Cara test:** buka di HP atau player, dan cek resolusinya:
```powershell
ffprobe -v error -show_entries stream=width,height out/clip_0.mp4
```

**Lulus kalau:** 1080x1920, suara ada, bisa diputar normal.

> 🎉 Di titik ini kita sudah punya **link → clip vertikal**. Masih kasar, tapi end-to-end.

---

## Step 7: Transkrip kandidat (timestamp per kata)

**Tujuan:** dapat teks + waktu tiap kata, **cuma di area kandidat** (±60–90 detik), bukan full video.

**Yang dibuat:** `src/transcribe.py` pakai `faster-whisper` (pakai model `small` dulu kalau tanpa GPU).
Output: `work/<id>/transcript_<t>.json`.

**Cara test:** print 20 kata pertama beserta `start` dan `end`-nya, lalu cocokkan dengan video.

**Lulus kalau:** teksnya kebanyakan benar dan timestamp meleset < 0.5 detik.

> Kalau CPU terlalu lambat, catat waktunya. Nanti kita putuskan model mana yang dipakai.

---

## Step 8: Snap ke batas kalimat

**Tujuan:** clip tidak kepotong di tengah omongan.

**Yang dibuat:** `snap_to_sentences(peak, segments)` di `src/select.py`. Hasilnya `start` dan `end` baru untuk Step 5.

**Cara test:** render ulang 1 clip pakai batas baru, lalu bandingkan dengan versi Step 6.

**Lulus kalau:** clip mulai di awal kalimat dan selesai di akhir kalimat, durasinya 15–60 detik.

---

## Step 9: Caption karaoke (.ass) + render

**Tujuan:** caption 3 kata per layar, kata yang sedang diucapkan berwarna kuning.

**Yang dibuat:**
- `src/captions.py` → `build_ass(words, clip_start, clip_end, out)`
- `render_vertical` menerima parameter `ass_path`
- Font tebal (misal Montserrat ExtraBold) di folder `fonts/`

**Cara test:** tonton clip-nya.

**Lulus kalau:** caption sinkron dengan suara, terbaca jelas, tidak keluar layar.

> ⚠️ Di Windows, path `.ass` di ffmpeg suka bermasalah. Pakai path relatif dari folder kerja.

---

## Step 10: Layout facecam + gameplay

**Tujuan:** facecam di atas (1080x640), gameplay di bawah (1080x1280).

**Yang dibuat:**
- Pertama: **preset manual** `presets/<channel>.json` berisi `cam_box: [x, y, w, h]` (lebih stabil, dan lebih gampang dites)
- Setelah itu: auto-detect pakai YuNet (`src/reframe.py`) untuk channel yang belum punya preset

**Cara test:** render 1 clip streamer pakai preset, lalu 1 clip pakai auto-detect.

**Lulus kalau:** wajah streamer utuh di bagian atas, gameplay tidak gepeng.

---

## Step 11: `pipeline.py`: semua jadi satu perintah

**Tujuan:** satu perintah dari link sampai 3 clip jadi.

```powershell
python -m src.pipeline "<link>" --top 3
```

**Yang dibuat:** `src/pipeline.py` yang memanggil Step 1 → 10 berurutan. Pakai cache: kalau file di `work/<id>/` sudah ada, step itu dilewati, jadi kalau ada yang error kita tidak perlu ulang dari awal.

**Lulus kalau:** 3 clip muncul di `out/<id>/` tanpa intervensi manual, dan minimal 2 dari 3 layak upload.

> ✅ Selesai di sini = **MVP Phase 1 jadi.**

---

## Setelah MVP (nanti, satu-satu juga)

Urutan yang disarankan, masing-masing jadi step kecil sendiri:

1. **Twitch:** chat replay → sinyal chat (+ geser ~5 detik karena chat telat)
2. ✅ **LLM refine:** batas clip + skor + judul (output JSON). Claude, lalu Gemini, lalu heuristik kalau tidak ada key atau gagal
   - ✅ **Render dari stream:** tanpa download potongan video, encode sekali
   - ✅ **Efek:** boom + zoom di punchline, judul hook, lagu latar dengan ducking
3. **Eval:** golden set kecil + `precision@k`, supaya perubahan dinilai pakai angka, bukan feeling
4. **Deteksi tawa/teriak:** YAMNet, lebih akurat dari loudness saja
5. **Momen hening:** quiet anomaly + motion + VLM
6. **Phase 3:** orchestrator Rust + worker + Redis Streams
7. **Phase 4:** train ranker sendiri

---

## Catatan hasil test

Isi tiap kali selesai satu step, biar kelihatan progresnya.

| Tanggal | Step | Video yang dites | Hasil | Catatan |
|---|---|---|---|---|
| 2026-11-24 | 0 | - | ✅ | Python 3.12.4, ffmpeg 9.0, yt-dlp 2026.11.23, GPU RTX 3050 Laptop 4GB |
| 2026-11-24 | 1 | `sqWUDQloQm8` (VOD 3j17m, 1jt views) | ✅ | heatmap 100 titik |
| 2026-11-24 | 1 | `cbHDLQhCnkM` (26 menit, 200rb views) | ✅ | heatmap kosong, padahal views lumayan |
| 2026-11-24 | 1 | `KoX-RdIKZIs` (VOD 1 jam, 11 views) | ✅ | heatmap kosong (normal) |
| 2026-11-24 | 2 | `sqWUDQloQm8` | ✅ | audio m4a 183 MB, durasi 11860 s sama dengan metadata, download 2 menit |
| 2026-11-24 | 3 | `sqWUDQloQm8` | ✅ | loudness mentah numpuk di akhir stream (bagian akhir lebih keras). Diganti lonjakan relatif vs median 5 menit, puncak jelas di 1:47:33 (+20 dB). Heatmap condong ke awal video. Cek manual link puncak oleh user |
| 2026-11-24 | 4 | `sqWUDQloQm8` | ✅ | top 5: 0:12:39, 1:47:34, 0:42:41, 0:22:10, 2:05:24. Heatmap di-detrend (median 15 menit) biar tidak condong ke awal |
| 2026-11-24 | 4 | `cbHDLQhCnkM` | ✅ | fallback audio saja jalan. Kena/tidak perlu dicek manual |
| 2026-11-24 | 5 | `sqWUDQloQm8` 1:46:59 - 1:47:39 | ✅ | durasi pas 40.000 s, 1080p60, 15 MB, 35 detik. Frame awal tidak hitam. VOD ini tanpa facecam |
| 2026-11-24 | 6 | `sqWUDQloQm8` | ✅ | 1080x1920 30fps + aac, NVENC: render 40 s dalam 6 s |
| 2026-11-24 | 7 | `AHtPn8fmJ2Y` t=1:21:44 | ✅ | large-v3-turbo int8 di RTX 3050: window 120 s dalam 7.4 s. Teks dan timestamp akurat. Model di-download manual ke `models/` (download HF Xet macet). Audio di-decode pakai ffmpeg karena PyAV tidak cocok. Temuan: kandidat ini 67/120 detik hening, isinya obrolan biasa |
| 2026-11-24 | fix | `AHtPn8fmJ2Y`, `sqWUDQloQm8` | ✅ | baseline lonjakan tidak lagi ikut detik hening (break/mute). Kandidat palsu di menit 50 sampai 85 Jynxzi hilang. Dicek pakai transkrip: 4:04:40 ada reaksi, 2:37 (catur) dan 3:54 (iklan game) kurang menarik, butuh LLM refine nanti |
| 2026-11-24 | 8 | `AHtPn8fmJ2Y` t=4:04:40, `sqWUDQloQm8` t=12:24 | ✅ | clip 43.1 s dan 51.2 s, mulai di awal kalimat, selesai di akhir kalimat. Dites juga dengan data palsu: kosong, kalimat sangat panjang, terlalu pendek |
| 2026-11-24 | fix | `AHtPn8fmJ2Y` | ✅ | download section Jynxzi macet / ffmpeg crash karena yt-dlp tidak punya JS runtime (YouTube throttle). Aktifkan node + `yt-dlp[default]` (yt-dlp-ejs): 43 s 1080p60 selesai 44 s |
| 2026-11-24 | 9 | `AHtPn8fmJ2Y` t=4:04:40 | ✅ | 46 kata, Montserrat ExtraBold, kata aktif kuning + pop, chunk baru kalau jeda > 1 s. Render 43 s dalam 6 s. Path ass dibuat relatif (cwd) supaya aman di Windows |
| 2026-11-24 | 10 | `AHtPn8fmJ2Y` (facecam kanan bawah), `sqWUDQloQm8` (tanpa facecam) | ✅ | YuNet 30/30 frame kena, wajah 191x240. Kotak awal (3.2x wajah) kebesaran, diganti 1.6x tinggi wajah: (1272, 580, 646, 382). Gameplay digeser menjauhi facecam. SMii7Y benar terdeteksi None, jadi center crop. Preset `presets/jynxzi.json` |
| 2026-11-24 | 11 | `AHtPn8fmJ2Y` --top 3 | ✅ | 3 clip layout facecam (preset Jynxzi) dalam 148 s: 5:35:26 (49 s), 4:04:29 (28 s), 2:36:57 (38 s, catur). Momen hening (< 0.5 kata/s) dilewati |
| 2026-11-24 | 11 | `sqWUDQloQm8` --top 2 | ✅ | 2 clip center crop (tanpa facecam) dalam 104 s. **MVP Phase 1 selesai** |
| 2026-11-24 | refine | `AHtPn8fmJ2Y` --top 3 | ✅ | Belum ada API key, jadi jalur heuristik: panjang clip ikut isi (32 s, 14 s, 15 s), bukan rata 30 s+. Momen "Bitched, bitched" sebelumnya kebuang sebagai hening (26 kata/60 s), batas hening diturunkan ke 0.25 kata/s. Jalur Claude dites pakai jawaban tiruan, belum dengan API asli |
| 2026-11-24 | stream | `AHtPn8fmJ2Y` --top 3 | ✅ | Downloader potongan yt-dlp gagal lagi (ffmpeg exit 2812791304). Link HTTPS langsung juga 403 untuk ffmpeg, HLS selalu 206. Video dari HLS (H.264), audio dari file lokal. Render per clip 4 sampai 12 s, tanpa file raw. Frame dicek sama dengan hasil download lama |
| 2026-11-24 | fx | `AHtPn8fmJ2Y` t=4:04:43 | ✅ | Judul kotak putih 3 s, zoom 14% di punchline, boom terdengar (puncak -4 dB vs -22 dB di sekitarnya). Lagu dummy di-loop + ducking, durasi audio = video |
| 2026-11-25 | gemini | `AHtPn8fmJ2Y` --top 3 | ✅ | Claude API ditolak (saldo kosong), otomatis pindah ke Gemini. `gemini-3.8-flash` sibuk (503), dipakai `gemini-3.5-flash`. Dari 9 kandidat hanya 2 dianggap layak (16 s dan 26 s), lengkap dengan judul. Momen GTA yang tadinya lolos heuristik dibuang. Render via stream 13 sampai 16 s per clip |
| 2026-11-25 | facecam | `TrduzvbeIBk` --top 3 | ✅ | Link baru langsung dari stream, tanpa download video (hanya audio untuk analisis). Gemini pilih 5 dari 9 kandidat (33 s, 38 s, 15 s). Preset Jynxzi (kamera kanan) salah untuk video reaksi ini (kamera kiri bawah), panel atas berisi game. Sekarang wajah selalu dicek dari potongan 20 s, preset hanya dipakai kalau wajahnya ada di dalam kotak preset |
| 2026-11-25 | scan | `TrduzvbeIBk` --top 3 | ✅ | Transkrip seluruh video (38 menit, sekitar 50 s di GPU), Gemini baca per 30 menit dan usulkan 7 momen. Digabung dengan 7 puncak sinyal jadi 14 kandidat, refine meloloskan 8 (sebelumnya 5 dari 9). Dua clip teratas ("green drink" dan "revive musuh") berasal dari scan dan tidak pernah tertangkap sinyal suara. Total 129 s. Model Gemini yang menggantung sekarang dilewati |
