"""banei コマンドのエントリポイント。

分析系サブコマンド（backtest）は `ml` エクストラを必要とする。
収集系だけを回す CI で重い依存を入れずに済むよう、import は各ハンドラ内で行う。
"""

import argparse

from banei.config import ODDS_DB, RACES_DB, REQUEST_INTERVAL


def _add_interval(p: argparse.ArgumentParser) -> None:
    p.add_argument("--interval", type=float, default=REQUEST_INTERVAL,
                   help=f"リクエスト間隔秒 (default: {REQUEST_INTERVAL})")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="banei", description="ばんえい競馬のデータ収集・分析")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scrape", help="レース結果を収集 (keiba.go.jp)")
    p.add_argument("--start", required=True, metavar="YYYY-MM")
    p.add_argument("--end", required=True, metavar="YYYY-MM")
    p.add_argument("--db", default=RACES_DB)
    _add_interval(p)

    p = sub.add_parser("odds", help="単勝・複勝の確定オッズを収集 (オッズパーク)")
    p.add_argument("--races-db", default=RACES_DB)
    p.add_argument("--db", default=ODDS_DB)
    _add_interval(p)

    p = sub.add_parser("combo-odds", help="組み合わせ券種の確定オッズを収集 (オッズパーク)")
    p.add_argument("--types", default="umatan,umaren,wide,sanrenpuku",
                   help="umatan,umaren,wide,sanrentan,sanrenpuku のカンマ区切り")
    p.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                   help="この日以降のレースに限定（三連単は重いので推奨）")
    p.add_argument("--races-db", default=RACES_DB)
    p.add_argument("--db", default=ODDS_DB)
    _add_interval(p)

    p = sub.add_parser("backtest", help="払戻金ベースの戦略バックテスト")
    p.add_argument("--db", default=RACES_DB)

    p = sub.add_parser("backtest-ev", help="実オッズを使った EV バックテスト")
    p.add_argument("--db", default=RACES_DB)
    p.add_argument("--odds-db", default=ODDS_DB)

    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "scrape":
        from banei.ingest import results
        results.scrape(args.start, args.end, args.db, args.interval)
    elif args.command == "odds":
        from banei.ingest import odds
        odds.scrape(args.races_db, args.db, args.interval)
    elif args.command == "combo-odds":
        from banei.ingest import combo_odds
        combo_odds.scrape(args.types, args.since, args.races_db, args.db, args.interval)
    elif args.command == "backtest":
        from banei.backtest import strategies
        strategies.run(args.db)
    elif args.command == "backtest-ev":
        from banei.backtest import ev
        ev.run(args.db, args.odds_db)


if __name__ == "__main__":
    main()
