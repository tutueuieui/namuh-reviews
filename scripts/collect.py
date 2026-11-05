"""나무증권 앱 리뷰 수집기.

- Android: google-play-scraper (공개 데이터, API 키 불필요)
- iOS: 애플 공개 RSS 피드 (응답이 비어 있으면 건너뜀)

결과는 data/reviews.json 에 누적 저장한다 (id 기준 중복 제거).
작성자 이름은 공개 사이트에 노출되지 않도록 저장하지 않는다.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from google_play_scraper import Sort, reviews

ANDROID_ID = "com.wooriwm.txsmart"
IOS_ID = "486312400"
ANDROID_BATCH = 500

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "reviews.json"


def fetch_android():
    items, _ = reviews(
        ANDROID_ID, lang="ko", country="kr", sort=Sort.NEWEST, count=ANDROID_BATCH
    )
    out = []
    for r in items:
        out.append(
            {
                "id": "a_" + r["reviewId"],
                "store": "android",
                "rating": r["score"],
                "title": "",
                "content": (r.get("content") or "").strip(),
                "version": r.get("reviewCreatedVersion") or r.get("appVersion") or "",
                "date": r["at"].replace(tzinfo=timezone.utc).isoformat(),
                "likes": r.get("thumbsUpCount") or 0,
                "replied": bool(r.get("replyContent")),
            }
        )
    return out


def fetch_ios():
    out = []
    for page in range(1, 11):
        url = (
            f"https://itunes.apple.com/kr/rss/customerreviews/page={page}"
            f"/id={IOS_ID}/sortBy=mostRecent/json"
        )
        try:
            with urllib.request.urlopen(url, timeout=20) as res:
                feed = json.load(res).get("feed", {})
        except Exception as e:  # noqa: BLE001
            print(f"[ios] page {page} 실패: {e}", file=sys.stderr)
            break
        entries = feed.get("entry") or []
        if isinstance(entries, dict):
            entries = [entries]
        entries = [e for e in entries if "im:rating" in e]
        if not entries:
            break
        for e in entries:
            out.append(
                {
                    "id": "i_" + e["id"]["label"],
                    "store": "ios",
                    "rating": int(e["im:rating"]["label"]),
                    "title": e.get("title", {}).get("label", ""),
                    "content": e.get("content", {}).get("label", "").strip(),
                    "version": e.get("im:version", {}).get("label", ""),
                    "date": e.get("updated", {}).get("label", ""),
                    "likes": 0,
                    "replied": False,
                }
            )
    return out


def main():
    existing = {}
    meta = {}
    if DATA.exists():
        saved = json.loads(DATA.read_text(encoding="utf-8"))
        existing = {r["id"]: r for r in saved.get("reviews", [])}
        meta = saved.get("meta", {})

    counts = {}
    for name, fn in (("android", fetch_android), ("ios", fetch_ios)):
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] 수집 실패: {e}", file=sys.stderr)
            got = []
        new = sum(1 for r in got if r["id"] not in existing)
        for r in got:
            existing[r["id"]] = r
        counts[name] = {"fetched": len(got), "new": new}
        print(f"[{name}] 가져옴 {len(got)}건, 신규 {new}건")

    all_reviews = sorted(existing.values(), key=lambda r: r["date"], reverse=True)
    meta.update(
        {
            "updated": datetime.now(timezone.utc).isoformat(),
            "last_run": counts,
            "android_id": ANDROID_ID,
            "ios_id": IOS_ID,
        }
    )
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(
        json.dumps({"meta": meta, "reviews": all_reviews}, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )
    print(f"총 {len(all_reviews)}건 저장 → {DATA}")


if __name__ == "__main__":
    main()
