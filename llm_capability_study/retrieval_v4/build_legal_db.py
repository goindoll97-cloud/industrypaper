"""Build an auditable full-annex SQLite index from the official 1451-row CSV.
CSV comes directly from the previously uploaded 2026-5 official workbook. No Gold used.
"""
from __future__ import annotations
import csv,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'data/official_annex_2026_5_full.csv'
DB=ROOT/'data/official_annex_2026_5.sqlite'
MANIFEST=ROOT/'data/manifest.json'
COLS=['excel_row','designation_id','sub_number','name_ko','name_en','cas_field','acute_percent',
      'chronic_percent','ecological_percent','hazard_type','previous_percent','parent_designation_id']

def build():
    m=json.loads(MANIFEST.read_text(encoding='utf-8'))
    if hashlib.sha256(SRC.read_bytes()).hexdigest()!=m['annex_sha256']:raise ValueError('원본 전체 고시 인덱스 SHA 불일치')
    with SRC.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);assert reader.fieldnames==COLS
        rows=list(reader)
    if len(rows)!=m['total_annex_rows']:raise ValueError(f'인덱스 행 수 오류 {len(rows)}')
    if any(not (r['name_ko'] or r['name_en']) or not r['excel_row'] or not r['parent_designation_id'] for r in rows):
        raise ValueError('공식 지정 항목 누락')
    DB.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.execute('DROP TABLE IF EXISTS annex')
        con.execute('CREATE TABLE annex (excel_row INTEGER PRIMARY KEY,'+','.join(c+' TEXT' for c in COLS[1:])+')')
        con.executemany('INSERT INTO annex VALUES ('+','.join('?' for _ in COLS)+')',
                        [tuple([int(r['excel_row'])]+[r[c] for c in COLS[1:]]) for r in rows])
        con.execute('CREATE INDEX IF NOT EXISTS idx_parent ON annex(parent_designation_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_name_en ON annex(name_en)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_name_ko ON annex(name_ko)')
        count=con.execute('SELECT count(*) FROM annex').fetchone()[0]
    if count!=1451:raise ValueError('SQLite 데이터 행 오류')
    print(f'PASS: 공식 고시 전체 {count}행 DB 구축: {DB}')

if __name__=='__main__':build()
