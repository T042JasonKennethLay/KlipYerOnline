"""Pilih kandidat yang benar-benar menarik dan tentukan batas clip yang pas.

LLM membaca transkrip semua kandidat sekaligus, membuang yang membosankan, lalu memilih awal (hook),
akhir (setelah punchline), detik punchline, dan judul. Provider dicoba berurutan sesuai key di .env:
    ANTHROPIC_API_KEY  -> Claude (bayar per pemakaian)
    GEMINI_API_KEY     -> Gemini (ada free tier)
Kalau semua gagal atau tidak ada key: heuristik, batas kalimat lebih ketat dan punchline = detik paling keras.

    python -m src.refine <video_id>      # pakai transcript_*.json yang sudah ada di work/<id>/
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np

from src.boundaries import snap_to_sentences, words_in
from src.paths import ROOT, work_dir

CLAUDE_MODEL = os.getenv("CLIP_LLM_MODEL", "claude-opus-5-5")
# Model pertama yang tidak sibuk yang dipakai (free tier sering kena 503/429 saat ramai).
GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.5-flash", "gemini-3.8-flash",
                             "gemini-flash-latest", "gemini-flash-lite-latest"] if m]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
MIN_LEN, MAX_LEN = 6.0, 60.0
TAIL = 0.35          # sisa sedikit setelah kata terakhir supaya tidak kepotong

SYSTEM = """You edit livestream VODs into vertical short clips (TikTok, YouTube Shorts).
You get transcripts of candidate moments that were picked because the audio got loud.
Loud does not mean good: many are ordinary talk, game sounds, chess, music, or sponsor reads.

For every candidate decide:
- keep: true only if a stranger scrolling Shorts would understand it without context and get a
  payoff (a joke, a reaction, a fail, a rage moment, a surprising line). Reject ads, sponsor
  reads, idle chat, reading chat names, singing along, and moments that need earlier context.
- score: 0 to 10, how likely it is to hold a viewer to the end.
- start: absolute second where the clip should begin. Start on the setup line that hooks the
  viewer, never in the middle of a sentence, and skip dead air before it.
- end: absolute second right after the payoff and the immediate reaction. Cut as soon as the
  energy drops.
- punchline: absolute second of the single funniest or loudest beat (a sound effect goes there).
- title: Shorts title in Gen Z internet humor, like the top clip channels (examples are given when
  available). Lowercase and casual, 2 to 7 words, at most 45 characters. It is a gimmick, not a
  summary: ironic, dramatic, or deadpan, and it makes people curious about the payoff. Patterns
  that work: "bro thought he was him 💀", "he's cooked 💀🥀", "it's over for him 🥀",
  "nah bro was NOT ready 😭", "-1000 aura 💀", "chat is this real 🥀", "pain. 🥀", a quoted line
  from the clip like "\"i don't know him\" 💀💀", or "speed did kai dirty 😭😭". Use 💀 for
  absurd or brutal moments and 🥀 (wilted rose) for losses, fails, sadness, or someone getting
  humbled; 😭 and 🙏 also fit. One or two emojis at the end, one word in CAPS is fine.
  No hashtags. Do not invent things that are not in the transcript.
- reason: one short sentence.

Length must follow the content, not a target. A quick reaction can be 7 to 15 seconds, a normal
bit 15 to 30, a story up to 60. Shorter is better whenever the payoff still lands; clips that drag
lose viewers. Use only times that appear in the transcript."""

SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "score": {"type": "integer"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "punchline": {"type": "number"},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "keep", "score", "start", "end", "punchline", "title", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def load_env() -> None:
    """Baca .env sederhana (KEY=VALUE) tanpa menimpa env yang sudah ada."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def providers() -> list[str]:
    """Provider LLM yang key-nya ada, urut prioritas."""
    load_env()
    out = []
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            out.append("claude")
        except ImportError:
            pass
    if os.getenv("GEMINI_API_KEY"):
        out.append("gemini")
    return out


# ---------- bantuan umum ----------

def loud_peak(video_id: str, start: float, end: float) -> float:
    """Detik paling keras di dalam clip (dari loudness.npy), dipakai sebagai punchline cadangan."""
    p = work_dir(video_id) / "loudness.npy"
    if not p.exists():
        return (start + end) / 2
    loud = np.load(p)
    a, b = int(start), min(int(end) + 1, len(loud))
    if b <= a:
        return (start + end) / 2
    return float(a + int(np.argmax(loud[a:b])))


