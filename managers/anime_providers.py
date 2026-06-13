"""Anime providers: AllAnime (allanime.day) and AnimePahe (animepahe.ru).

Both use JSON/GraphQL APIs rather than HTML scraping.
AllAnime: GraphQL API + XOR-56 decryption → direct m3u8
AnimePahe: REST API → Kwik embed → P,A,C,K,E,R unpacker → m3u8
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0"

# ---------------------------------------------------------------------------
# Shared HTTP helper (simple, no cookie jar needed for these APIs)
# ---------------------------------------------------------------------------


def _fetch(url: str, headers: dict | None = None, post_data: bytes | None = None) -> str:
    h = {"User-Agent": UA, "Accept": "application/json, */*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=post_data, headers=h)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# AllAnime (allanime.day)
# ---------------------------------------------------------------------------

_ALLANIME_API = "https://api.allanime.day/api"
_ALLANIME_REFERER_SEARCH = "https://allmanga.to/"
_ALLANIME_REFERER_SOURCE = "https://youtu-chan.com/"

_ALLANIME_SEARCH_HASH = "a24c500a1b765c68ae1d8dd85174931f661c71369c89b92b88b75a725afc471c"
_ALLANIME_EPISODES_HASH = "043448386c7a686bc2aabfbb6b80f6074e795d350df48015023b079527b0848a"
_ALLANIME_SOURCES_HASH = "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"

# Provider priority (map sourceName → preference index)
_ALLANIME_PROVIDER_ORDER = ["Yt-mp4", "S-Mp4", "Uv-mp4", "Ak", "Default"]


def _allanime_request(variables: dict, sha256_hash: str, referer: str) -> dict:
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": sha256_hash}}
    params = urllib.parse.urlencode(
        {"variables": json.dumps(variables), "extensions": json.dumps(extensions)}
    )
    url = f"{_ALLANIME_API}?{params}"
    raw = _fetch(url, {"Referer": referer})
    return json.loads(raw)


def _allanime_xor_decrypt(encoded: str) -> str:
    """Hex-XOR-56 decrypt → octal → ASCII path."""
    result = []
    for i in range(0, len(encoded), 2):
        hex_val = encoded[i : i + 2]
        dec = int(hex_val, 16) ^ 56
        oct_val = oct(dec)[2:].zfill(3)
        result.append(chr(int(oct_val, 8)))
    return "".join(result)


def _allanime_show_id_from_url(url: str) -> str | None:
    """Extract show _id from allanime URL like /anime/{id}/{slug}."""
    m = re.search(r"/anime/([^/?#]+)", url)
    return m.group(1) if m else None


def _allanime_search(title: str, trans_type: str = "sub") -> list[dict]:
    variables = {
        "search": {"query": title},
        "limit": 26,
        "page": 1,
        "translationType": trans_type,
        "countryOrigin": "ALL",
    }
    data = _allanime_request(variables, _ALLANIME_SEARCH_HASH, _ALLANIME_REFERER_SEARCH)
    return data.get("data", {}).get("shows", {}).get("edges", [])


def _allanime_episode_list(show_id: str) -> dict:
    """Returns availableEpisodesDetail: {"sub": ["1","2",...], "dub": [...]}."""
    data = _allanime_request({"_id": show_id}, _ALLANIME_EPISODES_HASH, _ALLANIME_REFERER_SEARCH)
    return data.get("data", {}).get("show", {}).get("availableEpisodesDetail", {})


def _allanime_get_stream(show_id: str, episode: str, trans_type: str) -> tuple[str, str]:
    variables = {
        "showId": show_id,
        "translationType": trans_type,
        "episodeString": str(episode),
    }
    data = _allanime_request(variables, _ALLANIME_SOURCES_HASH, _ALLANIME_REFERER_SOURCE)
    sources = data.get("data", {}).get("episode", {}).get("sourceUrls", [])

    # Sort by preferred provider order
    def _prio(s):
        name = s.get("sourceName", "")
        try:
            return _ALLANIME_PROVIDER_ORDER.index(name)
        except ValueError:
            return len(_ALLANIME_PROVIDER_ORDER)

    for source in sorted(sources, key=_prio):
        src_url = source.get("sourceUrl", "")
        if not src_url or src_url.startswith("http"):
            continue
        try:
            decrypted = _allanime_xor_decrypt(src_url)
            decrypted = decrypted.replace("--", "").replace("clock", "clock.json")
            clock_url = f"https://allanime.day{decrypted}"
            clock_raw = _fetch(clock_url, {"Referer": _ALLANIME_REFERER_SOURCE})
            clock_data = json.loads(clock_raw)
            links = clock_data.get("links", [])
            if links:
                m3u8 = links[0].get("link") or links[0].get("hls")
                if m3u8:
                    logger.info(f"AllAnime: source={source.get('sourceName')} → {m3u8[:60]}…")
                    return m3u8, clock_url
        except Exception as e:
            logger.debug(f"AllAnime source {source.get('sourceName')} failed: {e}")

    raise ValueError(f"AllAnime: no usable stream found for ep {episode}")


def get_allanime_episodes(show_url: str, trans_type: str = "sub") -> list[str]:
    """Return synthetic episode URLs for all available episodes of an AllAnime show."""
    show_id = _allanime_show_id_from_url(show_url)
    if not show_id:
        raise ValueError(f"AllAnime: could not extract show ID from {show_url}")

    # Derive show name from URL slug (last path segment after the id)
    parts = show_url.rstrip("/").split("/")
    raw_name = parts[-1] if len(parts) > 1 and parts[-1] != show_id else show_id
    show_name = urllib.parse.quote(raw_name.replace("-", " ").replace("_", " ").title(), safe="")

    eps_detail = _allanime_episode_list(show_id)
    eps = eps_detail.get(trans_type) or eps_detail.get("sub") or []
    try:
        eps = sorted(eps, key=lambda x: float(x))
    except ValueError:
        eps = sorted(eps)
    logger.info(f"AllAnime: {len(eps)} episodes ({trans_type}) for {show_id}")
    # Synthetic: allanime://{show_name}/{show_id}/{trans_type}/{ep_num}
    return [f"allanime://{show_name}/{show_id}/{trans_type}/{ep}" for ep in eps]


def allanime_stream_from_synthetic(synthetic_url: str) -> tuple[str, str]:
    """Resolve allanime://{show_name}/{show_id}/{trans_type}/{ep} to (m3u8, referer)."""
    m = re.match(r"allanime://([^/]+)/([^/]+)/([^/]+)/(.+)", synthetic_url)
    if not m:
        raise ValueError(f"Invalid AllAnime synthetic URL: {synthetic_url}")
    _show_name, show_id, trans_type, episode = m.group(1), m.group(2), m.group(3), m.group(4)
    return _allanime_get_stream(show_id, episode, trans_type)


