# Pembagian Tugas: KY & KO

| Kode | Orang | Pegang bagian |
|---|---|---|
| **KY** | Jason (dibantu Claude) | **Pipeline clip**: audio, scoring, transkrip, caption, render |
| **KO** | Teman | **Sinyal penonton**: bagian video mana yang paling banyak ditonton (heatmap + YouTube Analytics) |

Aturan paling penting: **jangan edit file milik orang lain.** Kalau butuh perubahan di file orang lain, chat dulu ke pemiliknya.

---

## 📌 Papan status (update setiap mulai / selesai kerja)

> Sebelum mulai kerja: `git pull origin develop`, lalu baca tabel ini dulu.
> Setelah selesai satu langkah: update tabel ini di PR kamu.

### KY sedang mengerjakan

| | |
|---|---|
| Langkah | **Step 7: transkrip kandidat (faster-whisper, timestamp per kata)** |
| Branch | `feat/step-07-transcribe` |
| File yang sedang dipegang | `src/transcribe.py` (baru), `requirements.txt`, `STEPS.md` |
| Berikutnya | Step 8 snap kalimat → Step 9 caption → Step 10 facecam → Step 11 pipeline |

### KO sedang mengerjakan

| | |
|---|---|
| Langkah | **K1: rapikan heatmap publik** (lihat daftar tugas KO di bawah) |
| Branch | `feat/viewers-heatmap` |
| File yang boleh dipegang | `src/viewers/` (semua isinya), `tests/viewers/` |
| Berikutnya | K2 CLI → K3 OAuth → K4 retensi → K5 gabung sumber → K6 test |

---

## 🗂️ Kepemilikan file

| File / folder | Pemilik | KY boleh edit? | KO boleh edit? |
|---|---|---|---|
| `src/viewers/` | **KO** | ❌ jangan | ✅ |
| `tests/viewers/` | **KO** | ❌ jangan | ✅ |
| `src/ingest.py` | KY | ✅ | ❌ jangan (cukup **dipakai**: `fetch_metadata`) |
| `src/signals.py` | KY | ✅ | ❌ jangan |
| `src/score.py` | KY | ✅ | ❌ jangan (dia yang **memanggil** fungsi KO) |
| `src/plot.py`, `src/render.py`, `src/transcribe.py` | KY | ✅ | ❌ jangan |
| `src/paths.py` | KY | ✅ | ❌ jangan (cukup **dipakai**: `work_dir`) |
| `STEPS.md` | KY | ✅ | ❌ jangan |
| `TEAM.md` | Berdua | ✅ hanya baris **KY** di papan status | ✅ hanya baris **KO** di papan status |
| `requirements.txt` | Berdua | ✅ tambah baris saja | ✅ tambah baris saja |
| `.gitignore` | Berdua | ✅ tambah baris saja | ✅ tambah baris saja |
| `README.md`, design doc | KY | ✅ | ❌ jangan |

File "berdua" sering bikin konflik kecil. Aturannya: **cuma boleh menambah baris, jangan mengubah atau menghapus baris orang lain.**

---

## 🔌 Kontrak: satu-satunya titik sambung KY ↔ KO

File: `src/viewers/__init__.py` (milik KO)

```python
@dataclass
class ViewerSignal:
    source: str               # "heatmap" | "analytics" | sumber lain
    per_second: np.ndarray    # float, panjang int(duration) + 1, nilai 0..1
    points: list[dict]        # data mentah [{"start", "end", "value"}]


def get_viewer_signal(meta: dict) -> ViewerSignal | None: ...
```

```
KY: src/ingest.py ──meta──► KO: get_viewer_signal(meta) ──ViewerSignal──► KY: src/score.py
```

| | Isi |
|---|---|
| Input `meta` | Hasil `fetch_metadata(url)`. Key yang pasti ada: `id`, `url`, `title`, `channel`, `duration`, `extractor`, `heatmap` |
| Output `per_second[i]` | Seberapa ramai detik ke-`i` ditonton, **0..1**. Panjangnya **wajib** `int(duration) + 1` |
| Kalau tidak ada data | Return `None`. Pipeline KY otomatis fallback ke audio saja |

**Aturan kontrak:**
- KO bebas mengubah **isi** fungsi, asal **signature dan format output tetap sama**.
- Menambah field baru yang opsional itu aman. Mengubah atau menghapus field yang sudah ada **harus diskusi dulu** dengan KY.
- KY **tidak** mengedit `src/viewers/`. Kalau KY butuh sesuatu dari KO, minta lewat chat atau issue.

Versi sekarang sudah jalan: fungsinya mengambil heatmap publik dari yt-dlp. Jadi KY bisa terus kerja tanpa menunggu KO.

---

## 📋 Daftar tugas KO

### Dulu pahami dua sumber datanya

| Sumber | Bisa untuk video siapa? | Isi | Catatan |
|---|---|---|---|
| **Heatmap publik "Most Replayed"** | Video siapa saja | 100 titik, nilai 0..1 | Tidak semua video punya. Contoh: stream Jynxzi `AHtPn8fmJ2Y` **tidak** punya |
| **YouTube Analytics API v2** | **Hanya channel milik sendiri** (yang login OAuth) | `audienceWatchRatio`, `relativeRetentionPerformance`, `startedWatching`, `stoppedWatching`, 100 titik | Ada delay 1 sampai 2 hari, butuh cukup views |

