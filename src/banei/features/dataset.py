"""学習用データセットの構築。

特徴量はすべてレース発走前に既知の情報のみ。過去成績は shift で厳密に因果化しており、
当該レースの結果が特徴量に混入しないようにしている（リーク防止）。
"""

import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from banei.config import RACES_DB

LADDER = {'Ｃ２': 0, 'Ｃ１': 1, 'Ｂ４': 2, 'Ｂ３': 3, 'Ｂ２': 4,
          'Ｂ１': 5, 'Ａ２': 6, 'Ａ１': 7, 'オープン': 8}
CLS_PAT = re.compile(r'(Ａ[１２]|Ｂ[１-４]|Ｃ[１２])(?:－\d+(?:・\d+決勝)?)?$')

FEATURES = ['age', 'weight_carried', 'wc_diff', 'horse_weight', 'horse_weight_diff',
            'moisture', 'month', 'race_no', 'field_size', 'cls_rank', 'cls_move',
            'career_starts', 'career_wr', 'career_p3r',
            'fin_1', 'fin_2', 'fin_3', 'prev_time_z', 'prev_pop', 'days_since',
            'jockey_wr', 'jockey_starts', 'trainer_wr', 'trainer_starts', 'sex_c']

QUERY = """
    SELECT r.race_date, r.race_no, r.horse_no, r.horse_name, r.finish, r.status,
           r.sex, r.age, r.weight_carried, r.jockey, r.trainer,
           r.horse_weight, r.horse_weight_diff, r.time_sec, r.popularity,
           ra.name AS race_name, ra.moisture,
           t.amount AS win_pay, f.amount AS place_pay
    FROM results r
    JOIN races ra USING (race_date, race_no)
    LEFT JOIN payouts t ON t.race_date=r.race_date AND t.race_no=r.race_no
         AND t.bet_type='単勝' AND CAST(t.combination AS INTEGER)=r.horse_no
    LEFT JOIN payouts f ON f.race_date=r.race_date AND f.race_no=r.race_no
         AND f.bet_type='複勝' AND CAST(f.combination AS INTEGER)=r.horse_no
"""


def race_class(name: str | None) -> float:
    """レース名からクラスの序列を返す。判定できなければ NaN。"""
    m = CLS_PAT.search(name or '')
    if m:
        return LADDER[m.group(1)]
    if 'オープン' in (name or '') or '選抜' in (name or ''):
        return LADDER['オープン']
    return np.nan


def build_dataset(db_path: Path | str = RACES_DB) -> pd.DataFrame:
    """出走ベースのデータセットを返す（取消・除外は除く）。"""
    con = sqlite3.connect(db_path)
    df = pd.read_sql(QUERY, con)
    con.close()
    df['date'] = pd.to_datetime(df['race_date'])
    df = df.sort_values(['date', 'race_no', 'horse_no']).reset_index(drop=True)
    df['win'] = (df['finish'] == 1).astype(int)
    df['p3'] = (df['finish'] <= 3).fillna(False).astype(int)
    df['ran'] = ~df['status'].isin(['取消', '除外'])
    df['cls_rank'] = df['race_name'].map(race_class)

    rk = df.groupby(['race_date', 'race_no'])
    df['field_size'] = rk['ran'].transform('sum')
    df['wc_diff'] = df['weight_carried'] - rk['weight_carried'].transform('min')
    # レース内タイム z 値（能力代理; そのレースの完走馬内で標準化）
    tmean = rk['time_sec'].transform('mean')
    tstd = rk['time_sec'].transform('std')
    df['time_z'] = (df['time_sec'] - tmean) / tstd

    # --- 馬の履歴（すべて shift 済み = 当該レースの結果を含まない） ---
    g = df.groupby('horse_name', sort=False)
    df['career_starts'] = g.cumcount()
    df['career_wr'] = (g['win'].cumsum() - df['win']) / df['career_starts'].replace(0, np.nan)
    df['career_p3r'] = (g['p3'].cumsum() - df['p3']) / df['career_starts'].replace(0, np.nan)
    for k in (1, 2, 3):
        df[f'fin_{k}'] = g['finish'].shift(k)
    df['prev_time_z'] = g['time_z'].shift(1)
    df['prev_pop'] = g['popularity'].shift(1)
    df['days_since'] = (df['date'] - g['date'].shift(1)).dt.days
    prev_cls = g['cls_rank'].apply(lambda s: s.shift(1).ffill())
    df['prev_cls'] = prev_cls.reset_index(level=0, drop=True)
    df['cls_move'] = df['cls_rank'] - df['prev_cls']

    # --- 騎手・調教師の通算成績（shift 済み） ---
    for col in ('jockey', 'trainer'):
        gg = df.groupby(col, sort=False)
        starts = gg.cumcount()
        df[f'{col}_wr'] = (gg['win'].cumsum() - df['win']) / starts.replace(0, np.nan)
        df[f'{col}_starts'] = starts

    df['month'] = df['date'].dt.month
    df['sex_c'] = df['sex'].astype('category')
    return df[df['ran']].copy()
