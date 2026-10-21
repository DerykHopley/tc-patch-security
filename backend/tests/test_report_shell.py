"""The review pages on GitHub Pages share one top bar and theme (app/evals/shell.py)."""
import re

import pytest

from app.config import ROOT
from app.evals import shell
from app.evals.__main__ import main

PAGES = ROOT.parent / "docs" / "report"


@pytest.mark.parametrize("page", [p for p, _ in shell.PAGES])
def test_each_published_page_has_the_current_shell(page):
    # Fails after a change to shell.py until `python -m app.evals shell` (and, for index.html, the report build) runs.
    text = (PAGES / page).read_text()
    assert shell.head() in text
    assert shell.bar(page) in text
    if page != "index.html":
        assert shell.apply(text, page) == text


def test_the_bar_links_every_page_and_marks_this_one():
    html = shell.bar("retro.html")
    assert re.findall(r'href="([^"]+)"', html) == ["index.html"] + [p for p, _ in shell.PAGES]
    assert html.count('aria-current="page"') == 1 and '<a href="retro.html" aria-current="page">Retro</a>' in html
    assert 'aria-label="Switch to dark mode"' in html  # the theme button has a name


def test_apply_puts_the_blocks_in_once_and_then_changes_nothing():
    page = ('<html><head><script src="https://cdn.tailwindcss.com"></script></head>'
            '<body class="x"><h1>Retro</h1></body></html>')
    once = shell.apply(page, "retro.html")
    assert once.index("report-shell:tailwind") > once.index("cdn.tailwindcss.com")
    assert once.index("report-shell:head") < once.index("</head>") < once.index("report-shell:bar")
    assert shell.apply(once, "retro.html") == once


def test_dark_mode_turns_each_tailwind_scale_round():
    css = shell.tailwind()
    light, dark = css.split(':root[data-theme="dark"]', 1)
    assert "--tw-slate-100: 241 245 249;" in light and "--tw-slate-100: 15 23 42;" in dark  # 100 takes 900
    assert "--tw-white: 26 26 46;" in dark  # cards become Patch's dark card


def test_the_command_writes_the_shell_into_a_folder(tmp_path, capsys):
    for page, _ in shell.PAGES[1:]:
        (tmp_path / page).write_text("<html><head></head><body></body></html>")
    assert main(["shell", "--dir", str(tmp_path)]) == 0
    assert "Updated: process-map.html" in capsys.readouterr().out
    assert main(["shell", "--dir", str(tmp_path)]) == 0
    assert "already has the current shell" in capsys.readouterr().out
