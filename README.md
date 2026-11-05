# 나무증권 앱 리뷰 보드

Google Play·App Store 공개 리뷰를 1시간마다 자동 수집해서 보여주는 개인용 대시보드.

- `scripts/collect.py` — 리뷰 수집 → `data/reviews.json`
- `.github/workflows/collect.yml` — GitHub Actions로 주기 실행 후 자동 커밋
- `index.html` — GitHub Pages로 띄우는 대시보드
