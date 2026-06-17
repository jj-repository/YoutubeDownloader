"""StreamManager — extracts stream URLs from aniworld.to / s.to / bs.to and movie sites via VOE/Vidmoly/Vidoza/Dood/Vinovo/Streamtape/Filemoon.

Extractor logic adapted from AniWorld-Downloader (MIT license).
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import logging
import random
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0"
PROVIDER_ORDER = ["VOE", "Vidmoly", "Vidoza", "Doodstream", "Streamtape", "Filemoon", "Vinovo"]
LANG_MAP = {"1": "German", "2": "English", "3": "German Sub", "4": "Japanese"}
LANG_FALLBACK: dict[str, list[str]] = {
    "German": ["English", "German Sub", "Japanese"],
    "English": ["German Sub", "German", "Japanese"],
    "German Sub": ["English", "German", "Japanese"],
    "Japanese": ["English", "German Sub", "German"],
}

# Maps domain fragment → category ("anime" or "shows").
# Add new sites here; category drives the per-category language setting in the UI.
SITE_CATEGORIES: dict[str, str] = {
    "aniworld.to": "anime",
    "s.to": "shows",
    "bs.to": "shows",
    "cine-to.com": "shows",
    "streamkiste.sx": "shows",
    "hdfilme": "shows",
    "allanime": "anime",
    "animepahe": "anime",
}


def get_site_category(url: str) -> str:
    """Return 'anime' or 'shows' for a stream URL. Falls back to 'shows'."""
    host = urlparse(url).netloc.lower()
    for domain, cat in SITE_CATEGORIES.items():
        if domain in host:
            return cat
    return "shows"


# ---------------------------------------------------------------------------
# URL helpers (public — imported by downloader_pyqt6)
# ---------------------------------------------------------------------------

_EPISODE_PAT = re.compile(
    r"^https://(aniworld\.to|s\.to)/(anime|serie)/stream/[^/]+"
    r"/(staffel-\d+/episode-\d+|filme/film-\d+)/?$"
)
_SEASON_PAT = re.compile(
    r"^https://(aniworld\.to|s\.to)/(anime|serie)/stream/[^/]+"
    r"/(staffel-\d+|filme)/?$"
)

# bs.to: https://bs.to/serie/Show-Name/1/3-Episode-Title
_BSTO_EPISODE_PAT = re.compile(r"^https://bs\.to/serie/[^/]+/\d+/\d+-[^/]+/?$")
_BSTO_SEASON_PAT = re.compile(r"^https://bs\.to/serie/[^/]+/\d+/?$")

# cine-to.com: film or serie episode
_CINETO_EPISODE_PAT = re.compile(
    r"^https?://(?:www\.)?cine-to\.com/(?:film/[^/]+|serie/[^/]+/staffel-\d+/episode-\d+)/?$"
)
_CINETO_SEASON_PAT = re.compile(r"^https?://(?:www\.)?cine-to\.com/serie/[^/]+/staffel-\d+/?$")

# hdfilme.deals: film or serie episode
_HDFILME_EPISODE_PAT = re.compile(
    r"^https?://(?:www\.)?hdfilme\.[a-z]+/(?:film/[^/]+|serie/[^/]+/staffel-\d+/episode-\d+)/?$"
)
_HDFILME_SEASON_PAT = re.compile(r"^https?://(?:www\.)?hdfilme\.[a-z]+/serie/[^/]+/staffel-\d+/?$")

# allanime: show page treated as season (all eps)
_ALLANIME_PAT = re.compile(r"^https?://(?:www\.)?allanime\.[a-z]+/anime/[^/]+")

# animepahe: show page treated as season
_ANIMEPAHE_PAT = re.compile(r"^https?://(?:www\.)?animepahe\.[a-z]+/anime/[^/?#]+/?$")

# aniworld.to / s.to canonical URLs carry a "/stream/" segment, but s.to URLs
# copied from the browser address bar omit it. Insert it when missing so both
# forms are accepted and fetched against the canonical page.
_STREAM_INSERT_PAT = re.compile(r"^(https://(?:aniworld\.to|s\.to)/(?:anime|serie))/(?!stream/)")


def normalize_stream_url(url: str) -> str:
    """Insert the '/stream/' segment for aniworld/s.to URLs that lack it."""
    return _STREAM_INSERT_PAT.sub(r"\1/stream/", url.strip())


def is_stream_episode_url(url: str) -> bool:
    u = normalize_stream_url(url)
    if u.startswith("allanime://") or u.startswith("animepahe://"):
        return True
    return bool(
        _EPISODE_PAT.match(u)
        or _BSTO_EPISODE_PAT.match(u)
        or _CINETO_EPISODE_PAT.match(u)
        or _HDFILME_EPISODE_PAT.match(u)
    )


def is_stream_season_url(url: str) -> bool:
    u = normalize_stream_url(url)
    return bool(
        _SEASON_PAT.match(u)
        or _BSTO_SEASON_PAT.match(u)
        or _CINETO_SEASON_PAT.match(u)
        or _HDFILME_SEASON_PAT.match(u)
        or _ALLANIME_PAT.match(u)
        or _ANIMEPAHE_PAT.match(u)
    )


def _is_bsto(url: str) -> bool:
    return "bs.to" in url


def _is_cineto(url: str) -> bool:
    return "cine-to.com" in url


def _is_hdfilme(url: str) -> bool:
    return "hdfilme." in url


def _is_allanime(url: str) -> bool:
    return "allanime." in url


def _is_animepahe(url: str) -> bool:
    return "animepahe." in url


def stream_series_name(url: str) -> str:
    if url.startswith("allanime://"):
        from managers.anime_providers import allanime_show_name

        return allanime_show_name(url)
    if url.startswith("animepahe://"):
        from managers.anime_providers import animepahe_show_name

        return animepahe_show_name(url)
    if _is_bsto(url):
        m = re.search(r"/serie/([^/]+)/", url)
        return m.group(1).replace("-", " ").title() if m else "episode"
    if _is_cineto(url) or _is_hdfilme(url):
        m = re.search(r"/(?:film|serie)/([^/?#]+)", url)
        return m.group(1).replace("-", " ").title() if m else "movie"
    if _is_allanime(url):
        m = re.search(r"/anime/([^/?#]+)/([^/?#]+)", url)
        name = m.group(2) if m else url.rstrip("/").split("/")[-1]
        return name.replace("-", " ").replace("_", " ").title()
    if _is_animepahe(url):
        m = re.search(r"/anime/(.+?)(?:-[0-9a-f-]{36})?/?$", url.rstrip("/"))
        return m.group(1).replace("-", " ").title() if m else "anime"
    m = re.search(r"/stream/([^/]+)/", url)
    return m.group(1).replace("-", " ").title() if m else "episode"


def stream_season_num(url: str) -> int:
    if url.startswith(("allanime://", "animepahe://")):
        return 1
    if _is_bsto(url):
        m = re.search(r"/serie/[^/]+/(\d+)", url)
        return int(m.group(1)) if m else 1
    m = re.search(r"staffel-(\d+)", url)
    return int(m.group(1)) if m else 1


def stream_episode_num(url: str) -> int:
    if url.startswith("allanime://"):
        from managers.anime_providers import allanime_episode_num

        return allanime_episode_num(url)
    if url.startswith("animepahe://"):
        from managers.anime_providers import animepahe_episode_num

        return animepahe_episode_num(url)
    if _is_bsto(url):
        m = re.search(r"/(\d+)-[^/]+/?$", url.rstrip("/"))
        return int(m.group(1)) if m else 0
    m = re.search(r"(?:episode|film)-(\d+)$", url.rstrip("/"))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# HTTP (module-level shared session)
# ---------------------------------------------------------------------------

_jar = http.cookiejar.CookieJar()
_opener = build_opener(HTTPCookieProcessor(_jar))


_CAPTCHA_MARKERS = (
    "just a moment",
    "cf-turnstile",
    "checking your browser",
    "enable javascript and cookies",
    "ddos protection by cloudflare",
    "challenge-running",
    "cf_chl_",
    "hcaptcha.com",
    "player-prepare-turnstile",
)

_CF_SOLVE_TIMEOUT = 300  # seconds


def _is_captcha_page(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in _CAPTCHA_MARKERS)


def _human_move(page, x: float, y: float) -> None:
    """Move mouse to (x, y) with human-like intermediate steps and timing."""
    page.mouse.move(
        x - random.uniform(60, 120),
        y + random.uniform(-15, 15),
    )
    page.mouse.move(
        x + random.uniform(-2, 2),
        y + random.uniform(-2, 2),
        steps=random.randint(8, 16),
    )


def _inject_cookies(pw_cookies: list) -> None:
    """Copy cookies from a patchright context into the shared urllib CookieJar."""
    for c in pw_cookies:
        expires = c.get("expires")
        if expires and expires < 0:
            expires = None
        cookie = http.cookiejar.Cookie(
            version=0,
            name=c["name"],
            value=c["value"],
            port=None,
            port_specified=False,
            domain=c.get("domain", ""),
            domain_specified=bool(c.get("domain")),
            domain_initial_dot=c.get("domain", "").startswith("."),
            path=c.get("path", "/"),
            path_specified=bool(c.get("path")),
            secure=c.get("secure", False),
            expires=int(expires) if expires else None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
        )
        _jar.set_cookie(cookie)


def _solve_cloudflare(url: str) -> bool:
    """Open a patchright Chromium window and auto-solve the Cloudflare Turnstile.

    Injects the resulting cookies into the shared urllib session on success.
    Returns True if solved within the timeout, False otherwise.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "patchright not installed — run: pip install patchright && patchright install chromium"
        )
        return False

    logger.info("Cloudflare challenge detected — opening Chromium to auto-solve...")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(user_agent=UA, locale="en-US")
            page = context.new_page()
            page.goto(url, timeout=30_000)

            deadline = time.time() + _CF_SOLVE_TIMEOUT
            solved = False

            while time.time() < deadline:
                # Success: cf_clearance cookie present
                if any(c["name"] == "cf_clearance" for c in context.cookies()):
                    solved = True
                    break

                # Try to interact with the Turnstile iframe
                try:
                    iframe_el = page.query_selector("iframe[src*='challenges.cloudflare.com']")
                    if iframe_el:
                        bbox = iframe_el.bounding_box()
                        frame = iframe_el.content_frame()
                        if bbox and frame:
                            # Already solved inside the frame?
                            token = frame.query_selector("input[name='cf-turnstile-response']")
                            if token and len(token.get_attribute("value") or "") > 20:
                                solved = True
                                break

                            # Find and click the checkbox
                            checkbox = frame.query_selector(
                                ".ctp-checkbox-label, #cf-stage, input[type='checkbox']"
                            )
                            if checkbox:
                                cb = checkbox.bounding_box()
                                if cb:
                                    cx = bbox["x"] + cb["x"] + cb["width"] / 2
                                    cy = bbox["y"] + cb["y"] + cb["height"] / 2
                                    _human_move(page, cx, cy)
                                    time.sleep(random.uniform(0.05, 0.15))
                                    page.mouse.down()
                                    time.sleep(random.uniform(0.05, 0.20))
                                    page.mouse.up()
                                    time.sleep(random.uniform(0.8, 1.5))
                                    continue
                except Exception as e:
                    logger.debug(f"Turnstile interaction attempt: {e}")

                time.sleep(0.5)

            if solved:
                _inject_cookies(context.cookies())
                logger.info("Cloudflare challenge solved — cookies injected")

            browser.close()
            return solved

    except Exception as e:
        logger.error(f"patchright solver error: {e}")
        return False


