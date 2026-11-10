"""나무증권 앱 리뷰 수집기.

- Android: google-play-scraper (공개 데이터, API 키 불필요)
- iOS: 애플 공개 RSS 피드 (응답이 비어 있으면 건너뜀)

결과는 data/reviews.json 에 누적 저장한다 (id 기준 중복 제거).
작성자 이름은 공개 사이트에 노출되지 않도록 저장하지 않는다.
"""
import json
import sys
import time
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


def _ios_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as res:
        feed = json.load(res).get("feed", {})
    entries = feed.get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    return [e for e in entries if "im:rating" in e]


def fetch_ios():
    """애플 RSS는 CDN(Akamai) 캐시 때문에 서버 위치에 따라 며칠 전 내용이 올 수 있다.
    같은 페이지를 주소를 조금씩 바꿔(캐시 우회) 여러 번 받아 합친다."""
    stamp = int(time.time())
    base = f"https://itunes.apple.com/kr/rss/customerreviews"
    variants = [
        "{b}/page={p}/id={i}/sortBy=mostRecent/json?cb={t}",
        "{b}/id={i}/sortBy=mostRecent/page={p}/json?cb={t}",
        "{b}/page={p}/id={i}/sortby=mostrecent/json?cb={t}",
        "{b}/page={p}/id={i}/sortBy=mostRecent/json",
    ]
    seen = {}
    for page in range(1, 11):
        got_any = False
        for v in variants:
            url = v.format(b=base, p=page, i=IOS_ID, t=stamp)
            try:
                entries = _ios_page(url)
            except Exception as e:  # noqa: BLE001
                print(f"[ios] page {page} 실패: {e}", file=sys.stderr)
                continue
            got_any = got_any or bool(entries)
            for e in entries:
                rid = "i_" + e["id"]["label"]
                seen.setdefault(rid, {
                    "id": rid,
                    "store": "ios",
                    "rating": int(e["im:rating"]["label"]),
                    "title": e.get("title", {}).get("label", ""),
                    "content": e.get("content", {}).get("label", "").strip(),
                    "version": e.get("im:version", {}).get("label", ""),
                    "date": e.get("updated", {}).get("label", ""),
                    "likes": 0,
                    "replied": False,
                })
        if not got_any:
            break
    out = list(seen.values())
    if out:
        print(f"[ios] 가장 최근 리뷰 {max(r['date'] for r in out)}")
    return out


def fetch_store_stats():
    """스토어에 표시되는 전체 평점(리뷰 본문 없이 별점만 남긴 것 포함)."""
    stats = {}
    try:
        from google_play_scraper import app

        a = app(ANDROID_ID, lang="ko", country="kr")
        stats["android"] = {
            "score": a.get("score"),
            "ratings": a.get("ratings"),
            "version": a.get("version"),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[android] 평점 조회 실패: {e}", file=sys.stderr)
    try:
        url = f"https://itunes.apple.com/lookup?id={IOS_ID}&country=kr"
        with urllib.request.urlopen(url, timeout=20) as res:
            r = json.load(res)["results"][0]
        stats["ios"] = {
            "score": r.get("averageUserRating"),
            "ratings": r.get("userRatingCount"),
            "version": r.get("version"),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[ios] 평점 조회 실패: {e}", file=sys.stderr)
    return stats


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
            "store_stats": fetch_store_stats() or meta.get("store_stats", {}),
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
