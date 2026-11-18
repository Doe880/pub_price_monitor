"""Inspect public official pages without publishing inferred menu prices.

Usage: python -m monitor.probe_sources https://chelsea-pub.ru/menyu/
Robots checks, same-origin redirects and request limits are enforced by Fetcher.
"""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from bs4 import BeautifulSoup
from .fetch import Fetcher
from .models import clean


def inspect(url, format='html', allow_ocr=False, wait_selector=None):
    from urllib.parse import urlsplit
    with TemporaryDirectory() as tmp:
        fetcher = Fetcher(Path(tmp), {urlsplit(url).hostname})
        try:
            if format in {'pdf', 'image'}:
                from .document_menus import extract_text
                data = fetcher.get(url, kind=format)
                extracted, used_ocr = extract_text(data, {'format':format,'allow_ocr':allow_ocr})
                print('URL:',url,'format:',format,'OCR:',used_ocr,'bytes:',len(data))
                print('TEXT PREVIEW (не утверждённые цены):',extracted[:3000])
                return
            if format == 'browser':
                html = fetcher.get_dynamic(url, {'format':'browser','wait_selector':wait_selector})
            else:
                html = fetcher.get(url)
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script','style','noscript']):
                tag.decompose()
            titles = [(t.name, clean(t.get_text(' ', strip=True))[:100])
                      for t in soup.select('h1,h2,h3,h4,h5')][:70]
            prices = soup.find_all(string=lambda s: s and ('₽' in s or 'руб' in s.lower()))
            print('URL:',url,'HTML chars:',len(html),'headings:',titles)
            print('PRICE SAMPLE:',[(clean(p)[:90],p.parent.name,p.parent.get('class',[]),
                                    p.parent.parent.name,p.parent.parent.get('class',[]))
                                   for p in prices[:18]])
            for p in prices[:3]:
                print('PARENT HTML:',str(p.parent.parent)[:850])
        except Exception as exc:
            print('PROBE FAILED:', url, type(exc).__name__, str(exc)[:250])
        finally:
            fetcher.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls',nargs='+')
    parser.add_argument('--format',choices=['html','pdf','image','browser'],default='html')
    parser.add_argument('--allow-ocr',action='store_true')
    parser.add_argument('--wait-selector',help='Обязательный CSS селектор для browser')
    args = parser.parse_args()
    for url in args.urls:
        inspect(url,args.format,args.allow_ocr,args.wait_selector)


if __name__=='__main__':
    main()