def _get(url: str, extra_headers: dict | None = None) -> tuple[str, str]:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "identity",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = Request(url, headers=headers)
    with _opener.open(req, timeout=20) as resp:
        final_url = resp.geturl()
        html = resp.read().decode("utf-8", errors="replace")

    if _is_captcha_page(html):
        if not _solve_cloudflare(url):
            raise RuntimeError(
                "Cloudflare challenge could not be solved automatically. "
                "Ensure patchright is installed: pip install patchright && patchright install chromium"
            )
        # Retry with injected cookies
        req2 = Request(url, headers=headers)
        with _opener.open(req2, timeout=20) as resp2:
            final_url = resp2.geturl()
            html = resp2.read().decode("utf-8", errors="replace")
        if _is_captcha_page(html):
            raise RuntimeError("Cloudflare challenge solved but still blocked on retry.")

    return final_url, html


def _cookie_header() -> str:
    return "; ".join(f"{c.name}={c.value}" for c in _jar)


# ---------------------------------------------------------------------------
# VOE decode (from AniWorld-Downloader, MIT)
# ---------------------------------------------------------------------------

_JUNK = ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]
_REDIRECT_PAT = re.compile(r"""['"](\s*https?://[^'"<>\s]+/e/[^'"<>\s]+)['"]""")
_B64_PAT = re.compile(r"var a168c='([^']+)'")
_HLS_PAT = re.compile(r"'hls':\s*'(?P<hls>[^']+)'")


