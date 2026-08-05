"""集計結果を JSON として書き出す。Astro のビルド入力になる。

出力先は既定で `web/src/data/`。Astro からは `import data from '~/data/xxx.json'` で
読める。ここに出るのは集計値だけで、生データは含まれない（aggregates.py 参照）。
"""

import datetime as dt
import json
from pathlib import Path

from banei.config import RACES_DB
from banei.export.aggregates import AGGREGATES, connect, policy_violations, summary

DEFAULT_OUT_DIR = Path("web/src/data")


class PolicyError(RuntimeError):
    """公開ポリシーに反する出力を検出した。"""


def build(db_path: Path | str = RACES_DB) -> dict[str, object]:
    """全集計を実行して {出力名: 中身} を返す。

    公開ポリシーに反する内容があれば PolicyError を送出して書き出しを止める。
    生データが 1 度でも公開側へ出ると取り返しがつかないので、ここで落とす。
    """
    con = connect(db_path)
    try:
        out: dict[str, object] = {
            "summary": {
                **summary(con),
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            }
        }
        for name, fn in AGGREGATES.items():
            out[name] = fn(con)
    finally:
        con.close()

    problems = []
    for name, payload in out.items():
        rows = payload if isinstance(payload, list) else [payload]
        # summary の n_jockeys などはグループの大きさではなく実体の個数なので、
        # グループサイズの下限は当てない（個体特定キーの検査は行う）
        problems += policy_violations(name, rows, check_group_size=(name != "summary"))
    if problems:
        raise PolicyError(
            "公開ポリシー違反のため書き出しを中止した:\n  " + "\n  ".join(problems))
    return out


def run(db_path: Path | str = RACES_DB, out_dir: Path | str = DEFAULT_OUT_DIR) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = build(db_path)
    for name, payload in data.items():
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n = len(payload) if isinstance(payload, list) else 1
        print(f"  {path}  ({n} 件)")
    print(f"書き出し完了: {len(data)} ファイル")
