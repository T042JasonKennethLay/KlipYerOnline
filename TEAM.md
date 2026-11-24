# Pembagian Tugas

Project ini dikerjakan berdua. Supaya kerjaan tidak nabrak, pembagiannya **per folder**, dan dua bagian hanya nyambung lewat **satu fungsi kontrak**.

| | Orang A (Jason) | Orang B (teman) |
|---|---|---|
| Bagian | Pipeline clip: audio, scoring, transkrip, caption, render | **Sinyal penonton**: bagian video mana yang paling banyak ditonton |
| Folder / file milik sendiri | `src/` (semua **kecuali** `src/viewers/`), `STEPS.md` | `src/viewers/`, `tests/viewers/`, `docs/viewers.md` |
| Prefix branch | `feat/step-XX-*` | `feat/viewers-*` |

> Aturan utama: **jangan edit file milik orang lain.** Kalau butuh perubahan di sana, bilang ke pemiliknya atau buka issue.

---

## Kontrak (titik sambung)

File: `src/viewers/__init__.py`

```python
@dataclass
class ViewerSignal:
    source: str               # "heatmap" | "analytics" | sumber lain
    per_second: np.ndarray    # float, panjang int(duration) + 1, nilai 0..1
    points: list[dict]        # data mentah [{"start", "end", "value"}]


def get_viewer_signal(meta: dict) -> ViewerSignal | None: ...
```

- **Input** `meta`: hasil `src.ingest.fetch_metadata(url)`. Key yang pasti ada: `id`, `url`, `title`, `channel`, `duration`, `extractor`, `heatmap`.
- **Output:**
  - `per_second[i]` = seberapa ramai detik ke-`i` ditonton, **dinormalisasi 0..1**
  - Panjangnya **harus** `int(duration) + 1`
  - Return `None` kalau tidak ada data sama sekali. Pipeline otomatis fallback ke audio saja.
- **Pemakai:** `src/score.py` (milik A) memanggil `get_viewer_signal(meta)` lalu memakai `per_second`. A tidak peduli datanya dari mana.

Kalau kontrak perlu diubah (misal tambah field), **diskusi dulu**. Menambah field baru yang opsional itu aman, sedangkan mengubah atau menghapus field yang sudah ada itu breaking.

Versi sekarang di `src/viewers/__init__.py` sudah jalan: dia mengambil heatmap publik dari yt-dlp. Tugas B adalah mengembangkan bagian dalamnya **tanpa mengubah signature**.

---

## Tugas B: sinyal penonton

### Dua sumber data, dua kondisi

| Sumber | Bisa untuk video siapa? | Isi | Catatan |
|---|---|---|---|
| **Heatmap publik "Most Replayed"** | Video siapa saja | 100 titik, nilai 0..1 | Tidak semua video punya (butuh views cukup). Contoh: stream Jynxzi `AHtPn8fmJ2Y` **tidak** punya heatmap |
| **YouTube Analytics API v2** | **Hanya channel milik sendiri** (atau creator yang login OAuth ke app kita) | `audienceWatchRatio`, `relativeRetentionPerformance`, `startedWatching`, `stoppedWatching` per `elapsedVideoTimeRatio` (100 titik) | Butuh OAuth pemilik channel, ada delay 1 sampai 2 hari, butuh cukup views |

> ⚠️ Retensi / watch time asli **tidak bisa** diambil untuk video orang lain. Untuk video orang lain, yang tersedia cuma heatmap publik.

### Langkah kerja (kecil-kecil, sama seperti STEPS.md)

| # | Branch | Isi | Lulus kalau |
|---|---|---|---|
| B1 | `feat/viewers-heatmap` | Rapikan heatmap publik: normalisasi 0..1, validasi panjang, simpan `work/<id>/viewers.json` | Tes 3 video (populer, kecil, stream panjang) dan `per_second` panjangnya benar |
| B2 | `feat/viewers-cli` | `python -m src.viewers <url>` print sumber, jumlah titik, top 5 timestamp + link `?t=` | Link puncaknya bisa diklik dan dicek manual |
| B3 | `feat/viewers-analytics-auth` | OAuth YouTube Analytics (scope `yt-analytics.readonly`), token disimpan lokal | Bisa login pakai channel sendiri, token **tidak** ter-commit |
| B4 | `feat/viewers-analytics-retention` | Query retensi 100 titik → `per_second`. Cari bagian yang **ditonton ulang**: retensi normal selalu turun, jadi yang naik berarti rewatch (pakai isotonic regression, lihat design doc bagian 7.3) | Tes di 1 video channel sendiri, puncaknya masuk akal |
| B5 | `feat/viewers-merge` | Kalau dua sumber ada, pakai Analytics (lebih kaya); kalau tidak, heatmap; kalau tidak ada dua-duanya, `None` | `source` sesuai kondisi |
| B6 | `feat/viewers-tests` | Unit test di `tests/viewers/` pakai data palsu (tanpa internet) | `pytest tests/viewers` hijau |

### Yang **tidak** perlu dikerjakan B

- Scoring / bobot gabungan (di `src/score.py`, milik A)
- Detrend heatmap (sudah ada di `score.py`)
- Download audio / video, transkrip, render

---

## Alur Git

```
main          ← versi stabil, cuma di-merge dari develop
 └─ develop   ← tempat gabung kerjaan A dan B
     ├─ feat/step-07-transcribe   (A)
     └─ feat/viewers-heatmap      (B)
```

1. Sebelum mulai satu langkah:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feat/viewers-heatmap
   ```
2. Commit kecil-kecil pakai Conventional Commits:
   - `feat(viewers): normalize heatmap to per second signal`
   - `fix(viewers): handle video without duration`
   - `test(viewers): add heatmap contract tests`
   - `docs(viewers): explain analytics oauth setup`
3. Push branch, lalu buka **Pull Request ke `develop`** di GitHub.
4. Orang yang satunya **review** dulu, baru di-merge. Jangan merge PR sendiri tanpa dilihat.
5. Setelah di-merge, hapus branch-nya, lalu `git pull origin develop` sebelum mulai langkah berikutnya.

Kalau ada konflik di file milik orang lain, berarti ada yang melanggar pembagian folder. Selesaikan bareng, jangan asal pilih "accept mine".

---

## Setup untuk B

```powershell
git clone https://github.com/T042JasonKennethLay/KlipYerOnline.git
cd KlipYerOnline
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.ingest "https://www.youtube.com/watch?v=sqWUDQloQm8"
```

Library tambahan untuk Analytics (B3 sampai B4), tambahkan ke `requirements.txt` di branch B:
`google-api-python-client`, `google-auth-oauthlib`, `scikit-learn`.

### Secret: jangan sampai ter-commit

- `client_secret*.json` (dari Google Cloud Console) dan file token OAuth sudah masuk `.gitignore`
- Simpan token di `work/` atau `.secrets/` (tambahkan `.secrets/` ke `.gitignore` kalau dipakai)
- Sebelum push, cek dulu pakai `git status`

---

## Video untuk testing bersama

| ID | Isi | Heatmap |
|---|---|---|
| `sqWUDQloQm8` | SMii7Y VOD 3j17m, 1 jt views | ✅ 100 titik |
| `cbHDLQhCnkM` | 26 menit, 200 rb views | ❌ |
| `AHtPn8fmJ2Y` | Jynxzi GTA 6 stream 5j50m | ❌ |
| (channel sendiri) | untuk tes Analytics | - |