def snap_to_words(segments: list[dict], start: float, end: float) -> tuple[float, float]:
    """Rapatkan batas ke kata: mulai di kata pertama, selesai sedikit setelah kata terakhir."""
    words = [w for s in segments for w in s.get("words", [])]
    inside = [w for w in words if w["start"] >= start - 0.3 and w["end"] <= end + 0.5]
    if not inside:
        return start, end
    return round(inside[0]["start"], 2), round(inside[-1]["end"] + TAIL, 2)


def clamp_len(start: float, end: float, peak: float) -> tuple[float, float]:
    if end - start > MAX_LEN:
        start = max(start, peak - MAX_LEN / 2)
        end = start + MAX_LEN
    if end - start < MIN_LEN:
        end = start + MIN_LEN
    return start, end


def render_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in segments)


# ---------- jalur heuristik ----------

def heuristic(video_id: str, cands: list[dict]) -> list[dict]:
    """Tanpa LLM: batas kalimat lebih rapat (bukan 35 s rata), panjang ikut isi omongan."""
    out = []
    for c in cands:
        segs = c["segments"]
        peak = loud_peak(video_id, c["t"] - 10, c["t"] + 10)
        start, end = snap_to_sentences(peak, segs, pre=8, post=5, min_len=8, max_len=45)
        start, end = snap_to_words(segs, start, end)
        out.append({**c, "start": start, "end": end, "punchline": loud_peak(video_id, start, end),
                    "title": "", "reason": "heuristik", "llm_score": None})
    return sorted(out, key=lambda c: -c["score"])


# ---------- jalur LLM ----------

def build_prompt(cands: list[dict]) -> str:
    blocks = [f"<candidate id=\"{i}\" center=\"{c['t']}\">\n{render_transcript(c['segments'])}\n</candidate>"
              for i, c in enumerate(cands)]
    from src.trends import title_examples

    examples = title_examples()
    style = ("Titles of top performing streamer clip Shorts right now (style reference only, do not copy):\n"
             + "\n".join(f"- {t}" for t in examples) + "\n\n") if examples else ""
    return (style + "Candidates (times are absolute seconds in the VOD):\n\n" + "\n\n".join(blocks)
            + "\n\nReturn one entry per candidate id.")


def ask_claude(system: str, prompt: str, schema: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude menolak: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("jawaban Claude terpotong (max_tokens)")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def ask_gemini(system: str, prompt: str, schema: dict) -> dict:
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema},
    }).encode()
    for attempt in range(2):
        try:
            return gemini_once(body)
        except RateLimited as e:
            if attempt:
                raise RuntimeError(str(e)) from None
            print("  gemini kena limit per menit, tunggu 60 s lalu coba lagi", flush=True)
            time.sleep(60)


class RateLimited(RuntimeError):
    pass


def gemini_once(body: bytes) -> dict:
    errors = []
    for model in dict.fromkeys(GEMINI_MODELS):
        req = urllib.request.Request(GEMINI_URL.format(model), data=body,
                                     headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                              "Content-Type": "application/json"})
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as e:
            errors.append(f"{model} HTTP {e.code}")
            if e.code in (404, 429, 500, 503):    # tidak ada / limit / sibuk: coba model berikutnya
                continue
            raise RuntimeError(f"Gemini {model} HTTP {e.code}: {e.read()[:300]!r}") from None
        except (TimeoutError, ConnectionError, urllib.error.URLError, OSError) as e:
            errors.append(f"{model} {type(e).__name__}")    # menggantung / koneksi putus
            continue
        print(f"  llm pakai {model}", flush=True)
        return parse_gemini(resp)
    msg = "semua model Gemini gagal: " + ", ".join(errors)
    if any("429" in e or "503" in e for e in errors):
        raise RateLimited(msg)
    raise RuntimeError(msg)


