"""探索 UI のマスの濃淡の上で、文字が読めることを確かめる（目視で色を決めない）。

global.css のトークン（ライト / ダーク）と .heat-N の混色率を読み、WCAG のコントラスト比が
4.5:1 以上かを計算する。color-mix(in srgb, …) は sRGB の値をそのまま線形に混ぜるので、
同じ計算で再現できる。global.css の系列色を検証したスクリプトはこの環境に無いため、
CSS を変えたらここで落ちるようにしておく。
"""

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "web/src/styles/global.css").read_text(
    encoding="utf-8")
AA = 4.5


def _tokens(selector: str) -> dict[str, str]:
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


THEMES = {"light": _tokens(":root"), "dark": _tokens(":root[data-theme='dark']")}
HEAT = {
    int(n): int(p) / 100
    for n, p in re.findall(
        r"\.heat-(\d)\s*\{\s*background:\s*color-mix\(in srgb, var\(--data\) (\d+)%,"
        r" var\(--card\)\);", CSS)
}


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(c) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _mix(a, b, p):
    return tuple(round(x * p + y * (1 - p)) for x, y in zip(a, b, strict=True))


def test_heat_steps_are_defined():
    # 正規表現が CSS とずれて検査が空振りしないこと
    assert sorted(HEAT) == [1, 2, 3, 4]
    assert max(HEAT.values()) <= 0.48


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_cell_text_is_readable_on_heat(theme, step):
    t = THEMES[theme]
    bg = _mix(_rgb(t["data"]), _rgb(t["card"]), HEAT[step])
    assert _contrast(_rgb(t["ink"]), bg) >= AA


@pytest.mark.parametrize("theme", THEMES)
def test_low_n_text_is_readable_on_card(theme):
    # 出走数 100 未満のマスは濃淡を付けず --ink-2 の文字にする
    t = THEMES[theme]
    assert _contrast(_rgb(t["ink-2"]), _rgb(t["card"])) >= AA


@pytest.mark.parametrize("theme", THEMES)
def test_selected_tab_text_is_readable(theme):
    t = THEMES[theme]
    assert _contrast(_rgb(t["card"]), _rgb(t["data"])) >= AA
