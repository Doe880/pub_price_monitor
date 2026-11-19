"""Optional Playwright loader for client-rendered public official menus.

Only trusted, configured HTTPS hosts can load; all browser requests are checked
against robots.txt and unrelated hosts are blocked.
"""
from urllib.parse import urlsplit

from .models import clean


def render_menu(url, source, fetcher):
    fetcher.check_robots(url)
    selector = source.get("wait_selector")
    if not selector or not isinstance(selector, str) or len(selector) > 180:
        raise ValueError("Для браузерного меню обязательно указать точный CSS wait_selector")
    if source.get("wait_timeout_ms", 12000) > 30000:
        raise ValueError("Слишком большое время ожидания динамического меню")
    allowed = {urlsplit(url).hostname} | set(source.get("browser_hosts", []))
    if not allowed <= fetcher.hosts:
        raise ValueError("Домены браузера должны быть объявлены в sources.json")
    if any("." not in host or host.startswith(".") for host in allowed):
        raise ValueError("Некорректный разрешённый домен")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError as exc:
        raise RuntimeError("Браузерный режим не установлен: pip install -r requirements-browser.txt && python -m playwright install chromium") from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = browser.new_context(user_agent=fetcher.USER_AGENT,
                                          accept_downloads=False,
                                          service_workers="block",
                                          viewport={"width": 1200, "height": 800})
            page = context.new_page()
            def guard(route):
                request_url = route.request.url
                parsed = urlsplit(request_url)
                if parsed.scheme != "https" or parsed.hostname not in allowed:
                    route.abort()
                    return
                try:
                    fetcher.check_robots(request_url)
                except Exception:
                    route.abort()
                    return
                route.continue_()
            page.route("**/*", guard)
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response is None or response.status >= 400:
                raise RuntimeError("Браузер не получил успешный HTML-ответ")
            page.wait_for_selector(selector, state="visible",
                                   timeout=source.get("wait_timeout_ms", 12000))
            # CSS target must contain meaningful text, not a loading skeleton.
            rendered = clean(page.locator(selector).first.inner_text(timeout=5000))
            if len(rendered) < source.get("min_rendered_chars", 60):
                raise ValueError("Динамический каталог пуст или ещё загружается")
            html = page.content()
            if len(html.encode("utf-8")) > 12_000_000:
                raise ValueError("HTML после рендера больше 12 МБ")
            fetcher.save_artifact(url, html.encode("utf-8"), "rendered-html")
            return html
        finally:
            browser.close()
