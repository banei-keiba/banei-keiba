# CLAUDE.md

ばんえい競馬（帯広）のデータ収集・分析プロジェクト。将来的に集計・分析結果を
公開サイトとして出す。技術方針とロードマップの詳細は
[docs/architecture.md](docs/architecture.md)（このファイルは要点と落とし穴のみ）。

## 最重要: データ公開方針

**スクレイピングした生データをそのまま表示・配布しない。** 公開してよいのは集計値・
派生指標・分析結果だけ。判断基準は「そのページを全部集めれば元の DB が復元できるか」。

この方針は飾りではなく構成を決めている。これがあるので個別レースの着順表ページを作らず、
ページ数が 42,000 → 約 6,000 に収まり、SSR もデータベースも不要になっている。緩めると
Cloudflare Pages の上限（ファイル数 20,000）に当たって設計が崩れる。

具体的に守ること:

- `data/` は .gitignore 済み。`.db` を絶対にコミットしない
- テストフィクスチャに実ページの HTML を置かない（`tests/fixtures/` は合成 HTML）
- 公開物は `src/banei/export/`（Phase 2 で作る）を唯一の出口にする

## 構成

```
src/banei/
  ingest/     results.py（keiba.go.jp）/ odds.py・combo_odds.py（オッズパーク）
  db/         schema.py — スキーマと接続ヘルパー
  features/   dataset.py — build_dataset（過去成績は shift で厳密に因果化）
  models/     train.py — LightGBM
  backtest/   strategies.py（払戻ベース）/ ev.py（実オッズベース）
  validate.py データ検証
  net.py      レート制限付き HTTP クライアント（3スクレイパー共通）
```

ML 依存は `ml` エクストラに分離してある。収集・検証だけなら `uv sync` で足り、
日次ワークフローもそれで回している。**分析系の import は CLI のハンドラ内で行うこと**
（トップレベルに置くと ml なし環境で `banei scrape` が壊れる）。

```bash
uv sync --all-extras          # 開発用
uv run banei --help           # scrape / odds / combo-odds / validate / backtest / backtest-ev
uv run ruff check . && uv run pytest
```

## データの正はバックアップ側にある

日次ワークフローが毎晩 DB を更新するため、**ローカルの `data/` は放っておくと古くなる**。
作業前に復元すること。

```bash
gh release download latest --repo banei-keiba/banei-db-backup --dir data --clobber
gunzip -f data/banei.db.gz data/odds.db.gz
```

逆に**ローカルで収集しても次の日次実行で上書きされて失われる**。過去分のバックフィルは
`gh workflow run backfill-odds.yml -f limit=3000` で回すこと。

バックアップ先 [banei-keiba/banei-db-backup](https://github.com/banei-keiba/banei-db-backup)
は **private のまま**にする（生データを含む）。`scripts/backup-db.sh` は実行前に
`isPrivate` を確認して、private でなければ中断する。

## 認証情報の期限

| 項目 | 値 |
|---|---|
| シークレット名 | `BACKUP_TOKEN`（banei-keiba/banei-keiba の Actions secret） |
| 種類 | fine-grained PAT。対象 `banei-keiba/banei-db-backup`、Contents: Read and write |
| **有効期限** | **2027-08-07（Sat, Aug 7 2027）** |

**期限が切れると日次ワークフローが「バックアップから DB を復元」で失敗する。**
そのときは PAT を作り直して `BACKUP_TOKEN` を更新する。データ自体はバックアップ
リポジトリに残っているので失われない。

## 実データから分かっている落とし穴

検証の閾値やロジックを足すときは、**推測せず実データを集計して決める**こと。
以下は推測していたら誤検知していたもの（19年分・33,493レースから確認済み）。

| 事実 | 誤りやすい思い込み |
|---|---|
| **同着がある**（1着が複数のレースが 37 件） | 「着順は一意」 |
| **取消・除外馬は `win_odds` が NULL**（617 行） | 「オッズは必ずある」。異常なのは*レース内全馬*が NULL のときだけ |
| **中止で `n_races=0` の開催日が 6 日ある** | 「開催日には必ずレースがある」 |
| **開催間隔は最大 34 日**（長期休催） | 「毎週開催」。鮮度チェックの閾値は 45 日 |
| 1日 3〜12 レース / 1レース 4〜10 頭 | 「常に 10〜12 レース」 |
| 枠列は結果ページでは省略されない。**rowspan 省略はオッズパーク側**のみ | 両方同じと思い込む |

**確定オッズは約 25,000 レース未取得**。1req/s で全部やると約 7 時間かかり Actions の
ジョブ上限を超える。`banei odds` は必ず `--since` か `--limit` で区切ること。

**オッズパークは連続アクセスに HTTP 500 を返し始める。** 2026-08-06 に 3,000 件を
1req/s で回したところ、1,400 件を過ぎたあたりから全て 500 になった（同じ URL を
手元から叩くと 200 が返るので、データセンター IP に対するレート制限とみられる）。
対策として:

- スクレイパーは連続 20 件失敗したら**自分で中断して正常終了**する。例外で落とさないのは、
  そのあとの検証とバックアップを走らせて成果を保存するため
- 失敗したレースは `odds_meta` を書かないので、次回の実行で再挑戦される
- バックフィルは 1 回 1,000 件・間隔 2 秒に刻む。中断されたときに失う量を小さくする

**長時間ジョブの成果はバックアップ手順が走るまで保存されない。** 上記の件では実行が
中断され、取得済み約 1,400 レース分がまるごと失われた。DB はランナー上のファイルなので、
最後まで到達しないと何も残らない。

## 環境まわりの既知の事情

- **git commit は GPG 署名必須**。セッションによっては gpg-agent のキャッシュが切れていて
  `Inappropriate ioctl for device` で失敗する。その場合はユーザーに
  `echo test | gpg --clearsign > /dev/null` を実行してもらう。署名を外して回避しない
- `astral-sh/setup-uv` は**移動メジャータグが v7 までしかない**。v8/v9 は解決できないので
  リリースタグ（`v9.0.0`）で固定する
- WSL2 の PATH に Windows の `/mnt/c/Program Files/nodejs/` が残っているが、Linux の
  `/usr/bin` が先に来るので `node`/`npm` は Linux 版が使われる
- `npx wrangler` をリポジトリ直下で実行すると `.wrangler/` にアカウント ID を書く。
  .gitignore 済みだが、public リポジトリなので混入に注意
- Cloudflare R2 は未使用。アカウントでの有効化に支払い方法の登録が必要だったため、
  バックアップは GitHub Releases を使っている

## 進捗

- **Phase 0（土台）完了** — パッケージ化、CI、public 化、バックアップ
- **Phase 1（日次自動化）実装完了、無人稼働の確認待ち** — ゴールデンテスト 27 / 検証テスト 21。
  日次ワークフローは手動実行で全ステップ成功済み。ただし**まだ「取得済みスキップ」の経路しか
  通っていない**。次の開催（8/8 前後）で実際の増分を確認して完了判定する
- Phase 2 以降は未着手。着手前に**ドメイン名・サイト名**と、記事の方向性
  （分析ノート寄り / 予想寄り）を決める必要がある

## 書き方

- ドキュメント・コミットメッセージ・コード内コメントは日本語
- コミットメッセージは「何を」より**「なぜ」**を書く。特に方針を変えた理由
- 未検証のことを完了扱いしない。動作確認の範囲を明示する