def _shift_letters(s: str) -> str:
    out = []
    for c in s:
        n = ord(c)
        if 65 <= n <= 90:
            n = (n - 65 + 13) % 26 + 65
        elif 97 <= n <= 122:
            n = (n - 97 + 13) % 26 + 97
        out.append(chr(n))
    return "".join(out)


def _decode_voe(encoded: str) -> dict:
    s = _shift_letters(encoded)
    for j in _JUNK:
        s = s.replace(j, "_")
    s = s.replace("_", "")
    s = base64.b64decode(s).decode()
    s = "".join(chr(ord(c) - 3) for c in s)
    s = base64.b64decode(s[::-1]).decode()
    return json.loads(s)


def _voe_source_from_html(html: str) -> str | None:
    for block in re.findall(
        r'<script\s+type=["\']application/json["\']>(.*?)</script>', html, re.DOTALL
    ):
        try:
            t = block.strip().strip('"')
            d = _decode_voe(t.encode().decode("unicode_escape"))
            if d.get("source"):
                return d["source"]
        except Exception:
            pass
    m = _B64_PAT.search(html)
    if m:
        try:
            d = _decode_voe(m.group(1))
            if d.get("source"):
                return d["source"]
        except Exception:
            pass
    m = _HLS_PAT.search(html)
    if m:
        return m.group("hls")
    return None


def _extract_voe(embed_url: str) -> tuple[str, str]:
    logger.debug("VOE: fetching embed page")
    _, html = _get(embed_url, {"Referer": "https://voe.sx/"})
    source = _voe_source_from_html(html)
    if not source:
        m = _REDIRECT_PAT.search(html)
        if m:
            logger.debug("VOE: following internal redirect")
            _, html2 = _get(m.group(1).strip(), {"Referer": embed_url})
            source = _voe_source_from_html(html2)
    if not source:
        raise ValueError("VOE: could not extract stream URL")
    return source, embed_url


