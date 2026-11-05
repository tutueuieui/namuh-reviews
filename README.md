# 나무증권 앱 리뷰 보드

Google Play·App Store 공개 리뷰를 1시간마다 자동 수집해서 보여주는 개인용 대시보드.

- `scripts/collect.py` — 리뷰 수집 → `data/reviews.json`
- `.github/workflows/collect.yml` — GitHub Actions로 주기 실행 후 자동 커밋
- `index.html` — GitHub Pages로 띄우는 대시보드

## 카테고리 수정하기
`categories.json` 에서 카테고리 이름·색·키워드를 고치면 바로 반영돼 (재수집 불필요).
- 리뷰 제목+본문에 키워드가 하나라도 들어 있으면 그 카테고리로 분류 (여러 개 동시 가능, 대소문자 무시)
- 아무 데도 안 걸리면 "기타"
- `minRating` 을 넣으면 그 별점 이상인 리뷰만 해당 (예: 칭찬은 4점 이상)