def allanime_show_name(synthetic_url: str) -> str:
    m = re.match(r"allanime://([^/]+)/", synthetic_url)
    return urllib.parse.unquote(m.group(1)) if m else "anime"


def allanime_episode_num(synthetic_url: str) -> int:
    m = re.match(r"allanime://[^/]+/[^/]+/[^/]+/(.+)", synthetic_url)
    try:
        return int(float(m.group(1))) if m else 0
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# AnimePahe (animepahe.ru)
# ---------------------------------------------------------------------------

_ANIMEPAHE_BASE = "https://animepahe.ru"
_ANIMEPAHE_REFERER = "https://animepahe.ru/"


def _animepahe_fetch(path: str) -> dict:
    url = f"{_ANIMEPAHE_BASE}{path}"
    raw = _fetch(url, {"Referer": _ANIMEPAHE_REFERER})
    return json.loads(raw)


def _animepahe_session_from_url(url: str) -> str | None:
    """Extract anime session UUID from URL like /anime/{session} or /anime/Name-{uuid}."""
    m = re.search(r"/anime/([^/?#]+)", url)
    if not m:
        return None
    slug = m.group(1)
    # UUID is last hyphen-segment if present
    uuid_m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", slug)
    if uuid_m:
        return uuid_m.group(1)
    return slug  # may be plain slug — API accepts it


def _animepahe_episodes(anime_session: str) -> list[dict]:
    """Fetch all episode entries via paginated API."""
    all_eps: list[dict] = []
    page = 1
    last_page = 1
    while page <= last_page:
        data = _animepahe_fetch(f"/api?m=release&id={anime_session}&sort=episode_asc&page={page}")
        last_page = data.get("last_page", 1)
        all_eps.extend(data.get("data", []))
        page += 1
        if page <= last_page:
            time.sleep(0.5)
    return all_eps


