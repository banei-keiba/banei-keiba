"""SVG のはみ出し検査（svgcheck.py）のテスト。合成の HTML だけを使う。"""

from banei import svgcheck


def svg(body, w=720, h=340):
    return f'<figure><svg viewBox="0 0 {w} {h}" role="img"><title>題</title>{body}</svg></figure>'


def test_text_inside_passes():
    html = svg('<text class="tick" x="42" y="100" text-anchor="end" '
               'dominant-baseline="middle">1,000</text>')
    assert svgcheck.problems_in(html) == []


def test_end_anchored_text_past_left_edge_is_reported():
    p = svgcheck.problems_in(svg('<text x="10" y="100" text-anchor="end">10,000</text>'))
    assert len(p) == 1 and "10,000" in p[0]


def test_wide_japanese_label_past_right_edge_is_reported():
    # 全角は 1 字幅で数える。半角と同じに数えると見逃す（700 + 6 字 × 12px > 720）
    assert svgcheck.problems_in(svg('<text x="700" y="100">見込みとの差</text>'))


def test_text_above_the_top_is_reported():
    assert svgcheck.problems_in(svg('<text x="100" y="5">勝</text>'))


def test_line_and_path_outside_are_reported():
    p = svgcheck.problems_in(svg('<line x1="0" x2="730" y1="10" y2="10" />'
                                 '<path d="M10,10 L20,-5" />'))
    assert len(p) == 2


def test_title_is_not_a_label():
    long = "とても長いタイトル" * 20
    assert svgcheck.problems_in(f'<svg viewBox="0 0 100 100"><title>{long}</title></svg>') == []


def test_each_svg_uses_its_own_viewbox():
    html = svg('<text x="600" y="100">a</text>') + svg('<text x="600" y="100">a</text>', w=500)
    p = svgcheck.problems_in(html)
    assert len(p) == 1 and p[0].startswith("図 2")


def test_svg_without_viewbox_is_ignored():
    assert svgcheck.problems_in('<svg><line x1="-5" x2="5" y1="0" y2="0" /></svg>') == []


def test_main_fails_without_html(tmp_path):
    # ビルドし忘れを「問題なし」にしない
    assert svgcheck.main(["svgcheck", str(tmp_path)]) == 2


def test_main_reports_file_and_fails(tmp_path, capsys):
    (tmp_path / "a").mkdir()
    (tmp_path / "a/index.html").write_text(
        svg('<text x="10" y="100" text-anchor="end">10,000</text>'), encoding="utf-8")
    assert svgcheck.main(["svgcheck", str(tmp_path)]) == 1
    assert "index.html" in capsys.readouterr().out