# ---------------------------------------------------------------------------
# Vidmoly
# ---------------------------------------------------------------------------

_VIDMOLY_FILE_PAT = re.compile(r'file\s*:\s*[\'"]([^\'"]+?\.m3u8[^\'"]*)[\'"]')


def _extract_vidmoly(embed_url: str) -> tuple[str, str]:
    logger.debug("Vidmoly: fetching embed page")
    _, html = _get(embed_url, {"Referer": "https://vidmoly.biz"})
    scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE))
    m = _VIDMOLY_FILE_PAT.search(scripts)
    if not m:
        raise ValueError("Vidmoly: could not extract stream URL")
    return m.group(1), "https://vidmoly.biz"


# ---------------------------------------------------------------------------
# Vidoza
# ---------------------------------------------------------------------------

_VIDOZA_SRC_PAT = re.compile(r'src:\s*"([^"]+)"')


def _extract_vidoza(embed_url: str) -> tuple[str, str]:
    logger.debug("Vidoza: fetching embed page")
    _, html = _get(embed_url, {"Referer": embed_url})
    if "sourcesCode:" not in html:
        raise ValueError("Vidoza: sourcesCode not found")
    m = _VIDOZA_SRC_PAT.search(html)
    if not m:
        raise ValueError("Vidoza: could not extract stream URL")
    return m.group(1), embed_url


# ---------------------------------------------------------------------------
# Doodstream (dood.to / doodstream.com)
# ---------------------------------------------------------------------------

_DOOD_MD5_PAT = re.compile(r"[\"'](/pass_md5/[^\"']+)[\"']")


