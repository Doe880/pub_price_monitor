"""Browser loader contract tests without network or installed Chromium."""
from types import ModuleType, SimpleNamespace
import sys
import pytest
from monitor.browser_menus import render_menu


class MockPage:
    def __init__(self):
        self.guard = None
        self.navigated = None
    def route(self, pattern, fn):
        assert pattern == "**/*"
        self.guard = fn
    def goto(self, url, **kw):
        self.navigated = url
        return SimpleNamespace(status=200)
    def wait_for_selector(self, selector, **kw):
        assert selector == ".menu-item"
    def locator(self, selector):
        return SimpleNamespace(first=SimpleNamespace(inner_text=lambda **kw:
                               "Стейк — 650 ₽ " * 6))
    def content(self):
        return '<html><div class="menu-item">Стейк — 650 ₽</div></html>'


def fake_playwright(monkeypatch, page):
    class Ctx:
        def new_page(self):
            return page
    class Browser:
        def new_context(self, **kwargs):
            assert kwargs["service_workers"] == "block"
            return Ctx()
        def close(self):
            pass
    class Playwright:
        chromium = SimpleNamespace(launch=lambda **kw: Browser())
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    mod = ModuleType("playwright")
    sync = ModuleType("playwright.sync_api")
    sync.sync_playwright = lambda: Playwright()
    sync.TimeoutError = RuntimeError
    monkeypatch.setitem(sys.modules, "playwright", mod)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync)


def test_browser_fails_before_launch_on_unapproved_domain():
    class Fetcher:
        hosts={"official.example"}
        def check_robots(self, url):
            pass
    with pytest.raises(ValueError, match="объявлены"):
        render_menu("https://official.example/menu",
                    dict(wait_selector=".menu-item", browser_hosts=["evil.example"]),
                    Fetcher())


def test_browser_html_snapshot_and_guard(monkeypatch):
    page = MockPage()
    fake_playwright(monkeypatch, page)
    class Fetcher:
        hosts = {"official.example"}
        USER_AGENT = "Test-Pub-Loader"
        def __init__(self):
            self.allowed = []
            self.snapshots = []
        def check_robots(self, url):
            self.allowed.append(url)
        def save_artifact(self, url, data, kind):
            self.snapshots.append((url, data, kind))
    fetcher = Fetcher()
    source=dict(wait_selector=".menu-item", min_rendered_chars=20)
    html=render_menu("https://official.example/menu", source, fetcher)
    assert "Стейк" in html
    assert fetcher.snapshots[0][2] == "rendered-html"
    class Route:
        def __init__(self, url):
            self.request=SimpleNamespace(url=url)
            self.decision=None
        def abort(self):
            self.decision="blocked"
        def continue_(self):
            self.decision="allowed"
    a=Route("https://external.example/track.js")
    b=Route("https://official.example/menu.json")
    page.guard(a)
    page.guard(b)
    assert a.decision=="blocked"
    assert b.decision=="allowed"
    assert "https://official.example/menu.json" in fetcher.allowed
