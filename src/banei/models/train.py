"""LightGBM 勝率モデルの学習。

期間の分け方は固定する:
  学習 〜2024年 / 検証 2025年（早期停止・閾値調整）/ テスト 2026年（最終評価）
検証期間で決めた閾値をテスト期間で凍結評価することで、閾値の過学習を避ける。
"""

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from banei.features.dataset import FEATURES

VALID_START = '2025-01-01'
TEST_START = '2026-01-01'

PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=63,
              min_data_in_leaf=100, feature_fraction=0.8, bagging_fraction=0.8,
              bagging_freq=1, verbosity=-1, seed=7)


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(学習, 検証, テスト) に分ける。"""
    return (df[df['date'] < VALID_START],
            df[(df['date'] >= VALID_START) & (df['date'] < TEST_START)],
            df[df['date'] >= TEST_START])


def train(df: pd.DataFrame, target: str) -> lgb.Booster:
    """target ('win' または 'p3') の二値分類モデルを学習する。"""
    tr, va, te = split(df)
    m = lgb.train(PARAMS,
                  lgb.Dataset(tr[FEATURES], tr[target]),
                  num_boost_round=2000,
                  valid_sets=[lgb.Dataset(va[FEATURES], va[target])],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    for name, part in (('valid(2025)', va), ('test(2026)', te)):
        p = m.predict(part[FEATURES])
        print(f'  {target} {name}: AUC={roc_auc_score(part[target], p):.4f} '
              f'logloss={log_loss(part[target], p):.4f} n={len(part)}')
    return m


def add_preds(df: pd.DataFrame, mw: lgb.Booster, mp: lgb.Booster) -> pd.DataFrame:
    """勝率・複勝率の予測列を付与する。p_win_n はレース内で正規化した勝率。"""
    df = df.copy()
    df['p_win'] = mw.predict(df[FEATURES])
    df['p_p3'] = mp.predict(df[FEATURES])
    s = df.groupby(['race_date', 'race_no'])['p_win'].transform('sum')
    df['p_win_n'] = df['p_win'] / s
    df['model_rank'] = df.groupby(['race_date', 'race_no'])['p_win'].rank(
        ascending=False, method='first')
    return df
