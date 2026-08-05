"""払戻金ベースの戦略バックテスト（一次実験）。

オッズは非勝利馬の分が payouts に存在しないため、EV は「人気別の市場的中率」を
暗黙確率の代理としてモデル確率との比で近似する。
実オッズを使った厳密な EV 評価は banei.backtest.ev を参照。
"""

import pandas as pd

from banei.config import RACES_DB
from banei.features.dataset import FEATURES, build_dataset
from banei.models.train import TEST_START, VALID_START, add_preds, train


def roi(part: pd.DataFrame, mask: pd.Series, pay_col: str, hit_col: str):
    """(件数, 的中率%, 回収率%) を返す。"""
    b = part[mask]
    n = len(b)
    if n == 0:
        return n, 0.0, 0.0
    hits = b[hit_col].sum()
    ret = b.loc[b[hit_col] == 1, pay_col].fillna(0).sum()
    return n, 100 * hits / n, 100 * ret / (n * 100)


def report(part: pd.DataFrame, label: str, implied: pd.Series) -> None:
    print(f'--- {label} ---')
    part = part.copy()
    part['implied'] = part['popularity'].map(implied)
    part['ev_ratio'] = part['p_win_n'] / part['implied']
    model_top_not_fav = (part['model_rank'] == 1) & (part['popularity'] > 1)
    strategies = [
        ('市場1番人気を単勝', part['popularity'] == 1, 'win_pay', 'win'),
        ('モデル1位を単勝', part['model_rank'] == 1, 'win_pay', 'win'),
        ('モデル1位≠市場1位を単勝', model_top_not_fav, 'win_pay', 'win'),
        ('モデル1位≠市場1位を複勝', model_top_not_fav, 'place_pay', 'p3'),
        ('EV比>=1.3を単勝', part['ev_ratio'] >= 1.3, 'win_pay', 'win'),
        ('EV比>=1.5を単勝', part['ev_ratio'] >= 1.5, 'win_pay', 'win'),
        ('EV比>=1.3を複勝', part['ev_ratio'] >= 1.3, 'place_pay', 'p3'),
    ]
    print(f'{"戦略":<24}{"n":>7}{"的中率":>8}{"回収率":>8}')
    for name, mask, pay, hit in strategies:
        n, hr, r = roi(part, mask, pay, hit)
        print(f'{name:<24}{n:>7}{hr:>8.1f}{r:>8.1f}')


def run(db_path=RACES_DB) -> None:
    print('データセット構築中...')
    df = build_dataset(db_path)
    print(f'総行数 {len(df)}（出走ベース・取消除外を除く）')
    print('学習中...')
    mw = train(df, 'win')
    mp = train(df, 'p3')
    df = add_preds(df, mw, mp)

    # 人気別の市場的中率（暗黙確率の代理）は学習期間のみから推定
    tr = df[df['date'] < VALID_START]
    implied = tr.groupby('popularity')['win'].mean()

    report(df[(df['date'] >= VALID_START) & (df['date'] < TEST_START)], '検証 2025年', implied)
    report(df[df['date'] >= TEST_START], 'テスト 2026年', implied)

    print('--- 特徴量重要度 (gain) 上位12 ---')
    imp = pd.Series(mw.feature_importance('gain'), index=FEATURES).sort_values(ascending=False)
    for k, v in imp.head(12).items():
        print(f'  {k:<18}{v:>12.0f}')