def _animepahe_kwik_from_episode(anime_session: str, ep_session: str) -> str:
    """Get Kwik URL for an episode (HD quality preferred)."""
    data = _animepahe_fetch(f"/api?m=links&id={anime_session}&session={ep_session}&p=kwik")
    # Response: {"360": {"kwik": "..."}, "720": {"kwik": "..."}, ...}
    for quality in ("1080", "720", "480", "360"):
        entry = data.get(quality, {})
        kwik = entry.get("kwik") or entry.get("hd")
        if kwik:
            return kwik
    # Fallback: take any first value
    for entry in data.values():
        if isinstance(entry, dict):
            kwik = entry.get("kwik") or entry.get("hd")
            if kwik:
                return kwik
    raise ValueError("AnimePahe: no Kwik URL found in episode links")


def get_animepahe_episodes(show_url: str) -> list[str]:
    """Return synthetic episode URLs for all available episodes of an AnimePahe show."""
    session = _animepahe_session_from_url(show_url)
    if not session:
        raise ValueError(f"AnimePahe: could not extract session from {show_url}")

    # Fetch first page to get show title
    first_page = _animepahe_fetch(f"/api?m=release&id={session}&sort=episode_asc&page=1")
    # AnimePahe release API includes anime title in some responses; fall back to slug
    raw_name = first_page.get("title") or show_url.rstrip("/").split("/")[-1]
    # Strip trailing UUID from slug like "One-Piece-6e5edd8e-..."
    raw_name = re.sub(
        r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", "", raw_name
    )
    show_name = urllib.parse.quote(raw_name.replace("-", " ").replace("_", " ").title(), safe="")

    eps: list[dict] = list(first_page.get("data", []))
    last_page = first_page.get("last_page", 1)
    page = 2
    while page <= last_page:
        data = _animepahe_fetch(f"/api?m=release&id={session}&sort=episode_asc&page={page}")
        eps.extend(data.get("data", []))
        page += 1
        if page <= last_page:
            time.sleep(0.5)

    logger.info(f"AnimePahe: {len(eps)} episodes for session {session}")
    # Synthetic: animepahe://{show_name}/{anime_session}/{ep_session}/{ep_num}
    return [
        f"animepahe://{show_name}/{session}/{ep['session']}/{ep.get('episode', i + 1)}"
        for i, ep in enumerate(eps)
    ]


def animepahe_stream_from_synthetic(synthetic_url: str) -> tuple[str, str]:
    """Resolve animepahe://{show_name}/{anime_session}/{ep_session}/{ep_num} to (m3u8, referer)."""
    from managers.stream_manager import _extract_kwik

    m = re.match(r"animepahe://([^/]+)/([^/]+)/([^/]+)/(.+)", synthetic_url)
    if not m:
        raise ValueError(f"Invalid AnimePahe synthetic URL: {synthetic_url}")
    _show_name, anime_session, ep_session = m.group(1), m.group(2), m.group(3)
    kwik_url = _animepahe_kwik_from_episode(anime_session, ep_session)
    return _extract_kwik(kwik_url, _ANIMEPAHE_REFERER)


def animepahe_show_name(synthetic_url: str) -> str:
    m = re.match(r"animepahe://([^/]+)/", synthetic_url)
    return urllib.parse.unquote(m.group(1)) if m else "anime"


def animepahe_episode_num(synthetic_url: str) -> int:
    m = re.match(r"animepahe://[^/]+/[^/]+/[^/]+/(.+)", synthetic_url)
    try:
        return int(float(m.group(1))) if m else 0
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Unified entry point called from stream_manager.get_season_episodes
# ---------------------------------------------------------------------------


def get_anime_episodes(show_url: str) -> list[str]:
    if "allanime." in show_url:
        return get_allanime_episodes(show_url)
    if "animepahe." in show_url:
        return get_animepahe_episodes(show_url)
    raise ValueError(f"anime_providers: unrecognised URL {show_url}")


def get_anime_stream(synthetic_url: str) -> tuple[str, str]:
    if synthetic_url.startswith("allanime://"):
        return allanime_stream_from_synthetic(synthetic_url)
    if synthetic_url.startswith("animepahe://"):
        return animepahe_stream_from_synthetic(synthetic_url)
    raise ValueError(f"anime_providers: unrecognised synthetic URL {synthetic_url}")
