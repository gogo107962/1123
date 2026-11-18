"""Explicit, bounded collection; never runs during app startup."""
import argparse
import json
from db import init_db
from ontong import sync, OntongError

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='온통청년 정책을 검수 대기 DB로 수집합니다.')
    parser.add_argument('--keyword', default='월세')
    parser.add_argument('--page-size', type=int, default=10, choices=range(1, 11))
    parser.add_argument('--max-pages', type=int, default=1, choices=range(1, 4))
    args = parser.parse_args()
    init_db()
    try:
        print(json.dumps(sync(args.keyword, args.page_size, args.max_pages), ensure_ascii=False, indent=2))
    except OntongError as exc:
        print(str(exc))
        raise SystemExit(1) from None
