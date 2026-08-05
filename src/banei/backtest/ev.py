"""実オッズ（odds.db）を使った EV バックテスト。

- モデルは banei.models.train と同一（オッズは特徴量に入れない）
- EV = モデル勝率（レース内正規化）× 単勝確定オッズ
- 閾値は 2025年（検証）で選び、2026年（テスト）で凍結評価する

注意: 確定オッズで購入できたという仮定に基づく（スリッページ未考慮）。
実際には締切前オッズで買うため、この結果はやや楽観的になる。
"""

import sqlite3
from pathlib import Path

import pandas as pd
from sklearn.metrics import log_loss

from banei.config import ODDS_DB, RACES_DB
from banei.features.dataset import build_dataset
from banei.models.train import TEST_START, VALID_START, add_preds, train


def load_odds(db_path: Path | str = ODDS_DB) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    o = pd.read_sql(
        "SELECT race_date, race_no, horse_no, win_odds, place_min FROM odds", con)
    con.close()
    return o


def implied_probs(df: pd.DataFrame) -> pd.Series:
    """オッズ由来の市場確率。控除率は正規化で除去する。"""
    inv = 1.0 / df['win_odds']
    s = inv.groupby([df['race_date'], df['race_no']]).transform('sum')
    return inv / s


def bet_report(df: pd.DataFrame, mask: pd.Series, kind: str) -> str:
    b = df[mask]
    n = len(b)
    if n == 0:
        return f'n={n:>6}'
    if kind == 'win':
        ret = (b['win'] * b['win_odds'] * 100).sum()
        hits = b['win'].mean()
    else:
        ret = (b['p3'] * b['place_min'] * 100).sum()  # 複勝はレンジ下限（保守的）
        hits = b['p3'].mean()
    return f'n={n:>6}  的中率={100 * hits:5.1f}%  回収率={100 * ret / (n * 100):6.1f}%'


def run(races_db_path=RACES_DB, odds_db_path=ODDS_DB) -> None:
    print('データセット構築・学習中...')
    df = build_dataset(races_db_path)
    mw = train(df, 'win')
    mp = train(df, 'p3')
    df = add_preds(df, mw, mp)
    df = df.merge(load_odds(odds_db_path), on=['race_date', 'race_no', 'horse_no'], how='left')
    df = df[df['win_odds'].notna() & (df['win_odds'] > 0)].copy()
    df['p_market'] = implied_probs(df)
    df['ev_win'] = df['p_win_n'] * df['win_odds']
    df['edge'] = df['p_win_n'] - df['p_market']

    periods = (
        ('検証 2025年', df[(df['date'] >= VALID_START) & (df['date'] < TEST_START)]),
        ('テスト 2026年', df[df['date'] >= TEST_START]),
    )
    for label, part in periods:
        print(f'--- {label}  (オッズ結合率 {100 * part["win_odds"].notna().mean():.1f}%)')
        print('  [基準] 全馬ベタ買い単勝      ', bet_report(part, part['win_odds'] > 0, 'win'))
        for th in (1.0, 1.1, 1.2, 1.4, 1.6):
            print(f'  EV>={th:.1f} 単勝            ', bet_report(part, part['ev_win'] >= th, 'win'))
        for th in (1.0, 1.2):
            m = (part['ev_win'] >= th) & (part['win_odds'] <= 20)
            print(f'  EV>={th:.1f} かつ20倍以下 単勝 ', bet_report(part, m, 'win'))
        top = part['model_rank'] == 1
        top_ev = top & (part['ev_win'] >= 1.2)
        print('  モデル1位 単勝            ', bet_report(part, top, 'win'))
        print('  モデル1位かつEV>=1.2 単勝  ', bet_report(part, top_ev, 'win'))
        print('  モデル1位かつEV>=1.2 複勝  ', bet_report(part, top_ev, 'place'))

    # モデルと市場の確率のズレの大きさ（キャリブレーション比較）
    te = df[df['date'] >= TEST_START]
    market_ll = log_loss(te['win'], te['p_market'].clip(1e-6, 1 - 1e-6))
    model_ll = log_loss(te['win'], te['p_win_n'].clip(1e-6, 1 - 1e-6))
    print('--- 確率の質（2026年・logloss 低いほど良い）')
    print(f'  市場（オッズ由来確率）: {market_ll:.4f}')
    print(f'  モデル（正規化勝率）  : {model_ll:.4f}')