def parse_gemini(resp: dict) -> list[dict]:
    cands = resp.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini tidak menjawab: {resp.get('promptFeedback')}")
    if cands[0].get("finishReason") != "STOP":
        raise RuntimeError(f"jawaban Gemini berhenti: {cands[0].get('finishReason')}")
    text = "".join(p.get("text", "") for p in cands[0]["content"]["parts"] if not p.get("thought"))
    return json.loads(text)


ASK = {"claude": ask_claude, "gemini": ask_gemini}
DEAD: set[str] = set()


def ask_json(system: str, prompt: str, schema: dict, cache) -> tuple[dict | None, str]:
    """Coba provider berurutan, simpan jawaban di `cache`. Return (jawaban atau None, nama provider)."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), "cache"
    for name in providers():
        if name in DEAD:
            continue
        try:
            answer = ASK[name](system, prompt, schema)
        except Exception as e:  # saldo habis, limit, jaringan: coba provider berikutnya
            msg = str(e)
            print(f"  {name} gagal: {msg[:160]}", flush=True)
            if any(k in msg.lower() for k in ("credit balance", "api key", "authentication", "permission")):
                DEAD.add(name)    # tidak akan berhasil selama proses ini, jangan dicoba lagi
            continue
        cache.write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
        return answer, name
    return None, "heuristik"


def apply_llm(video_id: str, cands: list[dict], answers: list[dict]) -> list[dict]:
    out = []
    for a in answers:
        i = a.get("id")
        if not isinstance(i, int) or not 0 <= i < len(cands) or not a.get("keep"):
            continue
        c = cands[i]
        segs = c["segments"]
        lo, hi = segs[0]["start"], segs[-1]["end"]
        start = float(np.clip(a["start"], lo, hi))
        end = float(np.clip(a["end"], start + 1, hi))
        start, end = snap_to_words(segs, start, end)
        punch = float(a["punchline"]) if start <= a["punchline"] <= end else loud_peak(video_id, start, end)
        start, end = clamp_len(start, end, punch)
        out.append({**c, "start": round(start, 2), "end": round(end, 2), "punchline": round(punch, 2),
                    "title": a["title"].strip(), "reason": a["reason"], "llm_score": a["score"]})
    return sorted(out, key=lambda c: (-c["llm_score"], -c["score"]))


def drop_overlaps(clips: list[dict], max_overlap: float = 0.3) -> list[dict]:
    """Clip sudah urut terbaik dulu. Buang yang sebagian besar isinya sama dengan clip yang lebih baik."""
    kept = []
    for c in clips:
        dur = c["end"] - c["start"]
        if all(min(c["end"], k["end"]) - max(c["start"], k["start"]) <= max_overlap * dur for k in kept):
            kept.append(c)
    return kept


def refine(video_id: str, cands: list[dict], context: str = "") -> tuple[list[dict], str]:
    """cands: [{"t", "score", "segments"}]. Return (clip terurut terbaik dulu, mode yang dipakai).
    context: info video (judul, channel) supaya LLM paham konteksnya."""
    if not cands:
        return [], "kosong"
    prompt = (context + "\n\n" if context else "") + build_prompt(cands)
    key = hashlib.sha1(prompt.encode()).hexdigest()[:10]
    answer, name = ask_json(SYSTEM, prompt, SCHEMA, work_dir(video_id) / f"refine_{key}.json")
    if answer is None:
        return drop_overlaps(heuristic(video_id, cands)), "heuristik"
    return drop_overlaps(apply_llm(video_id, cands, answer["clips"])), name


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("usage: python -m src.refine <video_id>")
        sys.exit(1)
    vid = argv[1]
    cands = []
    for p in sorted(work_dir(vid).glob("transcript_*_60.json")):
        t = int(p.stem.split("_")[1])
        cands.append({"t": t, "score": 0.0, "segments": json.loads(p.read_text(encoding="utf-8"))})
    clips, mode = refine(vid, cands)
    print(f"mode: {mode}, {len(clips)} dari {len(cands)} kandidat dipakai")
    for c in clips:
        n = len(words_in(c["segments"], c["start"], c["end"]))
        print(f"  {c['start']:.1f}-{c['end']:.1f} ({c['end'] - c['start']:.0f}s, {n} kata) "
              f"punch {c['punchline']:.1f} skor {c['llm_score']} {c['title']!r} | {c['reason']}")


if __name__ == "__main__":
    main(sys.argv)