> ⚠️ Watch time / retensi asli **tidak bisa** diambil untuk video orang lain. Untuk video orang lain, yang ada cuma heatmap publik. Jadi untuk tes Analytics, KO butuh video dari **channel YouTube sendiri**.

### Langkahnya (satu langkah = satu branch = satu PR)

| # | Branch | Isi | Lulus kalau | Status |
|---|---|---|---|---|
| K1 | `feat/viewers-heatmap` | Rapikan heatmap publik: normalisasi 0..1, validasi panjang `per_second`, simpan `work/<id>/viewers.json` | Tes 3 video tabel di bawah, panjang `per_second` benar | ⬜ |
| K2 | `feat/viewers-cli` | `python -m src.viewers <url>`: print sumber, jumlah titik, top 5 timestamp + link `?t=` | Link puncak bisa diklik dan dicek manual | ⬜ |
| K3 | `feat/viewers-analytics-auth` | OAuth YouTube Analytics (scope `yt-analytics.readonly`), token disimpan di `.secrets/` | Bisa login pakai channel sendiri, token **tidak** ter-commit | ⬜ |
| K4 | `feat/viewers-analytics-retention` | Query retensi 100 titik → `per_second`. Cari bagian yang **ditonton ulang**: retensi normal selalu turun, jadi yang naik = rewatch (isotonic regression, lihat design doc bagian 7.3) | Tes di 1 video channel sendiri, puncaknya masuk akal | ⬜ |
| K5 | `feat/viewers-merge` | Ada Analytics → pakai Analytics. Tidak ada → heatmap. Dua-duanya tidak ada → `None` | `source` sesuai kondisi | ⬜ |
| K6 | `feat/viewers-tests` | Unit test di `tests/viewers/` pakai data palsu (tanpa internet) | `pytest tests/viewers` hijau | ⬜ |

### Yang **tidak** perlu dikerjakan KO

- Bobot gabungan dan pemilihan kandidat (`src/score.py`, milik KY)
- Detrend heatmap (sudah ada di `score.py`)
- Download audio / video, transkrip, caption, render

---

## 📋 Daftar tugas KY

Ikuti [`STEPS.md`](STEPS.md). Ringkasnya:

| # | Branch | Isi | Status |
|---|---|---|---|
| 0 sampai 6 | `feat/step-00-setup` sampai `feat/step-06-render` | Setup, metadata, audio, loudness, scoring, download potongan, render 9:16 | ✅ |
| 7 | `feat/step-07-transcribe` | Transkrip kandidat | 🟨 |
| 8 | `feat/step-08-snap` | Snap ke batas kalimat | ⬜ |
| 9 | `feat/step-09-captions` | Caption karaoke | ⬜ |
| 10 | `feat/step-10-facecam` | Layout facecam + gameplay | ⬜ |
| 11 | `feat/step-11-pipeline` | Satu perintah: link → 3 clip | ⬜ |

---

## 🌿 Alur Git

```
main          ← versi stabil, cuma di-merge dari develop
 └─ develop   ← tempat gabung kerjaan KY dan KO
     ├─ feat/step-07-transcribe   (KY)
     └─ feat/viewers-heatmap      (KO)
```

1. **Sebelum mulai:**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feat/viewers-heatmap
   ```
2. **Update papan status** di `TEAM.md` (baris kamu sendiri saja).
3. **Commit kecil-kecil** pakai Conventional Commits:
   - `feat(viewers): normalize heatmap to per second signal`
   - `fix(viewers): handle video without duration`
   - `test(viewers): add heatmap contract tests`
4. **Push branch**, lalu buka **Pull Request ke `develop`** di GitHub.
5. **Review silang:** PR KO di-review KY, PR KY di-review KO. Jangan merge PR sendiri tanpa dilihat.
6. Setelah merge: hapus branch, lalu `git pull origin develop` sebelum mulai langkah berikutnya.

Kalau sampai ada konflik di file milik orang lain, berarti ada yang melanggar tabel kepemilikan. Selesaikan bareng, jangan asal pilih "accept mine".

---

## 🛠️ Setup untuk KO

```powershell
git clone https://github.com/T042JasonKennethLay/KlipYerOnline.git
cd KlipYerOnline
git checkout develop
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.ingest "https://www.youtube.com/watch?v=sqWUDQloQm8"
```

Library tambahan untuk Analytics (K3 sampai K4). Tambahkan ke `requirements.txt` di branch KO:
`google-api-python-client`, `google-auth-oauthlib`, `scikit-learn`.

### Secret: jangan sampai ter-commit

- `client_secret*.json` (dari Google Cloud Console) dan token OAuth simpan di `.secrets/`. Folder ini sudah masuk `.gitignore`.
- Sebelum push, selalu cek pakai `git status`.

---

## 🎬 Video untuk testing bersama

| ID | Isi | Heatmap |
|---|---|---|
| `sqWUDQloQm8` | SMii7Y VOD 3j17m, 1 jt views | ✅ 100 titik |
| `cbHDLQhCnkM` | 26 menit, 200 rb views | ❌ |
| `AHtPn8fmJ2Y` | Jynxzi GTA 6 stream 5j50m | ❌ |
| (channel sendiri KO / KY) | untuk tes Analytics | - |
