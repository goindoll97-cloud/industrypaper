# -*- coding: utf-8 -*-
"""Build private 60-question provisional Gold from the reviewed 30-case XLSX.

Only Python standard library is required. Gold and local integrity metadata stay
under private/ and must never be committed to this public repository.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
GROUP = {'S': 'PARENT_AND_SALTS', 'C': 'COMPOUND_CLASS', 'M': 'MIXTURE'}
DIFFICULTY = {'쉬움': 'EASY', '어려움': 'HARD'}
RELATIONS = {'GROUP_INCLUDED', 'DIRECT_SPECIFIC', 'EXPLICIT_EXCEPTION'}
HEADERS = ['상황 ID', '유형', '난이도', '성분수', 'CAS 목록', '성분 영문명',
           '적용 근거 엑셀행', '근거 지정 문구', '물질별 Gold 관계',
           '전부 지정성분인가(혼합물)', 'Gold 상태', '독립검토 완료']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def read_review_xlsx(path):
    """Read just the fixed Gold worksheet (no Excel automation/extra packages)."""
    with ZipFile(path) as z:
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = wb.find('s:sheets', NS)
        selected = next((s for s in sheets if s.get('name') == 'Gold_검토_30'), None)
        require(selected is not None, 'Gold_검토_30 시트가 없습니다')
        rel_id = selected.get('{' + NS['r'] + '}id')
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rel = next((x for x in rels if x.get('Id') == rel_id), None)
        require(rel is not None, 'worksheet 관계 정보가 없습니다')
        target = rel.get('Target')
        sheet_path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            ss = ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared = [''.join(t.text or '' for t in si.findall('.//s:t', NS)) for si in ss.findall('s:si', NS)]
        sheet = ET.fromstring(z.read(sheet_path))
        rows = []
        for row in sheet.findall('.//s:sheetData/s:row', NS):
            cells = [''] * 14
            for cell in row.findall('s:c', NS):
                addr = cell.get('r', '')
                letters = re.match(r'[A-Z]+', addr)
                if not letters:
                    continue
                col = 0
                for letter in letters.group():
                    col = col * 26 + ord(letter) - ord('A') + 1
                if not 1 <= col <= len(cells):
                    continue
                typ = cell.get('t')
                if typ == 'inlineStr':
                    value = ''.join(x.text or '' for x in cell.findall('.//s:t', NS))
                else:
                    raw = cell.find('s:v', NS)
                    value = raw.text if raw is not None and raw.text is not None else ''
                    if typ == 's':
                        value = shared[int(value)]
                cells[col - 1] = str(value).strip()
            if any(cells):
                rows.append(cells)
    require(len(rows) == 31, f'기대 31행(헤더 + 30사례), 실제 {len(rows)}행')
    require(rows[0][:len(HEADERS)] == HEADERS, 'Gold 표의 컬럼명이 변경되었습니다')
    return rows[1:]


def build_gold(workbook, cases_path, annex_path):
    cases = read_jsonl(cases_path)
    require(len(cases) == 60, '실험 문항이 60개가 아닙니다')
    by_case = {}
    for case in cases:
        by_case.setdefault(case['case_id'], {})[case['condition']] = case
    require(len(by_case) == 30 and all(set(v) == {'A', 'B'} for v in by_case.values()), 'A/B 대응 30사례가 아닙니다')
    with annex_path.open(encoding='utf-8-sig', newline='') as f:
        annex = {int(row['excel_row']): row for row in csv.DictReader(f)}
    require(len(annex) == 1451, '공식 고시 1451행과 일치하지 않습니다')
    records = []
    seen = set()
    for row in read_review_xlsx(workbook):
        case_id, _, difficulty, count, cas_str, name_str, ref_str, _, rel_str, mix_str, status, expert = row[:12]
        require(case_id in by_case and case_id not in seen, f'사례 ID 누락/중복: {case_id}')
        seen.add(case_id)
        cas_list = [v.strip() for v in cas_str.split(';')]
        name_list = [v.strip() for v in name_str.split(';')]
        refs = [int(v.strip()) for v in ref_str.split(';')]
        relations = [v.strip() for v in rel_str.split(';')]
        require(len(cas_list) == len(name_list) == len(refs) == len(relations) == int(count), f'{case_id}: 성분 수 불일치')
        require(status == 'CURATED_PROVISIONAL' and expert == '아니오', f'{case_id}: Gold 검토 상태는 별도 프로토콜로 관리해야 합니다')
        require(difficulty in DIFFICULTY, f'{case_id}: 난이도 값 오류')
        inputs = by_case[case_id]
        require(inputs['A']['difficulty'] == DIFFICULTY[difficulty] and
                inputs['A']['group'] == GROUP[case_id[0]], f'{case_id}: 입력 문항 분류 불일치')
        components = []
        for i, (cas, name, ref, relation) in enumerate(zip(cas_list, name_list, refs, relations), start=1):
            require(ref in annex and relation in RELATIONS, f'{case_id}/C{i}: 근거 행/관계 오류')
            for condition in ('A', 'B'):
                c = inputs[condition]['components'][i - 1]
                require(c['component_id'] == f'C{i}' and c['cas'] == cas and c['name_en'] == name,
                        f'{case_id}-{condition}/C{i}: 엑셀과 시험 문항 CAS/명칭 불일치')
            a = annex[ref]
            direct = bool(re.search(r'(?<!\\d)' + re.escape(cas) + r'(?!\\d)', a['cas_field']))
            require(direct == (relation == 'DIRECT_SPECIFIC'), f'{case_id}/C{i}: 직접 CAS 지정과 관계 분류 불일치')
            components.append({'component_id': f'C{i}', 'cas': cas,
                'source_excel_row': ref, 'direct_cas_match': direct,
                'covered_by_clause': relation != 'EXPLICIT_EXCEPTION',
                'expected_relation': relation,
                'relevant_entry_id': a['parent_designation_id'],
                'relevant_sub_number': int(a['sub_number']) if a['sub_number'].isdigit() else None})
        is_mix = inputs['A']['group'] == 'MIXTURE'
        require(mix_str in (('예', '아니오') if is_mix else ('-',)), f'{case_id}: 혼합물 여부 값 오류')
        mixture = mix_str == '예' if is_mix else None
        require(not is_mix or mixture == all(c['covered_by_clause'] for c in components),
                f'{case_id}: 제3조 혼합물 값과 성분값이 불일치')
        for condition in ('A', 'B'):
            case = inputs[condition]
            records.append({'test_id': case['test_id'], 'case_id': case_id,
                'condition': condition, 'group': case['group'], 'difficulty': case['difficulty'],
                'component_gold': components, 'mixture_article3_all_listed': mixture,
                'review_status': status, 'independent_expert_review_completed': False})
    require(len(seen) == 30 and len(records) == 60, '30사례/60문항 생성 실패')
    return records


def main():
    p = argparse.ArgumentParser(description='엑셀 검토 정답지로 로컬 비공개 Gold 생성')
    p.add_argument('workbook', type=Path, help='수정한 Gold_검토_30 엑셀 파일')
    ns = p.parse_args()
    cases = ROOT / 'data' / 'cases_60.jsonl'
    annex = ROOT / 'data' / 'official_annex_2026_5_full.csv'
    manifest = json.loads((ROOT / 'data' / 'manifest.json').read_text(encoding='utf-8'))
    require(digest(cases) == manifest['cases_sha256'] and digest(annex) == manifest['annex_sha256'],
            '공개 시험 데이터의 SHA256이 manifest와 일치하지 않습니다')
    gold = build_gold(ns.workbook, cases, annex)
    blob = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\\n' for row in gold).encode('utf-8')
    sha = hashlib.sha256(blob).hexdigest()
    private = ROOT / 'private'
    private.mkdir(exist_ok=True)
    target = private / 'gold_60.jsonl'
    registry = private / 'gold_registry.json'
    if target.exists() and target.read_bytes() != blob:
        backup = private / ('gold_60.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
        shutil.copy2(target, backup)
        print('기존 Gold 백업:', backup)
    target.write_bytes(blob)
    metadata = {'gold_sha256': sha, 'source_workbook_sha256': digest(ns.workbook),
        'source_workbook_name': ns.workbook.name, 'review_status': 'CURATED_PROVISIONAL',
        'independent_expert_review_completed': False, 'cases_sha256': digest(cases),
        'annex_sha256': digest(annex)}
    registry.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
    print('PASS: Gold 30사례/60문항 재구축; 로컬 private/ 전용')
    print('Gold SHA256:', sha)
    print('정답지 내용은 GitHub에 업로드되지 않습니다')
    print('다음: python .\\\\preflight.py; python .\\\\score_results.py --results-dir results')


if __name__ == '__main__':
    main()
