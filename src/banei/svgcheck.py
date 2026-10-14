"""ビルドした HTML の SVG 図版で、文字・線・点が viewBox の外へ出ていないかを確かめる。

CLAUDE.md「図版を足すときの決まり」。y 軸の単位や参照線のラベルが viewBox の外に出る事故が
実際にあった。文字の幅はフォントを使わずに見積もる（半角 0.6 字・それ以外 1 字）。
path は絶対座標（M・L・Q・Z）だけを想定する（図版の部品はすべてそう書いている）。
文字どうしの重なりは見ない（目視で確かめる）。

    uv run python -m banei.svgcheck web/dist
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

FONT_PX = 12.0  # global.css の .tick / .axis-label / .point-label
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def text_width(s: str, font_px: float = FONT_PX) -> float:
    """文字列の幅の見積もり。

    半角（U+2000 未満）は 0.6 字、それ以外（漢字・かな・全角記号）は 1 字。
    """
    return sum(font_px * (0.6 if ord(c) < 0x2000 else 1.0) for c in s)


class _Collector(HTMLParser):
    """viewBox のある svg ごとに、text の位置と中身、線・点・path の座標を集める。"""

    def __init__(self) -> None:
        super().__init__()
        self.svgs: list[dict] = []
        self._svg: dict | None = None
        self._text: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}  # 属性名は小文字になる（viewBox → viewbox）

        def num(key: str) -> float:
            return float(a.get(key) or 0)

        if tag == "svg":
            self._svg = None
            if "viewbox" in a:
                _, _, w, h = (float(v) for v in a["viewbox"].split())
                self._svg = {"w": w, "h": h, "texts": [], "points": []}
                self.svgs.append(self._svg)
            return
        if self._svg is None:
            return
        if tag == "text":
            self._text = {"x": num("x"), "y": num("y"), "anchor": a.get("text-anchor", "start"),
                          "middle": a.get("dominant-baseline") == "middle", "s": ""}
        elif tag == "line":
            self._svg["points"] += [(num("x1"), num("y1")), (num("x2"), num("y2"))]
        elif tag == "circle":
            r = num("r")
            self._svg["points"] += [(num("cx") - r, num("cy") - r), (num("cx") + r, num("cy") + r)]
        elif tag == "path":
            nums = [float(n) for n in _NUMBER.findall(a.get("d", ""))]
            self._svg["points"] += list(zip(nums[0::2], nums[1::2], strict=False))

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text["s"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "text" and self._text is not None and self._svg is not None:
            self._svg["texts"].append(self._text)
            self._text = None
        elif tag == "svg":
            self._svg = None


def problems_in(html: str) -> list[str]:
    """HTML 1 ページ分の違反。図の番号はページ内で viewBox のある svg の順（1 始まり）。"""
    c = _Collector()
    c.feed(html)
    out: list[str] = []
    for i, svg in enumerate(c.svgs, start=1):
        w, h = svg["w"], svg["h"]
        for t in svg["texts"]:
            s = t["s"].strip()
            width = text_width(s)
            left = t["x"] - {"middle": width / 2, "end": width}.get(t["anchor"], 0.0)
            if t["middle"]:
                top, bottom = t["y"] - FONT_PX / 2, t["y"] + FONT_PX / 2
            else:
                top, bottom = t["y"] - FONT_PX * 0.8, t["y"] + FONT_PX * 0.2
            if left < 0 or left + width > w or top < 0 or bottom > h:
                out.append(f"図 {i}: 文字「{s}」が viewBox（{w:g}×{h:g}）の外に出る"
                           f"（x {left:.0f}〜{left + width:.0f}, y {top:.0f}〜{bottom:.0f}）")
        for x, y in svg["points"]:
            if not (0 <= x <= w and 0 <= y <= h):
                out.append(f"図 {i}: 座標 ({x:g}, {y:g}) が viewBox（{w:g}×{h:g}）の外にある")
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("web/dist")
    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"{root} に HTML が無い（先に npm run build する）")
        return 2
    found = 0
    for path in pages:
        for p in problems_in(path.read_text(encoding="utf-8")):
            print(f"{path}: {p}")
            found += 1
    print(f"SVG の検査: {len(pages)} ページ・違反 {found} 件")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
