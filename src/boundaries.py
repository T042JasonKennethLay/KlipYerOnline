"""Tentukan batas clip supaya tidak kepotong di tengah omongan."""

MIN_LEN = 15.0
MAX_LEN = 60.0


def snap_to_sentences(peak: float, segments: list[dict], pre: float = 20, post: float = 15,
                      min_len: float = MIN_LEN, max_len: float = MAX_LEN) -> tuple[float, float]:
    """Mulai di awal kalimat sebelum (peak - pre), selesai di akhir kalimat setelah (peak + post).

    segments: [{"start", "end", "text"}] dalam detik absolut video, urut waktu.
    """
    st_target, en_target = peak - pre, peak + post
    if not segments:
        return round(max(st_target, 0.0), 2), round(en_target, 2)

    starts = [s["start"] for s in segments if s["start"] <= st_target]
    start = max(starts) if starts else min(segments[0]["start"], max(st_target, 0.0))
    start = max(start, peak - max_len + post)

    ends = [s["end"] for s in segments if s["end"] >= en_target]
    end = min(ends) if ends else max(en_target, segments[-1]["end"])

    if end - start > max_len:
        inside = [s["end"] for s in segments if peak < s["end"] <= start + max_len]
        end = max(inside) if inside else start + max_len
    if end - start < min_len:
        longer = [s["end"] for s in segments if s["end"] >= start + min_len]
        end = min(longer) if longer and min(longer) - start <= max_len else start + min_len
    return round(max(start, 0.0), 2), round(end, 2)


def words_in(segments: list[dict], start: float, end: float) -> list[dict]:
    return [w for s in segments for w in s.get("words", []) if start <= w["start"] < end]
