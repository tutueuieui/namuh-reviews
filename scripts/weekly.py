"""주간 리뷰 요약 생성기.

매주 금요일 아침 수집이 끝난 뒤 실행되어, 지난 7일(금~목, 한국시간) 리뷰를
요약해 data/weekly.json 에 쌓는다. 카테고리 분류는 index.html 과 같은 규칙
(categories.json 키워드 매칭)을 쓴다.

    python scripts/weekly.py          # 금요일(KST)일 때만 생성
    python scripts/weekly.py --force  # 요일과 상관없이 지금 기준으로 생성
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "data" / "reviews.json"
WEEKLY = ROOT / "data" / "weekly.json"
CATS = json.loads((ROOT / "categories.json").read_text(encoding="utf-8"))
STORES = {"android": "Android", "ios": "iOS"}


def classify(r):
    t = (r.get("title", "") + " " + r.get("content", "")).lower()
    hit = [
        c["name"]
        for c in CATS
        if r["rating"] >= c.get("minRating", 1)
        and any(k.lower() in t for k in c["keywords"])
    ]
    return hit or ["기타"]


def avg(rs):
    return round(sum(r["rating"] for r in rs) / len(rs), 2) if rs else None


def pick_quotes(rs, n, low=True):
    pool = [r for r in rs if (r["rating"] <= 2 if low else r["rating"] >= 4)]
    pool = [r for r in pool if len(r["content"]) >= 15]
    pool.sort(key=lambda r: (r.get("likes", 0), len(r["content"])), reverse=True)
    return [
        {
            "rating": r["rating"],
            "content": r["content"][:200],
            "date": r["date"],
            "likes": r.get("likes", 0),
            "cats": r["cats"],
        }
        for r in pool[:n]
    ]


def summarize_store(cur, prev, stats_now, stats_prev):
    cc, pc = Counter(), Counter()
    for r in cur:
        cc.update(r["cats"])
    for r in prev:
        pc.update(r["cats"])
    cats = [
        {"name": k, "count": v, "prev": pc.get(k, 0), "avg": avg([r for r in cur if k in r["cats"]])}
        for k, v in cc.most_common()
        if k not in ("칭찬",)
    ]
    rising = sorted(
        [c for c in cats if c["name"] != "기타" and c["count"] - c["prev"] >= 2],
        key=lambda c: c["count"] - c["prev"],
        reverse=True,
    )
    return {
        "count": len(cur),
        "prev_count": len(prev),
        "avg": avg(cur),
        "prev_avg": avg(prev),
        "neg_ratio": round(sum(r["rating"] <= 2 for r in cur) / len(cur) * 100) if cur else None,
        "store_score": (stats_now or {}).get("score"),
        "prev_store_score": (stats_prev or {}).get("score"),
        "version": (stats_now or {}).get("version"),
        "top_categories": cats[:5],
        "rising": [c["name"] for c in rising[:3]],
        "praise": cc.get("칭찬", 0),
        "complaints": pick_quotes(cur, 3, low=True),
        "compliments": pick_quotes(cur, 1, low=False),
    }


def headline(s):
    lines = []
    for k, name in STORES.items():
        x = s["stores"].get(k)
        if not x or not x["count"]:
            continue
        diff = x["count"] - x["prev_count"]
        part = f"{name} 리뷰 {x['count']}건(전주 대비 {'+' if diff >= 0 else ''}{diff}), 평균 ★{x['avg']:.1f}"
        if x["prev_avg"]:
            part += f"(전주 ★{x['prev_avg']:.1f})"
        top = [c for c in x["top_categories"] if c["name"] != "기타"]
        if top:
            part += f". 가장 많이 언급된 주제는 '{top[0]['name']}' {top[0]['count']}건"
        if x["rising"]:
            part += f", 전주보다 늘어난 주제는 " + ", ".join(f"'{n}'" for n in x["rising"])
        lines.append(part + ".")
    return lines or ["이번 주에 수집된 리뷰가 없어요."]


def main(force=False):
    now = datetime.now(KST)
    if not force and now.weekday() != 4:  # 4 = 금요일
        print("금요일이 아니라서 주간 요약을 건너뜀")
        return
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start, prev_start = end - timedelta(days=7), end - timedelta(days=14)

    data = json.loads(REVIEWS.read_text(encoding="utf-8"))
    reviews = []
    for r in data["reviews"]:
        r = dict(r)
        r["dt"] = datetime.fromisoformat(r["date"]).astimezone(KST)
        r["cats"] = classify(r)
        reviews.append(r)

    hist = json.loads(WEEKLY.read_text(encoding="utf-8")) if WEEKLY.exists() else []
    key = start.strftime("%Y-%m-%d")
    # 3시간마다 수집하므로 금요일엔 여러 번 불림 → 이번 주 요약이 이미 있으면 건너뜀
    if not force and any(h["week_start"] == key for h in hist):
        print("이번 주 요약이 이미 있어서 건너뜀")
        return
    # 같은 주이거나 기간이 겹치는 이전 요약(수동 실행분 등)은 교체
    hist = [
        h for h in hist
        if abs((datetime.fromisoformat(h["week_start"]) - datetime.fromisoformat(key)).days) >= 7
    ]
    prev_entry = next((h for h in hist if h["week_start"] < key), None)
    stats_now = data["meta"].get("store_stats", {})

    stores = {}
    for k in STORES:
        cur = [r for r in reviews if r["store"] == k and start <= r["dt"] < end]
        prev = [r for r in reviews if r["store"] == k and prev_start <= r["dt"] < start]
        prev_stats = (prev_entry or {}).get("store_stats", {}).get(k)
        stores[k] = summarize_store(cur, prev, stats_now.get(k), prev_stats)

    summary = {
        "week_start": key,
        "week_end": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "generated": now.isoformat(),
        "store_stats": stats_now,
        "stores": stores,
    }
    summary["headline"] = headline(summary)
    hist.insert(0, summary)
    hist.sort(key=lambda h: h["week_start"], reverse=True)
    WEEKLY.write_text(json.dumps(hist[:52], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"주간 요약 생성: {summary['week_start']} ~ {summary['week_end']}")
    for line in summary["headline"]:
        print(" -", line)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
