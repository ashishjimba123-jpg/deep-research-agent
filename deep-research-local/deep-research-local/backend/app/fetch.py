"""Fetch and extract readable text from web pages, refusing private network addresses (SSRF guard)."""
import asyncio
import ipaddress
import logging
import socket
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .config import Settings

log = logging.getLogger("research.fetch")
HEADERS = {"User-Agent": "DeepResearchLocal/1.0 (educational open-source project)", "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"}
SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg", "iframe", "button"}
BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article", "blockquote"}


class UnsafeURL(ValueError):
    pass


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast


async def assert_public_url(url: str) -> None:
    """Raise UnsafeURL unless the URL is http(s) and every address its host resolves to is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURL("only http(s) URLs are allowed")
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
        addrs = [host]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURL(f"cannot resolve {host}") from exc
        addrs = [i[4][0] for i in infos]
    if not addrs or not all(is_public_ip(a) for a in addrs):
        raise UnsafeURL("address is not public")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    try:  # best extractor when installed
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=False)
        if text and len(text) > 200:
            return text
    except Exception:  # pragma: no cover - extractor optional
        pass
    p = _TextExtractor()
    p.feed(html)
    return "".join(p.parts)


async def fetch_text(url: str, settings: Settings) -> Optional[str]:
    """Return page text or None. Redirects are followed manually so every hop is re-checked."""
    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout, headers=HEADERS, follow_redirects=False) as client:
            current = url
            for _ in range(4):
                await assert_public_url(current)
                async with client.stream("GET", current) as r:
                    if r.is_redirect:
                        current = urljoin(current, r.headers.get("location", ""))
                        continue
                    if r.status_code != 200:
                        return None
                    ctype = r.headers.get("content-type", "").lower()
                    if not any(t in ctype for t in ("text/html", "text/plain", "xhtml")):
                        return None
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > settings.max_page_bytes:
                            break
                    html = bytes(body).decode(r.encoding or "utf-8", errors="ignore")
                    return html if "text/plain" in ctype else html_to_text(html)
            return None
    except UnsafeURL as exc:
        log.info("blocked %s: %s", url, exc)
    except Exception as exc:
        log.info("fetch failed %s: %s", url, exc)
    return None