def _extract_doodstream(embed_url: str) -> tuple[str, str]:
    logger.debug("Doodstream: fetching embed page")
    parsed = urlparse(embed_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    vid_id = parsed.path.rstrip("/").split("/")[-1]
    embed_url = f"{base}/e/{vid_id}"
    referer = f"{base}/"

    _, html = _get(embed_url, {"Referer": referer})
    m = _DOOD_MD5_PAT.search(html)
    if not m:
        raise ValueError("Doodstream: pass_md5 token not found")

    _, base_seg = _get(f"{base}{m.group(1)}", {"Referer": referer})
    token = "".join(
        random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", k=10)
    )
    expiry = int(time.time() * 1000)
    return f"{base_seg.strip()}{token}?token={token}&expiry={expiry}", referer


# ---------------------------------------------------------------------------
# Vinovo (vinovo.to)
# ---------------------------------------------------------------------------

_VINOVO_M3U8_PAT = re.compile(r'["\']([^"\']+\.m3u8[^"\']*)["\']')
_VINOVO_FILE_PAT = re.compile(r'(?:file|src)\s*:\s*["\']([^"\']{20,})["\']')


def _extract_vinovo(embed_url: str) -> tuple[str, str]:
    logger.debug("Vinovo: fetching embed page")
    _, html = _get(embed_url, {"Referer": embed_url})
    m = _VINOVO_M3U8_PAT.search(html)
    if m:
        return m.group(1), embed_url
    m = _VINOVO_FILE_PAT.search(html)
    if m:
        return m.group(1), embed_url
    raise ValueError("Vinovo: could not extract stream URL")


# ---------------------------------------------------------------------------
# P,A,C,K,E,D JS unpacker (shared by Filemoon + Kwik)
# ---------------------------------------------------------------------------

_PACKER_PAT = re.compile(
    r"}\s*\(\s*'((?:[^'\\]|\\.)*)',\s*(\d+),\s*\d+,\s*'((?:[^'\\]|\\.)*)'\s*\.split\('\|'\)",
    re.DOTALL,
)


def _from_base(s: str, base: int) -> int:
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = 0
    for c in s:
        result = result * base + chars.index(c)
    return result


def _unpack_packer(packed: str) -> str:
    m = _PACKER_PAT.search(packed)
    if not m:
        return packed
    p_val, a_val, k_vals = m.group(1), int(m.group(2)), m.group(3).split("|")

    def _lookup(word: str) -> str:
        try:
            idx = _from_base(word, a_val)
        except (ValueError, IndexError):
            return word
        return k_vals[idx] if idx < len(k_vals) and k_vals[idx] else word

    return re.sub(r"\b(\w+)\b", lambda mm: _lookup(mm.group(1)), p_val)


# ---------------------------------------------------------------------------
# Streamtape
# ---------------------------------------------------------------------------


def _extract_streamtape(embed_url: str) -> tuple[str, str]:
    logger.debug("Streamtape: fetching embed page")
    _, html = _get(embed_url, {"Referer": embed_url})
    # The page splits the video URL across two elements:
    #   ideoooolink → base path, norobotlink → token suffix (set via JS)
    base_m = re.search(r'id=["\']ideoooolink["\'][^>]*>([^<]+)<', html)
    tok_m = re.search(
        r"getElementById\(['\"]norobotlink['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]",
        html,
    )
    if not tok_m:
        tok_m = re.search(r'id=["\']norobotlink["\'][^>]*>([^<]*)<', html)
    if base_m and tok_m:
        url = f"https:{base_m.group(1).strip()}{tok_m.group(1).strip()}"
        return url.replace("&amp;", "&"), embed_url
    raise ValueError("Streamtape: could not extract stream URL")


# ---------------------------------------------------------------------------
# Filemoon (filemoon.sx / filemoon.to)
# ---------------------------------------------------------------------------

_FILEMOON_M3U8_PAT = re.compile(r'["\']([^"\']+\.m3u8[^"\']*)["\']')


def _extract_filemoon(embed_url: str) -> tuple[str, str]:
    logger.debug("Filemoon: fetching embed page")
    _, html = _get(embed_url, {"Referer": embed_url})
    # Find packed JS block and unpack it
    scripts = re.findall(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\(.*?\)\)", html, re.DOTALL)
    for block in scripts:
        unpacked = _unpack_packer(block)
        m = _FILEMOON_M3U8_PAT.search(unpacked)
        if m:
            return m.group(1), embed_url
    # Fallback: m3u8 directly in HTML
    m = _FILEMOON_M3U8_PAT.search(html)
    if m:
        return m.group(1), embed_url
    raise ValueError("Filemoon: could not extract stream URL")


# ---------------------------------------------------------------------------
# Kwik (kwik.cx) — used by AnimePahe
# ---------------------------------------------------------------------------

_KWIK_M3U8_PAT = re.compile(r"source\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]")


def _extract_kwik(embed_url: str, referer: str = "https://animepahe.ru/") -> tuple[str, str]:
    logger.debug(f"Kwik: fetching {embed_url}")
    _, html = _get(embed_url, {"Referer": referer})
    scripts = re.findall(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\(.*?\)\)", html, re.DOTALL)
    for block in scripts:
        unpacked = _unpack_packer(block)
        m = _KWIK_M3U8_PAT.search(unpacked)
        if m:
            return m.group(1), embed_url
    raise ValueError("Kwik: could not extract m3u8 URL")


_EXTRACTORS: dict = {
    "voe": _extract_voe,
    "vidmoly": _extract_vidmoly,
    "vidoza": _extract_vidoza,
    "videzz": _extract_vidoza,
    "dood": _extract_doodstream,
    "doodstream": _extract_doodstream,
    "vinovo": _extract_vinovo,
    "streamtape": _extract_streamtape,
    "filemoon": _extract_filemoon,
    "kwik": _extract_kwik,
}

# ---------------------------------------------------------------------------
# Episode page provider parsing
# ---------------------------------------------------------------------------


def _parse_providers(html: str, base_domain: str) -> dict:
    result: dict = {}
    li_pat = re.compile(r'<li\s+[^>]*data-lang-key="(?P<k>\d+)"[^>]*>(?P<c>.*?)</li>', re.DOTALL)
    h4_pat = re.compile(r"<h4>(.*?)</h4>", re.DOTALL)
    a_pat = re.compile(r'<a\s+[^>]*class="watchEpisode"[^>]*href="([^"]+)"', re.DOTALL)
    for m in li_pat.finditer(html):
        lang = LANG_MAP.get(m.group("k"))
        if not lang:
            continue
        c = m.group("c")
        h4 = h4_pat.search(c)
        a = a_pat.search(c)
        if not h4 or not a:
            continue
        provider = h4.group(1).strip()
        href = a.group(1)
        url = f"{base_domain}{href}" if href.startswith("/") else href
        result.setdefault(lang, {})[provider] = url
    return result


# ---------------------------------------------------------------------------
# StreamManager
# ---------------------------------------------------------------------------


class StreamManager:
    def get_season_episodes(self, season_url: str) -> list[str]:
        """Fetch all episode URLs from a season page, sorted by episode number."""
        if _is_cineto(season_url):
            return self._get_cineto_season_episodes(season_url)
        if _is_hdfilme(season_url):
            return self._get_hdfilme_season_episodes(season_url)
        if _is_allanime(season_url) or _is_animepahe(season_url):
            from managers.anime_providers import get_anime_episodes

            return get_anime_episodes(season_url)

        parsed = urlparse(season_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        logger.info(f"Fetching season page: {season_url}")
        _, html = _get(season_url)

        if _is_bsto(season_url):
            ep_pat = re.compile(r'href="(/serie/[^/]+/\d+/\d+-[^"]+)"')

            def ep_key(u: str) -> int:
                return int(re.search(r"/(\d+)-[^/]+/?$", u).group(1))

        else:
            ep_pat = re.compile(
                r'href="(/(?:anime|serie)/stream/[^/]+/'
                r'(?:staffel-\d+/episode-\d+|filme/film-\d+))"'
            )

            def ep_key(u: str) -> int:  # type: ignore[no-redef]
                return int(re.search(r"\d+$", u).group())

        seen: set[str] = set()
        episodes: list[str] = []
        for m in ep_pat.finditer(html):
            url = f"{domain}{m.group(1)}"
            if url not in seen:
                seen.add(url)
                episodes.append(url)
        episodes.sort(key=ep_key)
        logger.info(f"Found {len(episodes)} episodes in season")
        return episodes

    def get_stream(self, episode_url: str, language: str, provider: str) -> tuple[str, str]:
        """Return (stream_url, referer) for the given episode URL."""
        if _is_cineto(episode_url):
            return self._get_cineto_stream(episode_url, language, provider)
        if _is_hdfilme(episode_url):
            return self._get_hdfilme_stream(episode_url, language, provider)
        if episode_url.startswith(("allanime://", "animepahe://")):
            from managers.anime_providers import get_anime_stream

            return get_anime_stream(episode_url)
        parsed = urlparse(episode_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        logger.info(f"Fetching episode page: {episode_url}")
        _, html = _get(episode_url)
        providers = _parse_providers(html, domain)

        if not providers:
            raise ValueError("No provider links found — is this an episode page?")

        # Apply fallback chain if selected language isn't available
        effective_lang = language
        if effective_lang not in providers:
            for fallback in LANG_FALLBACK.get(effective_lang, []):
                if fallback in providers:
                    logger.info(f"'{effective_lang}' not available — falling back to '{fallback}'")
                    effective_lang = fallback
                    break
            else:
                raise ValueError(f"'{effective_lang}' not available. Found: {list(providers)}")

        available = providers[effective_lang]
        logger.info(f"Available providers for {effective_lang}: {list(available)}")

        if provider == "Auto":
            try_list = [p for p in PROVIDER_ORDER if p in available] + [
                p for p in available if p not in PROVIDER_ORDER
            ]
        else:
            if provider not in available:
                raise ValueError(f"'{provider}' not available. Found: {list(available)}")
            try_list = [provider]

        last_error: Exception | None = None
        for p in try_list:
            try:
                logger.info(f"Trying provider: {p}")
                embed_url, _ = _get(available[p])
                embed_host = urlparse(embed_url).netloc.lower()
                extractor = next((fn for key, fn in _EXTRACTORS.items() if key in embed_host), None)
                if extractor is None:
                    raise ValueError(f"No extractor for host: {embed_host}")
                return extractor(embed_url)
            except Exception as e:
                logger.warning(f"{p} failed: {e}")
                last_error = e

        raise ValueError(f"All providers failed. Last error: {last_error}")

    # ------------------------------------------------------------------
    # cine-to.com
    # ------------------------------------------------------------------

    def _get_cineto_stream(self, page_url: str, language: str, provider: str) -> tuple[str, str]:
        parsed = urlparse(page_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        headers_ajax = {"X-Requested-With": "XMLHttpRequest", "Referer": page_url}

        # Fetch the page to get the content ID
        logger.info(f"cine-to.com: fetching page {page_url}")
        _, html = _get(page_url)

        # Extract content ID from the page
        id_m = re.search(r'data-id=["\'](\d+)["\']', html)
        if not id_m:
            id_m = re.search(r"/(?:film|serie)/[^/]+-(\d+)/?", page_url)
        if not id_m:
            raise ValueError("cine-to.com: could not find content ID")
        content_id = id_m.group(1)

        lang_key = {"German": "1", "English": "2", "German Sub": "3"}.get(language, "1")

        # Fetch provider links — GET result unused; POST is done below via urllib
        _get(
            f"{base}/request/links",
            {**headers_ajax, "Content-Type": "application/x-www-form-urlencoded"},
        )
        # Actually need POST — use urllib manually
        import urllib.parse as _up
        import urllib.request as _ur

        post_data = _up.urlencode({"id": content_id, "lang": lang_key}).encode()
        req = _ur.Request(
            f"{base}/request/links",
            data=post_data,
            headers={**{"User-Agent": UA, "Referer": page_url}, **headers_ajax},
        )
        with _opener.open(req, timeout=15) as resp:
            links_json = json.loads(resp.read().decode("utf-8", errors="replace"))

        if not links_json:
            raise ValueError("cine-to.com: no links returned from API")

        logger.info(f"cine-to.com: got {len(links_json)} provider links")

        order_lower = [p.lower() for p in PROVIDER_ORDER]
        if provider == "Auto":
            sorted_links = sorted(
                links_json,
                key=lambda x: next(
                    (i for i, k in enumerate(order_lower) if k in x.get("name", "").lower()),
                    len(order_lower),
                ),
            )
        else:
            pl = provider.lower()
            sorted_links = [x for x in links_json if pl in x.get("name", "").lower()]
            if not sorted_links:
                raise ValueError(f"cine-to.com: provider '{provider}' not found")

        last_error: Exception | None = None
        for link in sorted_links:
            try:
                link_id = link.get("id") or link.get("link_id")
                out_url, _ = _get(f"{base}/out/{link_id}", {"Referer": page_url})
                embed_host = urlparse(out_url).netloc.lower()
                extractor = next((fn for key, fn in _EXTRACTORS.items() if key in embed_host), None)
                if extractor:
                    logger.info(f"cine-to.com: using {link.get('name')} → {embed_host}")
                    return extractor(out_url)
                logger.warning(f"cine-to.com: no extractor for {embed_host}")
            except Exception as e:
                logger.warning(f"cine-to.com link failed: {e}")
                last_error = e

        raise ValueError(f"cine-to.com: all providers failed. Last: {last_error}")

    def _get_cineto_season_episodes(self, season_url: str) -> list[str]:
        parsed = urlparse(season_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        _, html = _get(season_url)
        ep_pat = re.compile(r'href="(/serie/[^"]+/staffel-\d+/episode-\d+/?)"')
        seen: set[str] = set()
        episodes: list[str] = []
        for m in ep_pat.finditer(html):
            url = f"{base}{m.group(1)}"
            if url not in seen:
                seen.add(url)
                episodes.append(url)
        episodes.sort(key=lambda u: int(re.search(r"episode-(\d+)", u).group(1)))
        return episodes

    # ------------------------------------------------------------------
    # hdfilme.deals
    # ------------------------------------------------------------------

    _HDFILME_LANG_MAP = {"German": "de", "English": "en", "German Sub": "de-sub"}

    def _get_hdfilme_stream(self, page_url: str, language: str, provider: str) -> tuple[str, str]:
        parsed = urlparse(page_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        logger.info(f"hdfilme: fetching page {page_url}")
        _, html = _get(page_url)

        # <a class="watchEpisode" href="/out/..." data-lang="de" data-id="...">VOE</a>
        link_pat = re.compile(
            r'<a[^>]+class="[^"]*watchEpisode[^"]*"[^>]+href="([^"]+)"[^>]*data-lang="([^"]*)"[^>]*>([^<]*)<',
            re.IGNORECASE,
        )
        lang_pref = self._HDFILME_LANG_MAP.get(language, "de")
        providers_by_lang: dict[str, list[tuple[str, str]]] = {}
        for m in link_pat.finditer(html):
            href, lang_val, name = m.group(1), m.group(2).lower(), m.group(3).strip()
            url = f"{base}{href}" if href.startswith("/") else href
            providers_by_lang.setdefault(lang_val, []).append((name, url))

        candidates = providers_by_lang.get(lang_pref) or next(iter(providers_by_lang.values()), [])
        if not candidates:
            raise ValueError(f"hdfilme: no provider links found (lang={lang_pref})")

        order_lower = [p.lower() for p in PROVIDER_ORDER]
        if provider == "Auto":
            candidates = sorted(
                candidates,
                key=lambda x: next(
                    (i for i, k in enumerate(order_lower) if k in x[0].lower()), len(order_lower)
                ),
            )
        else:
            pl = provider.lower()
            candidates = [(n, u) for n, u in candidates if pl in n.lower()]
            if not candidates:
                raise ValueError(f"hdfilme: provider '{provider}' not found")

        last_error: Exception | None = None
        for name, out_url in candidates:
            try:
                final_url, _ = _get(out_url, {"Referer": page_url})
                embed_host = urlparse(final_url).netloc.lower()
                extractor = next((fn for key, fn in _EXTRACTORS.items() if key in embed_host), None)
                if extractor:
                    logger.info(f"hdfilme: using {name} → {embed_host}")
                    return extractor(final_url)
                logger.warning(f"hdfilme: no extractor for {embed_host}")
            except Exception as e:
                logger.warning(f"hdfilme provider '{name}' failed: {e}")
                last_error = e

        raise ValueError(f"hdfilme: all providers failed. Last: {last_error}")

    def _get_hdfilme_season_episodes(self, season_url: str) -> list[str]:
        parsed = urlparse(season_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        _, html = _get(season_url)
        ep_pat = re.compile(r'href="(/serie/[^"]+/staffel-\d+/episode-\d+/?)"')
        seen: set[str] = set()
        episodes: list[str] = []
        for m in ep_pat.finditer(html):
            url = f"{base}{m.group(1)}"
            if url not in seen:
                seen.add(url)
                episodes.append(url)
        episodes.sort(key=lambda u: int(re.search(r"episode-(\d+)", u).group(1)))
        return episodes

    def select_hls_quality(self, master_url: str, target_height: int) -> str:
        """Parse a master M3U8 and return the variant URL closest to target_height.

        Falls back to highest available when target exceeds all variants.
        Returns master_url unchanged if it is not a master playlist.
        """
        try:
            _, content = _get(master_url, {"Accept": "*/*", "Referer": master_url})
        except Exception as e:
            logger.warning(f"Could not fetch master M3U8 for quality selection: {e}")
            return master_url

        variants: list[tuple[int, int, str]] = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            res_m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            bw_m = re.search(r"BANDWIDTH=(\d+)", line)
            if res_m and i + 1 < len(lines):
                height = int(res_m.group(2))
                bandwidth = int(bw_m.group(1)) if bw_m else 0
                url = lines[i + 1].strip()
                if not url.startswith("http"):
                    url = urljoin(master_url, url)
                variants.append((height, bandwidth, url))

        if not variants:
            return master_url

        candidates = [(h, bw, u) for h, bw, u in variants if h <= target_height]
        best = (
            max(candidates, key=lambda x: (x[0], x[1]))
            if candidates
            else max(variants, key=lambda x: (x[0], x[1]))
        )
        logger.info(
            f"HLS quality: selected {best[0]}p (target {target_height}p, available {[h for h, _, _ in variants]})"
        )
        return best[2]

    def run_ffmpeg(
        self,
        stream_url: str,
        referer: str,
        output_path: Path,
        stop_event: threading.Event | None = None,
        volume: float = 1.0,
        status_cb=None,
    ) -> bool:
        """Download HLS stream via ffmpeg. Returns True on success.

        status_cb(speed: str, bitrate: str) is called whenever ffmpeg emits
        progress stats (throttled — not every line).
        """
        cookies = _cookie_header()
        header_str = f"User-Agent: {UA}\r\nReferer: {referer}\r\n"
        if cookies:
            header_str += f"Cookie: {cookies}\r\n"

        apply_volume = abs(volume - 1.0) >= 0.01
        if apply_volume:
            codec_args = ["-c:v", "copy", "-c:a", "aac", "-af", f"volume={volume}"]
        else:
            codec_args = ["-c", "copy"]

        cmd = [
            "ffmpeg",
            "-y",
            "-headers",
            header_str,
            "-i",
            stream_url,
            *codec_args,
            str(output_path),
        ]
        logger.info(f"ffmpeg → {output_path.name}")

        _speed_re = re.compile(r"speed=\s*([\d.]+)x")
        _bitrate_re = re.compile(r"bitrate=\s*([\d.]+\s*\S+bits/s)")
        _last_cb = 0.0

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg not found in PATH") from e

        tail: list[str] = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                logger.debug(f"ffmpeg: {line}")
                tail.append(line)
                if len(tail) > 30:
                    tail.pop(0)
                if status_cb and time.time() - _last_cb > 1.0:
                    sm = _speed_re.search(line)
                    bm = _bitrate_re.search(line)
                    if sm or bm:
                        speed = f"{sm.group(1)}x" if sm else ""
                        bitrate = bm.group(1) if bm else ""
                        try:
                            status_cb(speed, bitrate)
                        except Exception:
                            pass
                        _last_cb = time.time()
            if stop_event and stop_event.is_set():
                proc.terminate()
                logger.info("ffmpeg terminated by stop event")
                return False

        proc.wait()
        success = proc.returncode == 0
        if not success:
            logger.error(f"ffmpeg exited with code {proc.returncode}")
            for line in tail[-10:]:
                logger.error(f"  {line}")
        return success

    def _get_duration(self, path: Path) -> float | None:
        """Return duration in seconds via ffprobe, or None on failure."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"ffprobe failed: {e}")
        return None

    def trim_file(self, path: Path, start_secs: float, end_secs: float) -> bool:
        """Trim start_secs from the beginning and end_secs from the end of path.

        Rewrites the file in-place via a temp file. Uses -c copy so no re-encode.
        Returns True on success.
        """
        if start_secs <= 0 and end_secs <= 0:
            return True

        duration = self._get_duration(path)
        if duration is None:
            logger.error(f"trim_file: could not get duration for {path}")
            return False

        trimmed = duration - start_secs - end_secs
        if trimmed <= 0:
            logger.error(
                f"trim_file: trim values ({start_secs}s + {end_secs}s) "
                f"exceed duration ({duration:.1f}s)"
            )
            return False

        tmp = path.with_suffix(".trimtmp.mkv")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_secs),
            "-i",
            str(path),
            "-t",
            str(trimmed),
            "-c",
            "copy",
            str(tmp),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"trim_file ffmpeg failed (rc={result.returncode})")
                if tmp.exists():
                    tmp.unlink()
                return False
            path.unlink()
            tmp.rename(path)
            logger.info(f"Trimmed {path.name}: -{start_secs}s start, -{end_secs}s end")
            return True
        except Exception as e:
            logger.error(f"trim_file failed: {e}")
            if tmp.exists():
                tmp.unlink()
            return False


def parse_trim_seconds(value: str) -> float:
    """Parse a trim value into seconds.

    Accepts: "1:30" (mm:ss), "1:30:00" (hh:mm:ss), "90" (plain seconds).
    Returns 0.0 for empty or invalid input.
    """
    if not value or not value.strip():
        return 0.0
    v = value.strip()
    try:
        parts = v.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(v)
    except (ValueError, IndexError):
        return 0.0
