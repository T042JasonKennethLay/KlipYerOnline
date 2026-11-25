"""Upload clip hasil pipeline ke channel YouTube kamu (YouTube Data API v3, OAuth).

Persiapan sekali (lihat README bagian Upload ke YouTube):
    .secrets/client_secret.json   OAuth client "Desktop app" dari Google Cloud Console
Login pertama membuka browser, token disimpan di .secrets/youtube_token.json (tidak di-commit).

    python -m src.upload <video_id>                     # semua clip, private (default)
    python -m src.upload <video_id> --only 1,3          # clip nomor 1 dan 3 saja
    python -m src.upload <video_id> --privacy unlisted  # private | unlisted | public
    python -m src.upload <video_id> --dry-run           # tampilkan judul dan deskripsi saja

Clip yang sudah ter-upload dicatat di out/<id>/clips.json (youtube_id), jadi tidak di-upload dua kali.
"""
import argparse
import json
import re
import sys

from src.paths import ROOT, out_dir

SECRETS = ROOT / ".secrets"
CLIENT_SECRET = SECRETS / "client_secret.json"
TOKEN = SECRETS / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CATEGORY_GAMING = "20"
TITLE_MAX = 100


def youtube_client():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not CLIENT_SECRET.exists():
            sys.exit(f"Belum ada {CLIENT_SECRET.relative_to(ROOT)}. Lihat README bagian Upload ke YouTube.")
        creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
        SECRETS.mkdir(exist_ok=True)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def clean_title(text: str) -> str:
    return re.sub(r"[<>]", "", text).strip()


def make_metadata(clip: dict, info: dict) -> dict:
    """Gaya clip channel teratas (data/trends): judul hook pendek tanpa nama channel, hashtag di
    deskripsi (#shorts, nama streamer, lalu hashtag yang sedang ramai), kredit ke video sumber."""
    from src.trends import top_hashtags

    channel = info.get("channel") or ""
    title = clean_title(clip.get("title") or info["title"])[:TITLE_MAX]
    tag = "#" + re.sub(r"[^a-z0-9]", "", channel.lower()) if channel else ""
    src_text = re.sub(r"[^a-z0-9]", "", f"{info['title']} {channel}".lower())
    relevant = [h for h in top_hashtags(30) if h[1:] in src_text]     # misal #ishowspeed untuk video Speed
    tags_line = list(dict.fromkeys(t for t in ["#shorts", tag, *relevant, "#twitch"] if t))[:5]
    desc = "\n".join([
        title,
        "",
        f"Full stream: {info['title']}" + (f" ({channel})" if channel else ""),
        clip["link"],
        "",
        " ".join(tags_line),
    ])
    tags = [t for t in [channel, "shorts", "streamer clips", "twitch", "funny moments"] if t]
    return {"title": title, "description": desc, "tags": tags, "categoryId": CATEGORY_GAMING}


QUOTA_REASONS = ("quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded")


class QuotaExceeded(RuntimeError):
    pass


def upload_one(yt, path, snippet: dict, privacy: str) -> tuple[str, str]:
    """Return (video id, status privasi yang benar-benar dipasang YouTube)."""
    from googleapiclient.errors import HttpError, ResumableUploadError
    from googleapiclient.http import MediaFileUpload

    body = {"snippet": snippet, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    try:
        while resp is None:
            _, resp = req.next_chunk()
    except (HttpError, ResumableUploadError) as e:
        if any(r in str(e) for r in QUOTA_REASONS):
            raise QuotaExceeded(str(e)[:200]) from None
        raise
    return resp["id"], resp.get("status", {}).get("privacyStatus", privacy)


def upload_clips(video_id: str, privacy: str = "private", only: list[int] | None = None,
                 dry_run: bool = False, log=print) -> list[dict]:
    summary = out_dir(video_id) / "clips.json"
    if not summary.exists():
        sys.exit(f"Belum ada {summary}. Jalankan pipeline dulu.")
    info = json.loads(summary.read_text(encoding="utf-8"))
    yt = None
    done = []
    for i, clip in enumerate(info["clips"], 1):
        if only and i not in only:
            continue
        if clip.get("youtube_id"):
            log(f"  clip {i} sudah di-upload: https://youtu.be/{clip['youtube_id']}")
            continue
        path = out_dir(video_id) / clip["file"]
        if not path.exists():
            log(f"  clip {i} dilewati, file {clip['file']} tidak ada")
            continue
        meta = make_metadata(clip, info)
        if dry_run:
            log(f"  [{i}] {meta['title']}\n{meta['description']}\n")
            continue
        yt = yt or youtube_client()
        log(f"  upload clip {i}: {meta['title']} ({privacy})")
        try:
            clip["youtube_id"], clip["youtube_privacy"] = upload_one(yt, path, meta, privacy)
        except QuotaExceeded as e:
            left = sum(1 for c in info["clips"] if not c.get("youtube_id"))
            log(f"  kuota YouTube habis, berhenti. Sisa {left} clip, jalankan perintah yang sama besok.\n  ({e})")
            break
        summary.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")   # simpan tiap clip
        note = "" if clip["youtube_privacy"] == privacy else f"  (YouTube memasang: {clip['youtube_privacy']})"
        log(f"    https://youtu.be/{clip['youtube_id']}{note}")
        done.append(clip)
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload clip ke YouTube")
    ap.add_argument("video_id")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    ap.add_argument("--only", help="nomor clip, misal 1,3")
    ap.add_argument("--dry-run", action="store_true", help="tampilkan judul dan deskripsi tanpa upload")
    args = ap.parse_args()
    only = [int(x) for x in args.only.split(",")] if args.only else None
    upload_clips(args.video_id, args.privacy, only, args.dry_run)


if __name__ == "__main__":
    main()
