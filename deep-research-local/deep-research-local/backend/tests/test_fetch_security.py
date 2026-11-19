import asyncio

import pytest

from app.config import Settings
from app.fetch import UnsafeURL, assert_public_url, fetch_text, html_to_text, is_public_ip


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.0.5", "169.254.169.254", "::1", "172.16.0.1", "0.0.0.0"])
def test_private_ips_rejected(ip):
    assert not is_public_ip(ip)


def test_public_ip_ok():
    assert is_public_ip("8.8.8.8")


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:8080/x", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "ftp://example.com/x", "http://[::1]/"])
def test_unsafe_urls_blocked(url):
    with pytest.raises(UnsafeURL):
        asyncio.run(assert_public_url(url))


def test_fetch_text_returns_none_for_blocked():
    assert asyncio.run(fetch_text("http://127.0.0.1:9/", Settings())) is None


def test_html_to_text_strips_scripts_and_nav():
    html = "<html><nav>Menu</nav><script>alert(1)</script><p>Real content paragraph goes here.</p></html>"
    out = html_to_text(html)
    assert "Real content" in out and "alert" not in out and "Menu" not in out
