"""Read the supplied XLSX without modifying it. Run with bundled Python/openpyxl."""
import argparse
import hashlib
import json
from pathlib import Path
import openpyxl


def extract(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    groups = {}
    current = None
    for number, row in enumerate(workbook['코드정보'].iter_rows(values_only=True), 1):
        if number == 1:
            continue
        field, title, prefix, code, label = row
        if field:
            current = str(field)
            groups[current] = {'title': title.replace('\n', ''), 'codes': {}}
        if not current or not isinstance(code, str) or not code.isdigit() or not label:
            raise ValueError(f'Invalid code row {number}; preserve codes as text')
        if code in groups[current]['codes']:
            raise ValueError(f'Duplicate code at row {number}')
        groups[current]['codes'][code] = {'label': label, 'cell': f'코드정보!D{number}:E{number}'}
    names = {}
    for sheet, field in [('정책대분류', 'lclsfNm'), ('정책중분류', 'mclsfNm'), ('정책키워드', 'plcyKywdNm')]:
        names[field] = [row[1] for row in workbook[sheet].iter_rows(min_row=2, values_only=True) if row[1]]
    workbook.close()
    return {'source': {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'read_on': '2026-11-17', 'provided_by': 'user',
                       'limitations': ['지역 zipCd 매핑 없음', '소득 금액 단위 없음', '연령 제한 Y/N 정의 없음']},
            'groups': groups, 'names': names}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'groups': len(result['groups']), 'codes': sum(len(g['codes']) for g in result['groups'].values()), 'sha256': result['source']['sha256']}))
