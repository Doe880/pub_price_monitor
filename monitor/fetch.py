"""Polite, bounded GETs; public official sites and their menu infrastructure only."""
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Fetcher:
    USER_AGENT = 'MoscowPubPriceMonitor/1.0 (+public-menu-research)'

    def __init__(self, directory: Path, hosts):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.hosts = set(hosts) | {'store.tildaapi.com'}
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.USER_AGENT})
        self.session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET'], respect_retry_after_header=False)))
        self.delay = max(0.5, float(os.getenv('REQUEST_DELAY', '1')))
        self.timeout = float(os.getenv('REQUEST_TIMEOUT', '35'))
        self.last = {}
        self.robots = {}
        self.cache = {}
        self.files = []

    def _check_url(self, url):
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname not in self.hosts or p.username or p.password or p.port not in {None, 443}:
            raise ValueError('URL вне разрешённых официальных источников: ' + url)

    def _get(self, url):
        for _ in range(5):
            self._check_url(url)
            host = urlsplit(url).hostname
            delay = max(self.delay, self.robots.get(host, (None, 0))[1])
            time.sleep(max(0, delay - (time.monotonic() - self.last.get(host, 0))))
            with self.session.get(url, timeout=(10, self.timeout), stream=True,
                                  allow_redirects=False) as r:
                self.last[host] = time.monotonic()
                if r.is_redirect:
                    target = urljoin(url, r.headers['Location'])
                    if urlsplit(target).hostname != host:
                        raise RuntimeError('Перенаправление на другой домен; проверьте конфигурацию')
                    url = target
                    continue
                r.raise_for_status()
                chunks = []
                total = 0
                for chunk in r.iter_content(65536):
                    total += len(chunk)
                    if total > 12_000_000:
                        raise ValueError('Ответ больше 12 МБ')
                    chunks.append(chunk)
                return b''.join(chunks), r.headers.get('Content-Type', ''), url
        raise ValueError('Слишком много перенаправлений')

    def check_robots(self, url):
        """Fail closed if the robots rules for the requested host cannot be checked."""
        self._check_url(url)
        host = urlsplit(url).hostname
        if host not in self.robots:
            robots_url = 'https://' + host + '/robots.txt'
            try:
                b, _, _ = self._get(robots_url)
                rp = RobotFileParser()
                rp.parse(b.decode('utf-8', errors='replace').splitlines())
            except requests.HTTPError as e:
                if e.response.status_code not in {404, 410}:
                    raise RuntimeError('Не удалось проверить robots.txt') from e
                rp = RobotFileParser()
                rp.parse([])
            except (requests.RequestException, ValueError, UnicodeError) as exc:
                raise RuntimeError('Не удалось проверить robots.txt') from exc
            self.robots[host] = (rp, rp.crawl_delay(self.USER_AGENT) or rp.crawl_delay('*') or 0)
        if not self.robots[host][0].can_fetch(self.USER_AGENT, url):
            raise RuntimeError('Сбор запрещён robots.txt: ' + url)

    def save_artifact(self, url, data, kind):
        if len(data) > 12_000_000:
            raise ValueError('Ответ больше 12 МБ')
        digest = hashlib.sha256(data).hexdigest()
        filename = hashlib.sha256((url + ':' + kind).encode()).hexdigest()[:14] + '.' + kind
        path = self.directory / filename
        path.write_bytes(data)
        self.files.append({'url': url, 'path': filename, 'sha256': digest,
                           'content_type': kind})
        (self.directory / 'manifest.json').write_text(
            json.dumps(self.files, ensure_ascii=False, indent=2), encoding='utf-8')
        return data

    def get(self, url, kind='html'):
        if url in self.cache:
            return self.cache[url]
        self.check_robots(url)
        host = urlsplit(url).hostname
        b, ct, final_url = self._get(url)
        if urlsplit(final_url).hostname != host:
            raise RuntimeError('Источник перенаправил на другой домен; проверьте конфигурацию')
        self.check_robots(final_url)
        if kind == 'pdf':
            if not b.startswith(b'%PDF'):
                raise ValueError('Вместо PDF получен другой формат')
            value = b
        elif kind == 'image':
            if not (b.startswith(b'\x89PNG\r\n\x1a\n') or
                    b.startswith(b'\xff\xd8\xff') or
                    (b.startswith(b'RIFF') and b[8:12] == b'WEBP')):
                raise ValueError('Вместо PNG/JPEG/WebP получен другой формат')
            value = b
        elif kind == 'json':
            value = json.loads(b.decode('utf-8-sig'))
        else:
            value = b.decode('utf-8-sig', errors='replace')
            if '<html' not in value.lower() and '<!doctype' not in value.lower():
                raise ValueError('Вместо HTML получен другой формат')
        self.save_artifact(url, b, kind)
        self.cache[url] = value
        return value

    def get_dynamic(self, url, source):
        from .browser_menus import render_menu
        return render_menu(url, source, self)

    def close(self):
        self.session.close()
