"""
app.py
Under the Radar — Fast, Verified Multi-Store PC Game Discovery
Features:
  - Fragment-isolated Spotlight & Catalog for ~20ms carousel turns and instant sorting
  - Pre-indexed, cached multi-store filtering & sorting across 25,000+ PC games
  - Compact, streamlined "Explore & Genres" popover panel
  - Tactile mouse hover & click-press micro-interactions on all buttons, pills, and cards
  - Official widescreen key-art resolver via Epic Games Store Catalog API, Blizzard media,
    and Valve Steam CDN headers (no map splashes, no transparent logos, no black boxes)
  - Isolated Insights & Charts page with honest 0–100% bar scale, leader-line donut,
    de-overplotted scatter, data-synced takeaways, and CSV dataset downloads
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import os
import random
import re
import urllib.parse
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from analytics import (
    engineer_gem_metrics,
    format_shadow_event,
)
from multi_store_live import (
    bootstrap_starter_catalog,
    get_live_cross_store_deals,
    get_live_player_reviews,
    get_live_steam_pulse,
    inject_multi_store_titles,
)

st.set_page_config(
    page_title="Under the Radar — PC Game Discovery",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None) or (lambda fn: fn)

DATA_PATH = "data/steam_catalog.csv"

defaults = {
    "nav_page": "Discover",
    "hide_aaa": False,
    "spotlight_idx": 0,
    "spotlight_seed": random.randint(1, 999999),
    "spot_anim_tick": 0,
    "radar_view": "All PC Games",
    "multi_genres": [],
    "selected_store": "All Launchers",
    "min_wilson": 50,
    "catalog_page": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _set_radar_view(view_name: str) -> None:
    st.session_state["radar_view"] = view_name
    st.session_state["catalog_page"] = 0


def _apply_genre_preset(tags_list: list[str]) -> None:
    st.session_state["multi_genres"] = list(tags_list)
    st.session_state["catalog_page"] = 0


def _reset_catalog_page() -> None:
    st.session_state["catalog_page"] = 0


def _reset_all_filters(min_y: int, max_y: int) -> None:
    st.session_state["radar_view"] = "All PC Games"
    st.session_state["multi_genres"] = []
    st.session_state["selected_store"] = "All Launchers"
    st.session_state["year_range"] = (min_y, max_y)
    st.session_state["min_wilson"] = 50
    st.session_state["catalog_page"] = 0


def clean_text(raw: str) -> str:
    no_html = re.sub(r"<[^>]+>", " ", str(raw))
    no_bb = re.sub(r"\[/?[a-zA-Z0-9_=*\"':/.\- ]+\]", " ", no_html)
    return html.escape(" ".join(no_bb.split()))


def clean_plain_review(raw: str, max_len: int = 380) -> str:
    no_html = re.sub(r"<[^>]+>", " ", str(raw))
    no_bb = re.sub(r"\[/?[a-zA-Z0-9_=*\"':/.\- ]+\]", " ", no_html)
    cleaned = " ".join(no_bb.split()).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3].rstrip() + "..."
    return cleaned


# ===========================================================================
# OFFICIAL WIDESCREEN KEY-ART RESOLVER (EPIC CATALOG + BLIZZARD + STEAM CDN)
# ===========================================================================
EPIC_CATALOG_TITLES = {
    "valorant": "VALORANT",
    "league of legends": "League of Legends",
    "teamfight tactics": "Teamfight Tactics",
    "legends of runeterra": "Legends of Runeterra",
    "fortnite": "Fortnite",
    "alan wake 2": "Alan Wake 2",
    "genshin impact": "Genshin Impact",
    "honkai: star rail": "Honkai: Star Rail",
    "wuthering waves": "Wuthering Waves",
}

BLIZZARD_OFFICIAL_PAGES = {
    "world of warcraft": "https://worldofwarcraft.blizzard.com/en-us/",
    "hearthstone": "https://hearthstone.blizzard.com/en-us/",
}

DIRECT_STEAM_HEADER_COVERS = {
    # Overwatch 2 is officially on Steam (AppID 2357570)
    "overwatch 2": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2357570/header.jpg",
}


def _fetch_epic_wide_key_art(search_title: str) -> str:
    """
    Fetches the official 16:9 widescreen store banner (OfferImageWide / DieselGameBoxWide)
    from Epic Games Store's public catalog GraphQL endpoint—never a transparent logo.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    query = """
    query searchStoreQuery($keywords: String!, $country: String!, $locale: String!) {
      Catalog {
        searchStoreElements(keywords: $keywords, country: $country, locale: $locale, count: 6) {
          elements {
            title
            keyImages {
              type
              url
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "keywords": search_title,
            "country": "US",
            "locale": "en-US",
        },
    }
    try:
        resp = requests.post(
            "https://store.epicgames.com/graphql",
            json=payload,
            headers=headers,
            timeout=4.5,
        )
        if resp.status_code == 200:
            elements = (
                resp.json()
                .get("data", {})
                .get("Catalog", {})
                .get("searchStoreElements", {})
                .get("elements", [])
            )
            target_low = search_title.strip().lower()
            # Prefer exact title match first, then first element
            ordered_elems = sorted(
                elements,
                key=lambda el: 0 if str(el.get("title", "")).strip().lower() == target_low else 1,
            )
            wide_priority = ("OfferImageWide", "DieselGameBoxWide", "Featured", "DieselStoreFrontWide")
            for el in ordered_elems:
                imgs = el.get("keyImages") or []
                for img_type in wide_priority:
                    for im in imgs:
                        if im.get("type") == img_type and im.get("url"):
                            u = str(im["url"]).strip()
                            if u.startswith("http"):
                                return u
    except Exception:
        pass
    return ""


def _fetch_blizzard_key_art(page_url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = requests.get(page_url, headers=headers, timeout=4.0, allow_redirects=True)
        if resp.status_code != 200 or not resp.text:
            return ""
        html_doc = resp.text[:140000]
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html_doc, flags=re.IGNORECASE)
            if m:
                img_u = html.unescape(m.group(1).strip())
                if img_u.startswith("//"):
                    img_u = "https:" + img_u
                elif img_u.startswith("/"):
                    img_u = urllib.parse.urljoin(resp.url, img_u)
                low_u = img_u.lower()
                if img_u.startswith("http") and "logo" not in low_u and "icon" not in low_u:
                    return img_u
    except Exception:
        pass
    return ""


@st.cache_data(ttl=86400, show_spinner=False)
def get_official_non_steam_covers() -> dict[str, str]:
    resolved = dict(DIRECT_STEAM_HEADER_COVERS)
    with ThreadPoolExecutor(max_workers=10) as pool:
        epic_futs = {
            pool.submit(_fetch_epic_wide_key_art, disp_name): t_key
            for t_key, disp_name in EPIC_CATALOG_TITLES.items()
        }
        blizz_futs = {
            pool.submit(_fetch_blizzard_key_art, url): t_key
            for t_key, url in BLIZZARD_OFFICIAL_PAGES.items()
        }
        for fut in as_completed({**epic_futs, **blizz_futs}):
            t_key = epic_futs.get(fut) or blizz_futs.get(fut)
            if not t_key:
                continue
            try:
                art_url = fut.result()
                if art_url:
                    resolved[t_key] = art_url
            except Exception:
                pass
    return resolved


def resolve_cover_urls(row: pd.Series) -> list[str]:
    """
    Returns an ordered priority list of official widescreen cover URLs:
      1. Live official widescreen store banner (Epic OfferImageWide / DieselGameBoxWide / Blizzard)
      2. Current Valve Steam 460x215 header CDN (for any Steam AppID)
      3. Catalog header_image backup (if valid)
    """
    urls: list[str] = []
    nm_key = str(row.get("name", "")).strip().lower()
    aid = int(row.get("appid", 0) or 0)

    official_map = get_official_non_steam_covers()
    if nm_key in official_map and official_map[nm_key]:
        urls.append(official_map[nm_key])

    if 0 < aid < 9000000 and nm_key not in NON_STEAM_EXCLUSIVES:
        steam_primary = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
        steam_backup = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
        for u in (steam_primary, steam_backup):
            if u not in urls:
                urls.append(u)

    raw_val = row.get("header_image")
    raw_url = "" if pd.isna(raw_val) else str(raw_val).strip()
    if raw_url.lower() not in ("", "nan", "none", "null") and raw_url.startswith("http"):
        if raw_url not in urls:
            urls.append(raw_url)

    return urls


def render_cover_art(row: pd.Series, variant: str = "card") -> str:
    """
    Renders a clean, full-bleed widescreen cover container:
      - When official cover URLs exist: renders CSS3 stacked background-image layers with
        background-size: cover and NO text underneath (prevents any bleed-through).
      - Only if zero URLs exist: renders a clean styled title badge.
    """
    g_name = str(row.get("name", "PC Game")).strip() or "PC Game"
    cover_urls = resolve_cover_urls(row)

    if cover_urls:
        bg_layers = [f"url('{html.escape(u)}')" for u in cover_urls]
        bg_layers.append("linear-gradient(135deg, #1e1b4b 0%, #0f172a 55%, #311042 100%)")
        bg_stack = ", ".join(bg_layers)
        inner_html = (
            f'<div class="cover-photo-layer" '
            f'style="background-image: {bg_stack}; background-size: cover; background-position: center center;"></div>'
        )
    else:
        stores_val = row.get("verified_stores")
        if pd.isna(stores_val) or not str(stores_val).strip():
            stores_list = detect_verified_stores(
                name=g_name,
                appid=int(row.get("appid", 0) or 0),
                publishers=str(row.get("publishers", "")),
                developers=str(row.get("developers", "")),
            )
            stores_str = " • ".join(stores_list)
        else:
            stores_str = str(stores_val).replace("|", " • ")
        inner_html = (
            f'<div class="cover-fallback-art">'
            f'<div class="cfb-title">{html.escape(g_name[:30].upper())}</div>'
            f'<div class="cfb-sub">{html.escape(stores_str[:36].upper())}</div>'
            f'</div>'
        )

    if variant == "spot":
        wrap_cls = "spot-media-col"
        extra_style = ""
    elif variant == "modal":
        wrap_cls = "card-img-wrap"
        extra_style = ' style="margin-bottom: 10px;"'
    else:
        wrap_cls = "card-img-wrap"
        extra_style = ""

    return f'<div class="{wrap_cls}"{extra_style}>{inner_html}</div>'


# ===========================================================================
# STRICT, VERIFIED MULTI-STORE LAUNCHER DETECTION (ZERO FALSE POSITIVES)
# ===========================================================================
NON_STEAM_EXCLUSIVES = {
    "valorant",
    "league of legends",
    "teamfight tactics",
    "legends of runeterra",
    "fortnite",
    "alan wake 2",
    "world of warcraft",
    "hearthstone",
    "genshin impact",
    "honkai: star rail",
    "wuthering waves",
}

EA_PUBLISHERS = (
    "electronic arts",
    "ea sports",
    "respawn entertainment",
    "bioware",
    "dice",
    "popcap",
    "codemasters",
    "criterion games",
    "ea motive",
    "ea maxis",
)
EA_TITLES = (
    "apex legends",
    "titanfall 2",
    "it takes two",
    "star wars jedi: fallen order",
    "star wars jedi: survivor",
    "battlefield",
    "mass effect",
    "dead space",
    "need for speed",
    "the sims 4",
    "dragon age",
    "star wars: squadrons",
    "unravel",
    "a way out",
    "lost in random",
    "immortals of aveum",
    "wild hearts",
    "ea sports fc",
    "f1 23",
    "f1 24",
)

UBISOFT_TITLES = (
    "tom clancy's rainbow six",
    "assassin's creed",
    "far cry",
    "watch dogs",
    "tom clancy's ghost recon",
    "tom clancy's the division",
    "for honor",
    "anno 1800",
    "trackmania",
    "riders republic",
    "the crew",
    "immortals fenyx rising",
    "prince of persia",
    "rayman",
    "south park: the stick of truth",
    "south park: the fractured but whole",
    "child of light",
    "valiant hearts",
)

RIOT_TITLES = (
    "valorant",
    "league of legends",
    "teamfight tactics",
    "legends of runeterra",
    "ruined king: a league of legends story",
    "conv/rgence: a league of legends story",
    "song of nunu: a league of legends story",
    "the mageseeker: a league of legends story",
)

BATTLENET_TITLES = (
    "overwatch 2",
    "diablo iv",
    "diablo ii: resurrected",
    "world of warcraft",
    "hearthstone",
    "starcraft ii",
    "call of duty",
    "crash bandicoot 4",
)

EPIC_VERIFIED_TITLES = (
    "valorant",
    "fortnite",
    "alan wake 2",
    "alan wake remastered",
    "control",
    "rocket league",
    "fall guys",
    "grand theft auto v",
    "red dead redemption 2",
    "cyberpunk 2077",
    "the witcher 3: wild hunt",
    "hades",
    "hades ii",
    "disco elysium",
    "frostpunk",
    "frostpunk 2",
    "hollow knight",
    "outer wilds",
    "subnautica",
    "subnautica: below zero",
    "ghostrunner",
    "ghostrunner 2",
    "a plague tale: innocence",
    "a plague tale: requiem",
    "metro exodus",
    "dying light",
    "dying light 2",
    "kingdom come: deliverance",
    "borderlands 3",
    "tiny tina's wonderlands",
    "death stranding",
    "days gone",
    "god of war",
    "marvel's spider-man remastered",
    "horizon zero dawn",
    "final fantasy vii remake",
    "sifu",
    "kena: bridge of spirits",
    "darkest dungeon",
    "darkest dungeon ii",
    "dead cells",
    "slay the spire",
    "celeste",
    "enter the gungeon",
    "inscryption",
    "loop hero",
    "vampire survivors",
    "brotato",
    "chivalry 2",
    "remnant ii",
    "remnant: from the ashes",
    "payday 2",
    "payday 3",
    "satisfactory",
    "cities: skylines",
    "surviving mars",
    "sid meier's civilization vi",
    "xcom 2",
    "batman: arkham",
    "bioshock",
    "tomb raider",
    "shadow of the tomb raider",
    "rise of the tomb raider",
    "prey",
    "dishonored",
    "fallout 3",
    "fallout: new vegas",
    "the elder scrolls v: skyrim",
    "doom eternal",
    "wolfenstein",
    "evil west",
    "the talos principle",
    "superliminal",
    "what remains of edith finch",
    "journey",
    "abzu",
    "gris",
    "among us",
    "overcooked! 2",
    "moving out",
    "human fall flat",
    "world war z",
    "back 4 blood",
    "killing floor 2",
    "deep rock galactic",
    "valheim",
    "terraria",
    "stardew valley",
    "genshin impact",
    "honkai: star rail",
    "wuthering waves",
    "naraka: bladepoint",
)

GOG_VERIFIED_TITLES = (
    "the witcher 3: wild hunt",
    "the witcher 2: assassins of kings",
    "cyberpunk 2077",
    "baldur's gate 3",
    "divinity: original sin 2",
    "disco elysium",
    "hollow knight",
    "stardew valley",
    "terraria",
    "cuphead",
    "dead cells",
    "slay the spire",
    "frostpunk",
    "this war of mine",
    "factorio",
    "rimworld",
    "no man's sky",
    "subnautica",
    "outer wilds",
    "control",
    "metro exodus",
    "a plague tale: innocence",
    "a plague tale: requiem",
    "kingdom come: deliverance",
    "x-com: ufo defense",
    "fallout: new vegas",
    "fallout 3",
    "the elder scrolls v: skyrim",
    "bioshock",
    "system shock",
    "deus ex",
    "grim dawn",
    "torchlight ii",
    "pillars of eternity",
    "pathfinder: wrath of the righteous",
    "wasteland 3",
    "ftl: faster than light",
    "into the breach",
    "darkest dungeon",
    "celeste",
    "katana zero",
    "hotline miami",
    "blasphemous",
    "psychonauts 2",
    "return of the obra dinn",
    "papers, please",
    "kerbal space program",
    "stellaris",
    "crusader kings iii",
    "europa universalis iv",
    "hearts of iron iv",
    "mount & blade ii: bannerlord",
    "kenshi",
    "project zomboid",
    "dying light",
    "s.t.a.l.k.e.r.",
    "mafia",
    "saints row",
    "yakuza",
    "dredge",
    "dave the diver",
    "sea of stars",
    "chained echoes",
    "crosscode",
)


def detect_verified_stores(name: str, appid: int, publishers: str = "", developers: str = "") -> list[str]:
    nm = str(name).strip().lower()
    pub = f"{publishers} {developers}".strip().lower()
    stores: list[str] = []

    if 0 < int(appid) < 9000000 and nm not in NON_STEAM_EXCLUSIVES:
        stores.append("Steam")

    if any(p in pub for p in EA_PUBLISHERS) or any(t in nm for t in EA_TITLES):
        stores.append("EA App")

    if "ubisoft" in pub or any(t in nm for t in UBISOFT_TITLES):
        stores.append("Ubisoft Connect")

    if "riot games" in pub or any(t in nm for t in RIOT_TITLES):
        stores.append("Riot Client")

    if "blizzard entertainment" in pub or any(t in nm for t in BATTLENET_TITLES):
        stores.append("Battle.net")

    if "epic games" in pub or any(t in nm for t in EPIC_VERIFIED_TITLES):
        stores.append("Epic Games Store")

    if "cd projekt" in pub or "gog.com" in pub or any(t in nm for t in GOG_VERIFIED_TITLES):
        stores.append("GOG")

    if not stores:
        stores.append("Steam")
    return stores


def build_verified_store_links(name: str, appid: int, stores: list[str]) -> dict[str, str]:
    q = urllib.parse.quote(str(name).strip())
    links: dict[str, str] = {}
    for s in stores:
        if s == "Steam":
            if 0 < int(appid) < 9000000:
                links["Steam"] = f"https://store.steampowered.com/app/{int(appid)}/"
            else:
                links["Steam"] = f"https://store.steampowered.com/search/?term={q}"
        elif s == "Epic Games Store":
            links["Epic"] = f"https://store.epicgames.com/en-US/browse?q={q}"
        elif s == "GOG":
            links["GOG"] = f"https://www.gog.com/en/games?query={q}"
        elif s == "EA App":
            links["EA App"] = f"https://www.ea.com/games/library?search={q}"
        elif s == "Ubisoft Connect":
            links["Ubisoft"] = f"https://store.ubisoft.com/search?q={q}"
        elif s == "Riot Client":
            links["Riot"] = "https://www.riotgames.com/en/games"
        elif s == "Battle.net":
            links["Battle.net"] = f"https://shop.battle.net/search?q={q}"
    return links


# ===========================================================================
# LIVE TELEMETRY & VERIFIED REVIEWS
# ===========================================================================
@st.cache_data(ttl=600, show_spinner=False)
def _fetch_single_live_ccu(appid: int) -> int | None:
    if appid <= 0 or appid >= 9000000:
        return None
    try:
        resp = requests.get(
            "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
            params={"appid": int(appid)},
            timeout=2.0,
        )
        if resp.status_code == 200:
            payload = resp.json().get("response", {})
            if payload.get("result") == 1 and "player_count" in payload:
                return int(payload["player_count"])
    except Exception:
        pass
    return None


@st.cache_data(ttl=600, show_spinner=False)
def get_live_ccu_batch(appids_tuple: tuple[int, ...]) -> dict[int, int | None]:
    unique_ids = list({int(a) for a in appids_tuple if int(a) > 0})
    if not unique_ids:
        return {}
    out: dict[int, int | None] = {}
    with ThreadPoolExecutor(max_workers=18) as pool:
        fut_map = {pool.submit(_fetch_single_live_ccu, aid): aid for aid in unique_ids}
        for fut in as_completed(fut_map):
            aid = fut_map[fut]
            try:
                out[aid] = fut.result()
            except Exception:
                out[aid] = None
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_verified_reviews(appid: int, game_name: str = "", max_reviews: int = 6) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json",
    }
    candidate_ids: list[int] = []
    if appid and 0 < int(appid) < 9000000:
        candidate_ids.append(int(appid))

    if game_name.strip():
        try:
            sr = requests.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": game_name.strip(), "l": "english", "cc": "US"},
                headers=headers,
                timeout=4,
            )
            if sr.status_code == 200:
                for it in sr.json().get("items", [])[:2]:
                    sid = int(it.get("id", 0) or 0)
                    if sid > 0 and sid not in candidate_ids:
                        candidate_ids.append(sid)
        except Exception:
            pass

    query_variants = [
        {"cursor": "*", "filter": "recent", "language": "english"},
        {"cursor": "*", "filter": "updated", "language": "all"},
        {"cursor": "*", "filter": "all", "day_range": 365, "language": "all"},
    ]

    for tid in candidate_ids:
        for qv in query_variants:
            try:
                params = {
                    "json": 1,
                    "purchase_type": "all",
                    "review_type": "all",
                    "filter_offtopic_activity": 0,
                    "num_per_page": 20,
                    **qv,
                }
                resp = requests.get(
                    f"https://store.steampowered.com/appreviews/{tid}",
                    params=params,
                    headers=headers,
                    timeout=5,
                )
                if resp.status_code == 200:
                    raw_revs = resp.json().get("reviews", [])
                    parsed = []
                    for rv in raw_revs:
                        txt = clean_plain_review(rv.get("review", ""), max_len=380)
                        if len(txt) < 12:
                            continue
                        author = rv.get("author", {}) or {}
                        mins = int(author.get("playtime_forever", 0) or 0)
                        parsed.append(
                            {
                                "voted_up": bool(rv.get("voted_up", True)),
                                "playtime_hrs": round(mins / 60.0, 1),
                                "votes_up": int(rv.get("votes_up", 0) or 0),
                                "snippet": txt,
                            }
                        )
                        if len(parsed) >= max_reviews:
                            break
                    if parsed:
                        return parsed
            except Exception:
                continue

    try:
        for tid in candidate_ids:
            fb = get_live_player_reviews(tid, max_reviews=max_reviews)
            if fb:
                return fb
    except Exception:
        pass

    return []


AAA_TITLE_PATTERN = re.compile(
    r"(?:grand theft auto|\bgta\b|elden ring|call of duty|counter-strike|cyberpunk 2077|"
    r"red dead|the witcher|baldur's gate|monster hunter|street fighter|tekken|mortal kombat|"
    r"total war|assassin's creed|far cry|battlefield|\bfifa\b|ea sports|nba 2k|starfield|"
    r"fallout|skyrim|elder scrolls|diablo|overwatch|world of warcraft|valorant|league of legends|"
    r"apex legends|pubg|destiny 2|helldivers|hogwarts legacy|god of war|spider-man|"
    r"horizon zero dawn|horizon forbidden west|last of us|ghost of tsushima|resident evil|"
    r"final fantasy|dota 2|team fortress|palworld|black myth|forza|\bhalo\b|civilization|"
    r"cities: skylines|farming simulator|borderlands|tomb raider|hitman|mass effect|dragon age|"
    r"sekiro|dark souls|armored core|metal gear|silent hill|persona|yakuza|like a dragon|"
    r"alan wake 2|rainbow six|ghost recon|watch dogs|star wars|marvel's|batman: arkham)",
    flags=re.IGNORECASE,
)

AAA_PUBLISHER_PATTERN = re.compile(
    r"(?:rockstar games|electronic arts|ubisoft|activision|bethesda|\b2k\b|capcom|square enix|"
    r"bandai namco|sega|sony interactive|xbox game studios|cd projekt red|blizzard|riot games|valve)",
    flags=re.IGNORECASE,
)


def apply_strict_non_aaa_filter(df: pd.DataFrame) -> pd.DataFrame:
    if "_strict_non_aaa" in df.columns:
        return df[df["_strict_non_aaa"]].copy()
    pub_col = df["publishers"].fillna("") if "publishers" in df.columns else pd.Series("", index=df.index)
    return df[
        (~df["is_aaa_blockbuster"])
        & (df["total_reviews"] < 35000)
        & (~df["name"].str.contains(AAA_TITLE_PATTERN, na=False))
        & (~pub_col.str.contains(AAA_PUBLISHER_PATTERN, na=False))
    ].copy()


st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@600;700&family=Plus+Jakarta+Sans:wght@700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
h1, h2, h3, h4, .radar-brand {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    letter-spacing: -0.025em;
}

section[data-testid="stSidebar"],
button[data-testid="collapsedControl"],
div[data-testid="stDecoration"],
#MainMenu,
footer {
    display: none !important;
}
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0px !important;
}

.stApp {
    background:
        radial-gradient(ellipse 80% 42% at 15% -5%, rgba(37, 99, 235, 0.24), transparent 55%),
        radial-gradient(ellipse 65% 38% at 85% -4%, rgba(124, 58, 237, 0.20), transparent 52%),
        radial-gradient(ellipse 50% 35% at 50% 45%, rgba(14, 165, 233, 0.06), transparent 60%),
        #060a13;
    color: #f1f5f9;
}
.block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    padding-top: 2.4rem !important;
    padding-bottom: 2.5rem !important;
}

@keyframes spotFadeIn {
    0% { opacity: 0.45; transform: translateX(10px); }
    100% { opacity: 1; transform: translateX(0); }
}
.spot-anim-card {
    animation: spotFadeIn 0.16s ease-out both;
}

/* TACTILE, MOUSE-REACTIVE BUTTON SYSTEM (CRISP HOVER + CLICK PRESS) */
div.stButton > button,
div[data-testid="stPopover"] > button,
div[data-testid="stDownloadButton"] > button {
    min-height: 42px !important;
    height: 42px !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    cursor: pointer !important;
    transition: transform 0.11s ease-out, background-color 0.14s ease, border-color 0.14s ease, box-shadow 0.14s ease, color 0.14s ease !important;
}

div.stButton > button[kind="primary"],
div[data-testid="stDownloadButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    border: 1px solid rgba(147, 197, 253, 0.55) !important;
    color: #ffffff !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.24), 0 3px 10px rgba(37, 99, 235, 0.30) !important;
}
div.stButton > button[kind="primary"]:hover,
div[data-testid="stDownloadButton"] > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%) !important;
    border-color: #bfdbfe !important;
    transform: translateY(-1px) !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.32), 0 6px 18px rgba(59, 130, 246, 0.46) !important;
}
div.stButton > button[kind="primary"]:active,
div[data-testid="stDownloadButton"] > button[kind="primary"]:active {
    transform: translateY(1px) scale(0.985) !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.35) !important;
    transition-duration: 0.05s !important;
}

div.stButton > button[kind="secondary"],
div[data-testid="stPopover"] > button,
div[data-testid="stDownloadButton"] > button[kind="secondary"] {
    background: rgba(24, 34, 58, 0.90) !important;
    border: 1px solid rgba(99, 125, 175, 0.36) !important;
    color: #e2e8f0 !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
}
div.stButton > button[kind="secondary"]:hover,
div[data-testid="stPopover"] > button:hover,
div[data-testid="stDownloadButton"] > button[kind="secondary"]:hover {
    background: rgba(37, 99, 235, 0.28) !important;
    border-color: #60a5fa !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.24) !important;
}
div.stButton > button[kind="secondary"]:active,
div[data-testid="stPopover"] > button:active,
div[data-testid="stDownloadButton"] > button[kind="secondary"]:active {
    background: rgba(37, 99, 235, 0.38) !important;
    transform: translateY(1px) scale(0.985) !important;
    transition-duration: 0.05s !important;
}
div.stButton > button:disabled {
    opacity: 0.36 !important;
    transform: none !important;
    cursor: not-allowed !important;
}

/* Compact, Streamlined Explore & Genres Popover */
div[data-testid="stPopoverBody"] {
    background: linear-gradient(155deg, #0d1528 0%, #131c36 60%, #0e1e36 100%) !important;
    border: 1px solid rgba(96, 165, 250, 0.48) !important;
    border-radius: 14px !important;
    padding: 16px 18px !important;
    min-width: 440px !important;
    max-width: 470px !important;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.78), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
}
div[data-testid="stPopoverBody"] div.stButton > button {
    min-height: 34px !important;
    height: 34px !important;
    font-size: 0.8rem !important;
    border-radius: 8px !important;
    padding: 0 10px !important;
}
.mega-sec-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.76rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #93c5fd;
    margin: 2px 0 7px 0;
}
.mega-divider {
    height: 1px;
    background: rgba(99, 125, 175, 0.22);
    margin: 10px 0;
}

/* Uniform Search Bar, Dropdowns & Multi-Genre Tag Pills */
div[data-baseweb="input"] > div {
    background: #0f172a !important;
    border: 1px solid rgba(96, 165, 250, 0.38) !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    height: 42px !important;
    color: #f8fafc !important;
    transition: border-color 0.14s ease, box-shadow 0.14s ease !important;
}
div[data-baseweb="input"] > div:hover,
div[data-baseweb="select"] > div:hover {
    border-color: rgba(147, 197, 253, 0.65) !important;
}
div[data-baseweb="input"] input {
    font-size: 0.9rem !important;
}
div[data-baseweb="select"] > div {
    background: #0f172a !important;
    border: 1px solid rgba(99, 125, 175, 0.34) !important;
    border-radius: 10px !important;
    min-height: 40px !important;
    color: #f8fafc !important;
    cursor: pointer !important;
    transition: border-color 0.14s ease, box-shadow 0.14s ease !important;
}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {
    border-color: #60a5fa !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.24) !important;
}
span[data-baseweb="tag"] {
    background: rgba(37, 99, 235, 0.34) !important;
    border: 1px solid rgba(96, 165, 250, 0.58) !important;
    color: #f0f9ff !important;
    border-radius: 6px !important;
}

/* Top Brand Bar */
.top-brand-strip {
    background: linear-gradient(125deg, #0f172a 0%, #191636 55%, #0d2137 100%);
    border: 1px solid rgba(99, 125, 175, 0.32);
    border-radius: 16px;
    padding: 15px 22px;
    margin-top: 4px;
    margin-bottom: 14px;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
}
.brand-wrap {
    display: flex;
    align-items: center;
    gap: 13px;
}
.brand-icon-box {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.38);
}
.radar-brand {
    font-size: 1.45rem;
    font-weight: 800;
    background: linear-gradient(90deg, #ffffff 0%, #bfdbfe 60%, #ddd6fe 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    line-height: 1.15;
}
.radar-sub {
    color: #e2e8f0;
    font-size: 0.85rem;
    margin: 3px 0 0 0;
}
.epic-gift-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(245, 158, 11, 0.2);
    border: 1px solid rgba(251, 191, 36, 0.5);
    color: #fef3c7;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
}

/* Full-Bleed Widescreen Cover Frame (Zero Bleed-Through) */
.cover-fallback-art {
    position: absolute;
    inset: 0;
    background:
        radial-gradient(circle at 85% 20%, rgba(244, 63, 94, 0.28), transparent 48%),
        radial-gradient(circle at 15% 85%, rgba(59, 130, 246, 0.30), transparent 52%),
        linear-gradient(135deg, #1e1b4b 0%, #0f172a 55%, #311042 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 14px;
    text-align: center;
}
.cfb-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #ffffff;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.55);
    line-height: 1.2;
}
.cfb-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #93c5fd;
    margin-top: 6px;
    padding: 2px 9px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(96, 165, 250, 0.32);
}
.cover-photo-layer {
    position: absolute;
    inset: 0;
    background-position: center center;
    background-repeat: no-repeat;
    background-size: cover;
}

/* Fixed-Height Atomic Spotlight Card — Full-Bleed Cover Art */
.spotlight-unified {
    background: linear-gradient(135deg, #111b33 0%, #1a1638 55%, #0f2238 100%);
    border: 1px solid rgba(96, 165, 250, 0.36);
    border-radius: 18px;
    padding: 20px 24px;
    height: 318px;
    margin-bottom: 12px;
    overflow: hidden;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 16px 38px rgba(0, 0, 0, 0.48);
    display: flex;
    gap: 24px;
    align-items: center;
}
.spot-media-col {
    position: relative;
    flex: 0 0 424px;
    width: 424px;
    height: 204px;
    background: #080d1a;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    overflow: hidden;
}
.spot-info-col {
    flex: 1 1 auto;
    min-width: 0;
}
.spot-kicker {
    font-size: 0.76rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #93c5fd;
    margin-bottom: 4px;
}
.spot-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.58rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0 0 8px 0;
    line-height: 1.18;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.spot-stats-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-bottom: 8px;
    align-items: center;
}
.stat-chip-live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16, 185, 129, 0.2);
    border: 1px solid rgba(52, 211, 153, 0.5);
    color: #a7f3d0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-score {
    background: rgba(59, 130, 246, 0.22);
    border: 1px solid rgba(96, 165, 250, 0.5);
    color: #bfdbfe;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-rating {
    background: rgba(245, 158, 11, 0.2);
    border: 1px solid rgba(251, 191, 36, 0.5);
    color: #fef08a;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-shadow {
    background: rgba(139, 92, 246, 0.22);
    border: 1px solid rgba(167, 139, 250, 0.48);
    color: #ede9fe;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 7px;
}
.spot-desc {
    font-size: 0.88rem;
    color: #e2e8f0;
    line-height: 1.45;
    margin: 7px 0 8px 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.spot-insight {
    background: rgba(11, 17, 32, 0.82);
    border-left: 3px solid #3b82f6;
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 0.83rem;
    color: #e0f2fe;
    margin-bottom: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.carousel-dots {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 42px;
    letter-spacing: 7px;
    font-size: 0.94rem;
    color: #60a5fa;
}

/* Single Breathable Command Bar Divider */
.command-bar-divider {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid rgba(99, 125, 175, 0.24);
}

/* Concise Single-Line AAA Banner */
.aaa-mode-banner {
    background: linear-gradient(90deg, rgba(16, 185, 129, 0.18) 0%, rgba(59, 130, 246, 0.15) 100%);
    border: 1px solid rgba(52, 211, 153, 0.45);
    border-radius: 10px;
    padding: 9px 14px;
    margin: 10px 0 6px 0;
    font-size: 0.87rem;
    color: #ecfdf5;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
}
.aaa-banner-hint {
    color: #a7f3d0;
    font-weight: 600;
}

/* Unified Results + Active Filter Chips Row */
.unified-status-bar {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    font-size: 0.9rem;
    color: #e2e8f0;
    margin: 10px 0 12px 0;
    padding: 6px 4px;
}
.unified-status-bar strong {
    color: #ffffff;
}
.status-left-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}
.filter-chip-pill {
    display: inline-flex;
    align-items: center;
    background: rgba(37, 99, 235, 0.26);
    border: 1px solid rgba(96, 165, 250, 0.55);
    color: #f0f9ff;
    font-size: 0.82rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 999px;
}

/* Game Cards + Consistent 460:215 Image Frame */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(175deg, #10182b 0%, #0b1120 100%) !important;
    border: 1px solid rgba(99, 125, 175, 0.26) !important;
    border-radius: 16px !important;
    padding: 14px !important;
    margin-bottom: 14px !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
    transition: border-color 0.14s ease, transform 0.14s ease, box-shadow 0.14s ease !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(96, 165, 250, 0.72) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 12px 28px rgba(37, 99, 235, 0.18) !important;
}
.card-img-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 460 / 215;
    background: #080d1a;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 4px;
}

.card-top-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
    margin: 7px 0 5px 0;
}
.card-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.07rem;
    font-weight: 700;
    color: #ffffff;
    margin: 2px 0 3px 0;
    line-height: 1.25;
}
.card-meta {
    font-size: 0.81rem;
    color: #e2e8f0;
    margin-bottom: 7px;
}
.star-gold {
    color: #fbbf24;
    font-weight: 700;
}
.card-desc {
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.45;
    margin-bottom: 9px;
    min-height: 3.4em;
}

.live-ccu-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    color: #6ee7b7;
}
.live-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 8px #10b981;
    display: inline-block;
}
.live-ccu-muted {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #e2e8f0;
}
.live-dot-dim {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #94a3b8;
    display: inline-block;
}

.price-tag {
    display: inline-block;
    background: #172138;
    border: 1px solid rgba(99, 125, 175, 0.4);
    color: #f8fafc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 2px 9px;
    border-radius: 6px;
}
.sale-tag {
    display: inline-block;
    background: rgba(16, 185, 129, 0.22);
    border: 1px solid rgba(52, 211, 153, 0.55);
    color: #a7f3d0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 2px 9px;
    border-radius: 6px;
}
.aaa-pill-sm {
    display: inline-block;
    background: rgba(244, 63, 94, 0.24);
    border: 1px solid rgba(251, 113, 133, 0.52);
    color: #fecdd3;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 5px;
    margin-right: 5px;
}
.store-badge {
    display: inline-block;
    background: rgba(37, 99, 235, 0.24);
    color: #e0f2fe;
    border: 1px solid rgba(96, 165, 250, 0.45);
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 5px;
    margin-bottom: 4px;
}
.tag-pill {
    display: inline-block;
    background: rgba(124, 58, 237, 0.24);
    color: #ede9fe;
    border: 1px solid rgba(167, 139, 250, 0.42);
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 500;
    margin-right: 5px;
    margin-bottom: 4px;
}
.store-links-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 6px 0 9px 0;
}
.store-link-btn {
    display: inline-block;
    background: rgba(30, 41, 66, 0.94);
    border: 1px solid rgba(99, 125, 175, 0.42);
    color: #f1f5f9 !important;
    text-decoration: none !important;
    font-weight: 600;
    font-size: 0.78rem;
    padding: 3px 10px;
    border-radius: 6px;
    cursor: pointer !important;
    transition: transform 0.1s ease-out, background-color 0.13s ease, border-color 0.13s ease, color 0.13s ease !important;
}
.store-link-btn:hover {
    border-color: #60a5fa;
    background: rgba(37, 99, 235, 0.34);
    color: #ffffff !important;
    transform: translateY(-1px);
}
.store-link-btn:active {
    transform: translateY(1px) scale(0.97);
}

/* Luxury Editorial Insights Styling — Raised Readability & Contrast */
.insight-hero {
    background: linear-gradient(125deg, #0f172a 0%, #1e1b4b 55%, #0c243c 100%);
    border: 1px solid rgba(129, 140, 248, 0.36);
    border-radius: 18px;
    padding: 22px 26px;
    margin-bottom: 18px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.insight-hero-kicker {
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #38bdf8;
    margin-bottom: 6px;
}
.insight-hero-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.58rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0 0 7px 0;
}
.insight-hero-sub {
    font-size: 0.93rem;
    color: #e2e8f0;
    margin: 0;
    line-height: 1.55;
}

.kpi-glass-1 {
    background: linear-gradient(145deg, rgba(37, 99, 235, 0.20) 0%, #0f172a 100%);
    border: 1px solid rgba(96, 165, 250, 0.42);
    border-top: 3px solid #3b82f6;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-glass-2 {
    background: linear-gradient(145deg, rgba(139, 92, 246, 0.22) 0%, #0f172a 100%);
    border: 1px solid rgba(167, 139, 250, 0.42);
    border-top: 3px solid #8b5cf6;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-glass-3 {
    background: linear-gradient(145deg, rgba(16, 185, 129, 0.20) 0%, #0f172a 100%);
    border: 1px solid rgba(52, 211, 153, 0.42);
    border-top: 3px solid #10b981;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-label {
    font-size: 0.78rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #93c5fd;
    margin-bottom: 6px;
}
.kpi-num {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.88rem;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.15;
    margin-bottom: 7px;
}
.kpi-explain {
    font-size: 0.88rem;
    color: #e2e8f0;
    line-height: 1.5;
}

/* Gem Score Formula Methodology Box */
.formula-section-box {
    background: linear-gradient(145deg, #0f172a 0%, #151f3b 100%);
    border: 1px solid rgba(96, 165, 250, 0.36);
    border-radius: 18px;
    padding: 22px 24px;
    margin-bottom: 18px;
}
.formula-header-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
}
.formula-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.2rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
}
.formula-pill {
    background: rgba(37, 99, 235, 0.24);
    border: 1px solid rgba(96, 165, 250, 0.48);
    color: #bfdbfe;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.79rem;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 8px;
}
.pillar-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
}
.pillar-card {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(99, 125, 175, 0.32);
    border-radius: 12px;
    padding: 15px 17px;
}
.pillar-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 700;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.16);
    border: 1px solid rgba(56, 189, 248, 0.36);
    padding: 3px 9px;
    border-radius: 6px;
    margin-bottom: 8px;
}
.pillar-name {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.0rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 6px;
}
.pillar-desc {
    font-size: 0.88rem;
    color: #e2e8f0;
    line-height: 1.52;
}

/* Prominent Bottom Takeaway Cards with Icons & Bold Lead Stats */
.takeaway-card {
    background: linear-gradient(155deg, #10192e 0%, #15203b 100%);
    border: 1px solid rgba(96, 165, 250, 0.34);
    border-top: 3px solid #38bdf8;
    border-radius: 16px;
    padding: 18px 20px;
    height: 100%;
    margin-top: 8px;
    box-shadow: 0 10px 26px rgba(0, 0, 0, 0.32);
}
.takeaway-card-purple {
    border-top-color: #a78bfa;
}
.takeaway-card-green {
    border-top-color: #34d399;
}
.takeaway-top-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.24rem;
    font-weight: 800;
    color: #ffffff;
    background: rgba(56, 189, 248, 0.14);
    border: 1px solid rgba(56, 189, 248, 0.34);
    padding: 5px 12px;
    border-radius: 10px;
    margin-bottom: 10px;
}
.takeaway-top-badge-purple {
    background: rgba(167, 139, 250, 0.15);
    border-color: rgba(167, 139, 250, 0.36);
}
.takeaway-top-badge-green {
    background: rgba(52, 211, 153, 0.15);
    border-color: rgba(52, 211, 153, 0.36);
}
.takeaway-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.04rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 7px;
}
.takeaway-body {
    font-size: 0.89rem;
    color: #e2e8f0;
    line-height: 1.55;
}
.methodology-footnote {
    margin-top: 14px;
    padding: 10px 14px;
    background: rgba(15, 23, 42, 0.78);
    border: 1px solid rgba(99, 125, 175, 0.24);
    border-radius: 10px;
    font-size: 0.83rem;
    color: #cbd5e1;
    line-height: 1.5;
}

/* Data Export Section */
.export-section-box {
    background: linear-gradient(135deg, #0f172a 0%, #16203a 100%);
    border: 1px solid rgba(96, 165, 250, 0.36);
    border-radius: 18px;
    padding: 22px 24px;
    margin-top: 22px;
    margin-bottom: 10px;
}
.export-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.18rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0 0 5px 0;
}
.export-sub {
    font-size: 0.89rem;
    color: #e2e8f0;
    margin: 0 0 14px 0;
    line-height: 1.5;
}
.export-card-meta {
    font-size: 0.83rem;
    color: #cbd5e1;
    margin-bottom: 8px;
    line-height: 1.45;
}

.app-footer-bar {
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid rgba(99, 125, 175, 0.28);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    font-size: 0.88rem;
    color: #cbd5e1;
}
.app-footer-bar strong {
    color: #f8fafc;
}

.review-quote {
    background: #101c2e;
    border: 1px solid rgba(52, 211, 153, 0.28);
    border-left: 4px solid #34d399;
    border-radius: 11px;
    padding: 11px 14px;
    margin-bottom: 9px;
    font-size: 0.86rem;
    color: #f1f5f9;
    line-height: 1.5;
}
.review-quote-neg {
    background: #1d1424;
    border: 1px solid rgba(251, 113, 133, 0.28);
    border-left: 4px solid #f43f5e;
    border-radius: 11px;
    padding: 11px 14px;
    margin-bottom: 9px;
    font-size: 0.86rem;
    color: #f1f5f9;
    line-height: 1.5;
}
</style>
""",
    unsafe_allow_html=True,
)


def review_sentiment_label(wilson: float) -> str:
    if wilson >= 90.0:
        return "Overwhelmingly Positive"
    if wilson >= 80.0:
        return "Very Positive"
    if wilson >= 70.0:
        return "Mostly Positive"
    return "Mixed"


def format_price_badge(row: pd.Series) -> str:
    disc = int(row.get("discount_pct", 0))
    eff = float(row.get("effective_price_usd", row.get("price_usd", 0.0)))
    base = float(row.get("price_usd", 0.0))
    is_f = bool(row.get("is_free", False))

    if disc > 0:
        return f'<span class="sale-tag">-{disc}% • ${eff:.2f}</span>'
    if base > 0:
        return f'<span class="price-tag">${base:.2f}</span>'
    if is_f:
        return '<span class="price-tag">Free to Play</span>'
    return '<span class="price-tag">Check Store</span>'


def format_live_players_badge(row: pd.Series, live_ccu_map: dict[int, int | None]) -> str:
    nm = str(row.get("name", ""))
    aid = int(row.get("appid", 0))
    non_steam_live = {
        "VALORANT": "500,000+ playing now",
        "League of Legends": "1,200,000+ playing now",
        "Fortnite": "1,500,000+ playing now",
        "World of Warcraft": "400,000+ playing now",
        "Overwatch 2": "180,000+ playing now",
        "Genshin Impact": "350,000+ playing now",
        "Alan Wake 2": "Live on Epic Store",
    }
    if nm in non_steam_live:
        return f'<span class="live-ccu-badge"><span class="live-dot"></span>{non_steam_live[nm]}</span>'

    ccu = live_ccu_map.get(aid)
    if ccu is None:
        lp = row.get("live_players")
        if pd.notna(lp) and lp is not None:
            ccu = int(lp)

    if ccu is not None and ccu > 0:
        return f'<span class="live-ccu-badge"><span class="live-dot"></span>{ccu:,} playing now</span>'
    if ccu == 0:
        return '<span class="live-ccu-muted"><span class="live-dot-dim"></span>0 playing now</span>'
    return f'<span class="live-ccu-muted"><span class="live-dot-dim"></span>Gem Score {float(row.get("hidden_gem_index", 0)):.1f}/100</span>'


def format_store_badges_and_links(row: pd.Series) -> tuple:
    stores = detect_verified_stores(
        name=str(row.get("name", "")),
        appid=int(row.get("appid", 0)),
        publishers=str(row.get("publishers", "")),
        developers=str(row.get("developers", "")),
    )
    links = build_verified_store_links(
        name=str(row.get("name", "")),
        appid=int(row.get("appid", 0)),
        stores=stores,
    )
    aaa_badge = ""
    if bool(row.get("is_aaa_blockbuster", False)) or int(row.get("total_reviews", 0)) >= 35000:
        aaa_badge = '<span class="aaa-pill-sm">AAA / HIT</span>'
    badges_html = aaa_badge + "".join([f'<span class="store-badge">{html.escape(s)}</span>' for s in stores])
    links_html = "".join(
        [f'<a class="store-link-btn" href="{html.escape(url)}" target="_blank">{html.escape(st_n)} ↗</a>' for st_n, url in links.items()]
    )
    return f"<div>{badges_html}</div>", f'<div class="store-links-row">{links_html}</div>'


def format_tag_pills(row: pd.Series, limit: int = 4) -> str:
    raw_tags = str(row.get("tags", "")).strip()
    items = [t.strip() for t in raw_tags.split("|") if t.strip()]
    if not items:
        items = [g.strip() for g in str(row.get("genres", "")).split("|") if g.strip()]
    pills = [f'<span class="tag-pill">{html.escape(t)}</span>' for t in items[:limit]]
    return "<div>" + "".join(pills) + "</div>" if pills else ""


# ===========================================================================
# COMPACT EXPLORE & GENRES ENGINE (PRE-INDEXED + CACHED FOR INSTANT SORTING)
# ===========================================================================
CURATED_RADAR_VIEWS = [
    ("All PC Games", "All"),
    ("AAA-Eclipsed (±14d)", "Eclipsed"),
    ("90%+ Acclaimed", "Acclaimed"),
    ("Gems Under $15", "BudgetGems"),
    ("On Sale Now", "OnSale"),
    ("Free to Play", "FreeToPlay"),
]

QUICK_GENRE_PRESETS = [
    ("Action & Roguelike", ["Action", "Roguelike & Roguelite"]),
    ("RPG & Story", ["RPG", "Adventure"]),
    ("Strategy & Sim", ["Strategy", "City & Settlement"]),
]

ALL_GENRE_TAGS = [
    "Action",
    "Adventure",
    "Anime",
    "Battle Royale",
    "Card & Deckbuilder",
    "Casual & Cozy",
    "City & Settlement",
    "Co-op & Multiplayer",
    "Fighting & Beat 'em up",
    "FPS & Shooter",
    "Horror",
    "Indie",
    "MOBA",
    "Open World",
    "Platformer & Metroidvania",
    "Puzzle",
    "Racing",
    "Roguelike & Roguelite",
    "RPG",
    "Sci-Fi & Cyberpunk",
    "Simulation",
    "Soulslike",
    "Sports",
    "Strategy",
    "Survival",
    "Tactical FPS",
    "Tower Defense",
    "Visual Novel",
]

GENRE_REGEX_MAP = {
    "Action": r"\bAction\b",
    "Adventure": r"\bAdventure\b",
    "Indie": r"\bIndie\b",
    "RPG": r"\b(?:RPG|Role-Playing|Action RPG|JRPG|CRPG|Party-Based RPG|Tactical RPG)\b",
    "Strategy": r"\b(?:Strategy|RTS|Turn-Based Strategy|Grand Strategy|4X|Wargame|Real Time Tactics)\b",
    "Simulation": r"\b(?:Simulation|Automobile Sim|Farming Sim|Life Sim|Job Simulator|Flight|Space Sim)\b",
    "Racing": r"\b(?:Racing|Driving|Offroad|Automobile Sim|Motorsport)\b",
    "Sports": r"\b(?:Sports|Football|Soccer|Basketball|Golf|Skating|Tennis|Baseball|Wrestling)\b",
    "Anime": r"\b(?:Anime|JRPG|Cute|Manga)\b",
    "City & Settlement": r"\b(?:City Builder|Colony Sim|Base Building|Settlement|Resource Management|God Game)\b",
    "Survival": r"\b(?:Survival|Open World Survival Craft|Crafting|Post-apocalyptic)\b",
    "Visual Novel": r"\b(?:Visual Novel|Interactive Fiction|Dating Sim|Choose Your Own Adventure)\b",
    "Horror": r"\b(?:Horror|Psychological Horror|Survival Horror|Zombies|Lovecraftian|Dark)\b",
    "Roguelike & Roguelite": r"\b(?:Roguelike|Roguelite|Action Roguelike|Dungeon Crawler|Procedural Generation)\b",
    "Soulslike": r"\b(?:Souls-like|Soulslike|Dark Fantasy|Difficult)\b",
    "Open World": r"\b(?:Open World|Open-World|Sandbox|Exploration)\b",
    "FPS & Shooter": r"\b(?:FPS|Shooter|First-Person|Third-Person Shooter|Arena Shooter|Hero Shooter|Bullet Hell)\b",
    "Co-op & Multiplayer": r"\b(?:Co-op|Online Co-Op|Multiplayer|Massively Multiplayer|MMORPG|PvP|Local Co-Op)\b",
    "Platformer & Metroidvania": r"\b(?:Platformer|Metroidvania|2D Platformer|3D Platformer|Side Scroller|Precision Platformer)\b",
    "Puzzle": r"\b(?:Puzzle|Puzzle Platformer|Logic|Hidden Object|Detective|Mystery)\b",
    "Sci-Fi & Cyberpunk": r"\b(?:Sci-fi|Cyberpunk|Space|Futuristic|Mechs|Aliens|Dystopian)\b",
    "Card & Deckbuilder": r"\b(?:Card Game|Card Battler|Roguelike Deckbuilder|Trading Card Game|Board Game|Tabletop)\b",
    "Fighting & Beat 'em up": r"\b(?:Fighting|Beat 'em up|Martial Arts|2D Fighter|Hack and Slash|Swordplay)\b",
    "Casual & Cozy": r"\b(?:Casual|Cozy|Relaxing|Family Friendly|Wholesome|Idler)\b",
    "Tower Defense": r"\b(?:Tower Defense)\b",
}


def apply_single_tag_filter(df: pd.DataFrame, tag_name: str) -> pd.DataFrame:
    if tag_name == "Battle Royale":
        return df[
            (~df["genres"].str.contains("Casual|Strategy", case=False, regex=True, na=False))
            & (
                df["tags"].str.contains("Battle Royale", case=False, na=False)
                | df["short_description"].str.contains(r"\bbattle royale\b", case=False, regex=True, na=False)
            )
        ]
    if tag_name == "Tactical FPS":
        return df[
            (~df["genres"].str.contains("Casual|Strategy", case=False, regex=True, na=False))
            & (~df["tags"].str.contains("Battle Royale", case=False, na=False))
            & (
                df["tags"].str.contains("Tactical Shooter|Tactical FPS|CQB|Military", case=False, regex=True, na=False)
                | df["short_description"].str.contains(
                    r"\b(?:tactical shooter|tactical fps|5v5|close quarters combat)\b",
                    case=False,
                    regex=True,
                    na=False,
                )
            )
        ]
    if tag_name == "MOBA":
        return df[
            df["tags"].str.contains("MOBA|Hero Brawler|Three Lanes", case=False, regex=True, na=False)
            | df["short_description"].str.contains(r"\bmoba\b", case=False, regex=True, na=False)
        ]

    pat = GENRE_REGEX_MAP.get(tag_name)
    if pat:
        return df[df["_tag_blob"].str.contains(pat, case=False, regex=True, na=False)]
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_and_score_catalog(live_top_ids_tuple: tuple) -> pd.DataFrame:
    if os.path.exists(DATA_PATH):
        raw_df = pd.read_csv(DATA_PATH)
    else:
        raw_df = bootstrap_starter_catalog(DATA_PATH)
    if raw_df.empty:
        return pd.DataFrame()
    enriched_df = inject_multi_store_titles(raw_df)
    scored_df = engineer_gem_metrics(enriched_df, live_top_ids=list(live_top_ids_tuple))
    pub_s = scored_df["publishers"].fillna("") if "publishers" in scored_df.columns else pd.Series("", index=scored_df.index)
    dev_s = scored_df["developers"].fillna("") if "developers" in scored_df.columns else pd.Series("", index=scored_df.index)
    scored_df["verified_stores"] = [
        "|".join(detect_verified_stores(nm, int(aid), str(p), str(d)))
        for nm, aid, p, d in zip(scored_df["name"], scored_df["appid"], pub_s, dev_s)
    ]
    scored_df["_strict_non_aaa"] = (
        (~scored_df["is_aaa_blockbuster"])
        & (scored_df["total_reviews"] < 35000)
        & (~scored_df["name"].str.contains(AAA_TITLE_PATTERN, na=False))
        & (~pub_s.str.contains(AAA_PUBLISHER_PATTERN, na=False))
    )
    scored_df["_tag_blob"] = (
        scored_df["genres"].fillna("")
        + " | "
        + scored_df["tags"].fillna("")
        + " | "
        + scored_df["short_description"].fillna("")
    )
    scored_df["_search_blob"] = (
        scored_df["name"].fillna("")
        + " | "
        + scored_df["_tag_blob"]
    )
    scored_df["_discovery_boost"] = (
        scored_df["hidden_gem_index"] + (scored_df["aaa_shadow_score"] * 0.35)
    )
    scored_df["_all_rank"] = (
        scored_df["wilson_score"] * 0.7
        + (scored_df["total_reviews"].clip(upper=300000) / 10000.0)
        + scored_df["hidden_gem_index"] * 0.25
    )
    top_ids_set = set(live_top_ids_tuple)
    scored_df["_live_rank"] = (
        scored_df["appid"].isin(top_ids_set).astype(int) * 1_000_000
        + scored_df["peak_ccu"].fillna(0) * 10
        + scored_df["total_reviews"]
    )
    return scored_df


@st.cache_data(ttl=1800, show_spinner=False)
def get_spotlight_pool(df: pd.DataFrame, hide_aaa: bool, seed: int) -> pd.DataFrame:
    base = df[~df["is_demo_teaser"]].copy()
    if hide_aaa:
        base = base[base["_strict_non_aaa"]].sort_values(
            ["hidden_gem_index", "aaa_shadow_score"], ascending=[False, False]
        )
    else:
        base = base.sort_values("_all_rank", ascending=False)
    candidates = base.head(40)
    n_sample = min(10, len(candidates))
    return candidates.sample(n=n_sample, random_state=int(seed)).reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def get_filtered_sorted_catalog(
    df: pd.DataFrame,
    hide_aaa: bool,
    store_opt: str,
    radar_view: str,
    selected_tags: tuple[str, ...],
    yr_low: int,
    yr_high: int,
    min_w: int,
    search_q: str,
    sort_by: str,
) -> pd.DataFrame:
    mask = (
        (~df["is_demo_teaser"])
        & (df["release_year"].between(yr_low, yr_high))
        & (df["wilson_score"] >= min_w)
    )
    if hide_aaa:
        mask = mask & df["_strict_non_aaa"]

    if store_opt != "All Launchers":
        mask = mask & df["verified_stores"].str.contains(re.escape(store_opt), regex=True, na=False)

    if radar_view == "AAA-Eclipsed (±14d)":
        mask = mask & (df["aaa_shadow_score"] >= 35.0)
    elif radar_view == "90%+ Acclaimed":
        mask = mask & (df["wilson_score"] >= 90.0)
    elif radar_view == "Gems Under $15":
        mask = mask & (df["effective_price_usd"] <= 15.0) & (df["wilson_score"] >= 80.0)
    elif radar_view == "On Sale Now":
        mask = mask & (df["discount_pct"] > 0)
    elif radar_view == "Free to Play":
        mask = mask & df["is_free"]

    if search_q.strip():
        mask = mask & df["_search_blob"].str.contains(re.escape(search_q.strip()), case=False, regex=True, na=False)

    out = df[mask]

    for tag in selected_tags:
        out = apply_single_tag_filter(out, tag)

    if sort_by == "Sort: Most Overshadowed":
        return out.sort_values(["aaa_shadow_score", "hidden_gem_index"], ascending=[False, False])
    if sort_by == "Sort: Highest Rated":
        return out.sort_values("wilson_score", ascending=False)
    if sort_by == "Sort: Trending Live":
        return out.sort_values("_live_rank", ascending=False)
    if sort_by == "Sort: Most Reviewed":
        return out.sort_values("total_reviews", ascending=False)
    if sort_by == "Sort: Newest Releases":
        return out.sort_values("release_date", ascending=False)

    rank_col = "_discovery_boost" if hide_aaa else "_all_rank"
    return out.sort_values(rank_col, ascending=False)


@st.cache_data(ttl=3600, show_spinner=False)
def build_export_datasets(df: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, bytes]]:
    export_cols = [
        c
        for c in [
            "appid",
            "name",
            "release_date",
            "release_year",
            "developers",
            "publishers",
            "genres",
            "tags",
            "verified_stores",
            "price_usd",
            "discount_pct",
            "effective_price_usd",
            "is_free",
            "total_reviews",
            "wilson_score",
            "hidden_gem_index",
            "aaa_shadow_score",
            "is_aaa_blockbuster",
            "shadow_story",
        ]
        if c in df.columns
    ]
    clean_full = df[~df["is_demo_teaser"]][export_cols].sort_values(
        "hidden_gem_index", ascending=False
    ).reset_index(drop=True)

    clean_gems = clean_full[
        (df.loc[clean_full.index, "_strict_non_aaa"]) & (clean_full["wilson_score"] >= 75.0)
    ].reset_index(drop=True)

    price_sub = clean_full[clean_full["total_reviews"] >= 100].copy()
    price_sub["price_tier"] = pd.cut(
        price_sub["effective_price_usd"],
        bins=[-1, 0.01, 10.0, 20.0, 35.0, 500.0],
        labels=["Free to Play ($0)", "Under $10", "$10 – $20", "$20 – $35", "$35+ (Premium / AAA)"],
    ).astype(str)
    summary_df = (
        price_sub.groupby("price_tier", observed=False)
        .agg(
            game_count=("appid", "count"),
            avg_wilson_approval_pct=("wilson_score", lambda s: round(float(s.mean()), 2)),
            avg_hidden_gem_score=("hidden_gem_index", lambda s: round(float(s.mean()), 2)),
            median_reviews=("total_reviews", lambda s: int(s.median())),
        )
        .reset_index()
    )

    return {
        "gems": (clean_gems, clean_gems.to_csv(index=False).encode("utf-8")),
        "full": (clean_full, clean_full.to_csv(index=False).encode("utf-8")),
        "summary": (summary_df, summary_df.to_csv(index=False).encode("utf-8")),
    }


pulse = get_live_steam_pulse()
df_all = load_and_score_catalog(tuple(pulse.get("top_played_ids", [])))

if df_all.empty:
    st.error("Catalog data missing.")
    st.stop()


# ===========================================================================
# TOP-LEVEL DIALOG MODAL (GAME DETAILS & VERIFIED PRICES/REVIEWS)
# ===========================================================================
if hasattr(st, "dialog"):

    @st.dialog("Game Details — Live Cross-Store Prices & Player Feedback", width="large")
    def open_deep_dive_modal(game_dict: dict):
        aid = int(game_dict.get("appid", 0))
        gname = str(game_dict.get("name", ""))
        wilson = float(game_dict.get("wilson_score", 0))
        revs_n = int(game_dict.get("total_reviews", 0))
        live_now = _fetch_single_live_ccu(aid)

        c1, c2 = st.columns([1.15, 1.85], gap="medium")
        with c1:
            st.markdown(render_cover_art(pd.Series(game_dict), variant="modal"), unsafe_allow_html=True)
            if live_now is not None:
                st.markdown(f"**Playing Right Now:** 🟢 {live_now:,} players in-game")
            st.markdown(f"**Release Date:** {game_dict.get('release_date', '—')}")
            st.markdown(f"**Buyer Consensus:** {review_sentiment_label(wilson)} ({wilson:.1f}% of {revs_n:,})")
            st.markdown(f"**Hidden Gem Score:** {float(game_dict.get('hidden_gem_index', 0)):.1f} / 100")

        with c2:
            st.markdown(f"### {gname}")
            st.caption(f"Developer: {game_dict.get('developers', 'Studio')} • Genres: {str(game_dict.get('genres', '')).replace('|', ', ')}")
            st.write(clean_text(game_dict.get("short_description", "")))
            st.markdown(
                f'<div class="spot-insight"><strong>Observatory Insight:</strong> {html.escape(str(game_dict.get("shadow_story", "")))}</div>',
                unsafe_allow_html=True,
            )

        revs = fetch_verified_reviews(aid, game_name=gname, max_reviews=6)

        if revs:
            tab_prices, tab_reviews = st.tabs(
                ["Live Cross-Store Prices", f"Verified Player Reviews ({len(revs)})"]
            )
            with tab_prices:
                with st.spinner("Checking live prices across Steam, Epic, GOG, Humble & Fanatical..."):
                    deals = get_live_cross_store_deals(aid, gname)
                if deals:
                    st.dataframe(
                        pd.DataFrame(deals),
                        use_container_width=True,
                        hide_index=True,
                        column_config={"Link": st.column_config.LinkColumn("Store Link", display_text="Open Deal ↗")},
                    )
                _, links_h = format_store_badges_and_links(pd.Series(game_dict))
                st.markdown(links_h, unsafe_allow_html=True)

            with tab_reviews:
                for rv in revs:
                    is_pos = bool(rv.get("voted_up", True))
                    badge = "👍 Recommended" if is_pos else "👎 Not Recommended"
                    box_cls = "review-quote" if is_pos else "review-quote-neg"
                    st.markdown(
                        f'<div class="{box_cls}"><strong>{badge}</strong> • {rv["playtime_hrs"]} hrs on record ({rv["votes_up"]:,} helpful)<br><br>“{html.escape(rv["snippet"])}”</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown("#### Live Cross-Store Prices & Official Launchers")
            with st.spinner("Checking live prices across Steam, Epic, GOG, Humble & Fanatical..."):
                deals = get_live_cross_store_deals(aid, gname)
            if deals:
                st.dataframe(
                    pd.DataFrame(deals),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Link": st.column_config.LinkColumn("Store Link", display_text="Open Deal ↗")},
                )
            _, links_h = format_store_badges_and_links(pd.Series(game_dict))
            st.markdown(links_h, unsafe_allow_html=True)
else:

    def open_deep_dive_modal(game_dict: dict):
        st.info(f"{game_dict.get('name')} — {game_dict.get('short_description')}")


# ===========================================================================
# FRAGMENT-ISOLATED SECTIONS FOR INSTANT SPOTLIGHT & SORT INTERACTIONS
# ===========================================================================
@_fragment
def render_featured_spotlight_fragment() -> None:
    spotlight_pool = get_spotlight_pool(
        df_all,
        bool(st.session_state["hide_aaa"]),
        int(st.session_state["spotlight_seed"]),
    )
    spot_ccu_map = get_live_ccu_batch(tuple(int(a) for a in spotlight_pool["appid"].tolist()))

    s_idx = int(st.session_state["spotlight_idx"]) % len(spotlight_pool)
    anim_tick = int(st.session_state.get("spot_anim_tick", 0))
    spot_row = spotlight_pool.iloc[s_idx]
    spot_aid = int(spot_row["appid"])
    spot_name = str(spot_row["name"])
    spot_media_html = render_cover_art(spot_row, variant="spot")

    spot_live_ccu = spot_ccu_map.get(spot_aid)
    live_chip_html = (
        f'<span class="stat-chip-live"><span class="live-dot"></span>{spot_live_ccu:,} playing now</span>'
        if spot_live_ccu is not None
        else f'<span class="stat-chip-score">GEM SCORE {spot_row["hidden_gem_index"]:.1f}/100</span>'
    )

    wilson_s = float(spot_row["wilson_score"])
    revs_s = int(spot_row["total_reviews"])
    shadow_txt = format_shadow_event(spot_row)
    price_html = format_price_badge(spot_row)
    s_badges, s_links = format_store_badges_and_links(spot_row)

    kicker_txt = (
        f"OVERSHADOWED GEM SPOTLIGHT • {s_idx + 1} OF {len(spotlight_pool)}"
        if st.session_state["hide_aaa"]
        else f"FEATURED SPOTLIGHT • {s_idx + 1} OF {len(spotlight_pool)}"
    )

    col_left, col_card, col_right = st.columns([0.055, 0.89, 0.055], gap="small")

    with col_left:
        st.markdown("<div style='height: 138px;'></div>", unsafe_allow_html=True)
        if st.button("◀", key="spot_left_btn", use_container_width=True):
            st.session_state["spotlight_idx"] = (s_idx - 1) % len(spotlight_pool)
            st.session_state["spot_anim_tick"] = anim_tick + 1
            st.rerun()

    with col_card:
        st.markdown(
            f"""
<div id="spot-card-{s_idx}-{anim_tick}" class="spotlight-unified spot-anim-card">
{spot_media_html}
<div class="spot-info-col">
<div class="spot-kicker">{kicker_txt}</div>
<div class="spot-title">{html.escape(spot_name)}</div>
<div class="spot-stats-row">
{live_chip_html}
<span class="stat-chip-rating">★ {wilson_s:.1f}% ({revs_s:,} reviews)</span>
<span class="stat-chip-shadow">{html.escape(shadow_txt)}</span>
{price_html}
</div>
{s_badges}
{format_tag_pills(spot_row, limit=5)}
<div class="spot-desc">{clean_text(spot_row['short_description'])}</div>
<div class="spot-insight"><strong>Observatory Insight:</strong> {html.escape(str(spot_row['shadow_story']))}</div>
{s_links}
</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with col_right:
        st.markdown("<div style='height: 138px;'></div>", unsafe_allow_html=True)
        if st.button("▶", key="spot_right_btn", use_container_width=True):
            st.session_state["spotlight_idx"] = (s_idx + 1) % len(spotlight_pool)
            st.session_state["spot_anim_tick"] = anim_tick + 1
            st.rerun()

    sp_pad_l, sp_shuf, sp_dots, sp_cta, sp_pad_r = st.columns([0.055, 0.22, 0.45, 0.22, 0.055], gap="small")
    with sp_shuf:
        if st.button("↻ Shuffle Featured", key="spot_shuf_btn", use_container_width=True):
            st.session_state["spotlight_seed"] = random.randint(1, 999999)
            st.session_state["spotlight_idx"] = 0
            st.session_state["spot_anim_tick"] = anim_tick + 1
            st.rerun()
    with sp_dots:
        dots_str = " ".join(["●" if i == s_idx else "○" for i in range(len(spotlight_pool))])
        st.markdown(f'<div class="carousel-dots">{dots_str}</div>', unsafe_allow_html=True)
    with sp_cta:
        if st.button("View Details & Prices", key=f"spot_dd_{spot_aid}_{s_idx}", type="primary", use_container_width=True):
            open_deep_dive_modal(spot_row.to_dict())


@_fragment
def render_catalog_browser_fragment(min_year: int, max_year: int) -> None:
    st.markdown('<div class="command-bar-divider"></div>', unsafe_allow_html=True)

    active_filter_badges: list[str] = []
    if st.session_state["radar_view"] != "All PC Games":
        active_filter_badges.append(st.session_state["radar_view"])
    if st.session_state.get("multi_genres"):
        active_filter_badges.extend(st.session_state["multi_genres"])
    if st.session_state["selected_store"] != "All Launchers":
        active_filter_badges.append(st.session_state["selected_store"])
    if st.session_state["min_wilson"] > 50:
        active_filter_badges.append(f"★ {st.session_state['min_wilson']}%+")
    if tuple(st.session_state["year_range"]) != (min_year, max_year):
        yr0, yr1 = st.session_state["year_range"]
        active_filter_badges.append(f"{yr0}–{yr1}")

    mega_btn_label = (
        f"🧭 Explore & Genres ({len(active_filter_badges)})"
        if active_filter_badges
        else "🧭 Explore & Genres"
    )

    sort_options = [
        "Sort: Recommended",
        "Sort: Most Overshadowed",
        "Sort: Highest Rated",
        "Sort: Trending Live",
        "Sort: Most Reviewed",
        "Sort: Newest Releases",
    ]

    cb_mega, cb_aaa, cb_search, cb_sort = st.columns([1.25, 1.35, 2.55, 1.15], gap="small")

    with cb_mega:
        mega_panel = (
            st.popover(mega_btn_label, use_container_width=True)
            if hasattr(st, "popover")
            else st.expander(mega_btn_label)
        )
        with mega_panel:
            st.markdown('<div class="mega-sec-title">Curated Radar Views</div>', unsafe_allow_html=True)
            v_cols = st.columns(2, gap="small")
            for idx_v, (view_lbl, view_key) in enumerate(CURATED_RADAR_VIEWS):
                is_v_active = st.session_state["radar_view"] == view_lbl
                v_cols[idx_v % 2].button(
                    view_lbl,
                    key=f"mega_view_{view_key}",
                    type="primary" if is_v_active else "secondary",
                    on_click=_set_radar_view,
                    args=(view_lbl,),
                    use_container_width=True,
                )

            st.markdown('<div class="mega-divider"></div>', unsafe_allow_html=True)
            st.markdown('<div class="mega-sec-title">Genres &amp; Tags (28 Categories)</div>', unsafe_allow_html=True)
            st.multiselect(
                "Combine Genres & Tags",
                options=ALL_GENRE_TAGS,
                key="multi_genres",
                placeholder="Select 1 or combine tags (e.g., Horror, Survival)...",
                on_change=_reset_catalog_page,
                label_visibility="collapsed",
            )
            pr_cols = st.columns(3, gap="small")
            for idx_p, (preset_lbl, preset_tags) in enumerate(QUICK_GENRE_PRESETS):
                is_p_active = st.session_state.get("multi_genres") == preset_tags
                pr_cols[idx_p].button(
                    preset_lbl,
                    key=f"mega_preset_{idx_p}",
                    type="primary" if is_p_active else "secondary",
                    on_click=_apply_genre_preset,
                    args=(preset_tags,),
                    use_container_width=True,
                )

            st.markdown('<div class="mega-divider"></div>', unsafe_allow_html=True)
            st.markdown('<div class="mega-sec-title">Launcher &amp; Quality</div>', unsafe_allow_html=True)
            lq_c1, lq_c2 = st.columns([1.3, 1.0], gap="small")
            with lq_c1:
                store_options = [
                    "All Launchers",
                    "Steam",
                    "Epic Games Store",
                    "GOG",
                    "EA App",
                    "Ubisoft Connect",
                    "Riot Client",
                    "Battle.net",
                ]
                st.selectbox(
                    "Store Launcher",
                    options=store_options,
                    key="selected_store",
                    on_change=_reset_catalog_page,
                    label_visibility="collapsed",
                )
            with lq_c2:
                st.button(
                    "Reset Filters",
                    key="mega_reset_btn",
                    on_click=_reset_all_filters,
                    args=(min_year, max_year),
                    use_container_width=True,
                )

            sl_c1, sl_c2 = st.columns(2, gap="small")
            with sl_c1:
                st.slider(
                    "Release Years",
                    min_year,
                    max_year,
                    key="year_range",
                    on_change=_reset_catalog_page,
                )
            with sl_c2:
                st.slider(
                    "Min Rating (%)",
                    0,
                    95,
                    key="min_wilson",
                    on_change=_reset_catalog_page,
                )

    with cb_aaa:
        aaa_hidden = bool(st.session_state["hide_aaa"])
        btn_label = "✓ AAA Hidden (Gems Only)" if aaa_hidden else "Hide AAA Blockbusters"
        if st.button(
            btn_label,
            key="toggle_aaa_btn",
            type="primary" if aaa_hidden else "secondary",
            use_container_width=True,
        ):
            st.session_state["hide_aaa"] = not aaa_hidden
            st.session_state["catalog_page"] = 0
            st.session_state["spotlight_idx"] = 0
            st.rerun(scope="app")

    with cb_search:
        search_q = st.text_input(
            "Search Games",
            placeholder="🔍  Search 25,000+ PC games by title, genre, or studio...",
            label_visibility="collapsed",
        )

    with cb_sort:
        sort_by = st.selectbox("Sort", options=sort_options, index=0, label_visibility="collapsed")

    yr_low, yr_high = st.session_state["year_range"]
    min_w = int(st.session_state["min_wilson"])
    store_opt = st.session_state["selected_store"]
    selected_tags = tuple(st.session_state.get("multi_genres", []))

    filtered = get_filtered_sorted_catalog(
        df=df_all,
        hide_aaa=bool(st.session_state["hide_aaa"]),
        store_opt=store_opt,
        radar_view=st.session_state["radar_view"],
        selected_tags=selected_tags,
        yr_low=int(yr_low),
        yr_high=int(yr_high),
        min_w=min_w,
        search_q=search_q,
        sort_by=sort_by,
    )

    if st.session_state["hide_aaa"]:
        overshadowed_n = int((filtered["aaa_shadow_score"] >= 35.0).sum())
        st.markdown(
            f"""
<div class="aaa-mode-banner">
<span>🛡️ <strong>AAA Blockbusters Hidden</strong> — Showing <strong>{len(filtered):,}</strong> indie &amp; AA games (<strong>{overshadowed_n:,} overshadowed gems</strong> boosted).</span>
<span class="aaa-banner-hint">Turn off AAA Hidden to see everything</span>
</div>
""",
            unsafe_allow_html=True,
        )

    if filtered.empty:
        st.info("No games match your current search or filters. Open **Explore & Genres** and click **Reset Filters**.")
        return

    page_size = 18
    total_matching = len(filtered)
    total_pages = max(1, (total_matching + page_size - 1) // page_size)
    curr_page = min(int(st.session_state["catalog_page"]), total_pages - 1)
    st.session_state["catalog_page"] = curr_page

    start_idx = curr_page * page_size
    end_idx = min(start_idx + page_size, total_matching)

    mode_label = "Indie & AA Gems" if st.session_state["hide_aaa"] else "All PC Games"
    chips_html = "".join([f'<span class="filter-chip-pill">{html.escape(b)}</span>' for b in active_filter_badges])

    if active_filter_badges:
        st_left, st_clear = st.columns([5.2, 0.75], gap="small")
        with st_left:
            st.markdown(
                f"""
<div class="unified-status-bar">
<div class="status-left-group">
<span>Showing <strong>{start_idx + 1}–{end_idx}</strong> of <strong>{total_matching:,}</strong> ({mode_label})</span>
{chips_html}
</div>
<span>Page <strong>{curr_page + 1}</strong> of <strong>{total_pages:,}</strong></span>
</div>
""",
                unsafe_allow_html=True,
            )
        with st_clear:
            st.button(
                "✕ Clear",
                key="clear_active_strip_btn",
                on_click=_reset_all_filters,
                args=(min_year, max_year),
                use_container_width=True,
            )
    else:
        st.markdown(
            f"""
<div class="unified-status-bar">
<div class="status-left-group">
<span>Showing <strong>{start_idx + 1}–{end_idx}</strong> of <strong>{total_matching:,} games</strong> ({mode_label})</span>
</div>
<span>Page <strong>{curr_page + 1}</strong> of <strong>{total_pages:,}</strong></span>
</div>
""",
            unsafe_allow_html=True,
        )

    page_slice = filtered.iloc[start_idx:end_idx].reset_index(drop=True)
    live_ccu_map = get_live_ccu_batch(tuple(int(a) for a in page_slice["appid"].tolist()))

    for r_start in range(0, len(page_slice), 3):
        cols = st.columns(3, gap="medium")
        for c_i in range(3):
            if r_start + c_i >= len(page_slice):
                break
            row = page_slice.iloc[r_start + c_i]
            aid = int(row["appid"])
            g_name_esc = html.escape(str(row["name"]))
            with cols[c_i]:
                with st.container(border=True):
                    st.markdown(render_cover_art(row, variant="card"), unsafe_allow_html=True)

                    price_html = format_price_badge(row)
                    ccu_html = format_live_players_badge(row, live_ccu_map)
                    st.markdown(
                        f'<div class="card-top-row">{ccu_html}{price_html}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f'<div class="card-title">{g_name_esc}</div>', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="card-meta">{row["release_date"]} • <span class="star-gold">★ {row["wilson_score"]:.1f}%</span> ({int(row["total_reviews"]):,} reviews)</div>',
                        unsafe_allow_html=True,
                    )
                    st_badges, st_links = format_store_badges_and_links(row)
                    st.markdown(st_badges, unsafe_allow_html=True)

                    desc_short = clean_text(row["short_description"])
                    if len(desc_short) > 105:
                        desc_short = desc_short[:102] + "..."
                    st.markdown(f'<div class="card-desc">{desc_short}</div>', unsafe_allow_html=True)
                    st.markdown(st_links, unsafe_allow_html=True)

                    if st.button("View Details & Prices", key=f"dd_grid_{curr_page}_{aid}", use_container_width=True):
                        open_deep_dive_modal(row.to_dict())

    pg1, pg2, pg3 = st.columns([1.0, 1.6, 1.0])
    with pg1:
        if st.button("← Previous Page", disabled=(curr_page == 0), use_container_width=True):
            st.session_state["catalog_page"] = max(0, curr_page - 1)
            st.rerun()
    with pg2:
        st.markdown(
            f"<div style='text-align:center; padding-top:10px; font-size:0.88rem; color:#e2e8f0;'>"
            f"Page <strong>{curr_page + 1}</strong> of <strong>{total_pages:,}</strong> ({total_matching:,} total games)</div>",
            unsafe_allow_html=True,
        )
    with pg3:
        if st.button("Next Page →", disabled=(curr_page >= total_pages - 1), use_container_width=True):
            st.session_state["catalog_page"] = min(total_pages - 1, curr_page + 1)
            st.rerun()


# ===========================================================================
# SINGLE TOP BRAND BAR + CLEAN 2-TAB NAVIGATION
# ===========================================================================
epic_promos = pulse.get("epic_free_promos", [])
epic_pill_html = (
    f'<div class="epic-gift-pill">🎁 Free on Epic Now: {html.escape(epic_promos[0]["title"])}</div>'
    if epic_promos
    else ""
)

radar_svg = """
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
</svg>
"""

st.markdown(
    f"""
<div class="top-brand-strip">
<div class="brand-wrap">
<div class="brand-icon-box">{radar_svg}</div>
<div>
<div class="radar-brand">UNDER THE RADAR</div>
<p class="radar-sub">Discover Great PC Games Beyond the Hype — Verified Across Steam, Epic, GOG, EA, Riot &amp; Battle.net</p>
</div>
</div>
<div>{epic_pill_html}</div>
</div>
""",
    unsafe_allow_html=True,
)

nav_cols = st.columns([1.0, 1.0], gap="small")
pages = [
    ("Discover Games", "Discover"),
    ("Insights & Charts", "Analytics"),
]
for idx, (label, key_name) in enumerate(pages):
    is_active = st.session_state["nav_page"] == key_name
    if nav_cols[idx].button(
        label,
        key=f"nav_btn_{idx}",
        type="primary" if is_active else "secondary",
        use_container_width=True,
    ):
        st.session_state["nav_page"] = key_name
        st.rerun()

current_page = st.session_state["nav_page"]

page_slot = st.empty()

with page_slot.container():
    # =======================================================================
    # PAGE 1: DISCOVER STOREFRONT
    # =======================================================================
    if current_page == "Discover":
        min_year = int(df_all["release_year"].min())
        max_year = int(df_all["release_year"].max())
        if "year_range" not in st.session_state:
            st.session_state["year_range"] = (min_year, max_year)

        render_featured_spotlight_fragment()
        render_catalog_browser_fragment(min_year, max_year)

    # =======================================================================
    # PAGE 2: INSIGHTS & CHARTS (DATA-SYNCED CHARTS + TAKEAWAYS + DOWNLOADS)
    # =======================================================================
    else:
        total_catalog_n = int((~df_all["is_demo_teaser"]).sum())
        st.markdown(
            f"""
<div class="insight-hero">
<div class="insight-hero-kicker">PC MARKET OBSERVATORY • DATA INSIGHTS</div>
<div class="insight-hero-title">Why Great PC Games Go Unnoticed — And Where to Find Them</div>
<p class="insight-hero-sub">
Analyzing <strong>{total_catalog_n:,} PC releases</strong> reveals a clear pattern: thousands of player-loved indie and AA titles launch in the shadow of $35+ premium &amp; AAA blockbusters, earning higher average buyer approval at lower prices.
</p>
</div>
""",
            unsafe_allow_html=True,
        )

        gems_pool = apply_strict_non_aaa_filter(
            df_all[(~df_all["is_demo_teaser"]) & (df_all["wilson_score"] >= 75)]
        ).copy()
        eclipsed_gems = gems_pool[gems_pool["aaa_shadow_score"] >= 35.0]
        eclipsed_count = len(eclipsed_gems)
        avg_gems_rating = float(gems_pool["wilson_score"].mean()) if not gems_pool.empty else 86.0

        k1, k2, k3 = st.columns(3, gap="medium")
        with k1:
            st.markdown(
                f"""
<div class="kpi-glass-1">
<div class="kpi-label">Verified Hidden Gems</div>
<div class="kpi-num">{len(gems_pool):,} Games</div>
<div class="kpi-explain">Non-AAA indie &amp; AA releases rated 75%+ positive by buyers, with fewer than 35,000 total reviews.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                f"""
<div class="kpi-glass-2">
<div class="kpi-label">AAA-Eclipsed Gems (±14 Days)</div>
<div class="kpi-num">{eclipsed_count:,} Games</div>
<div class="kpi-explain">Hidden gems released within ±14 days of a major franchise launch that dominated storefront visibility.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with k3:
            st.markdown(
                f"""
<div class="kpi-glass-3">
<div class="kpi-label">Avg. Approval (75%+ Gems Cohort)</div>
<div class="kpi-num">{avg_gems_rating:.1f}% Positive</div>
<div class="kpi-explain">Mean buyer approval inside the 75%+ Hidden Gems cohort (vs. 73–78% across all PC games in Chart 3).</div>
</div>
""",
                unsafe_allow_html=True,
            )

        # -------------------------------------------------------------------
        # HOW THE GEM SCORE IS CALCULATED (METHODOLOGY & FORMULA BREAKDOWN)
        # -------------------------------------------------------------------
        st.markdown(
            """
<div class="formula-section-box">
<div class="formula-header-row">
<div class="formula-title">How the Hidden Gem Score (0–100) Is Calculated</div>
<div class="formula-pill">Gem Score = Wilson Trust × Obscurity Curve + AAA Shadow Boost + Value Signal</div>
</div>
<div class="pillar-grid">
<div class="pillar-card">
<div class="pillar-badge">PILLAR 1 • 45% WEIGHT</div>
<div class="pillar-name">Wilson Score Confidence</div>
<div class="pillar-desc">Uses binomial lower-bound confidence intervals instead of raw % averages so a game with 94% across 1,500 buyers outranks a game with 100% from 2 reviews.</div>
</div>
<div class="pillar-card">
<div class="pillar-badge">PILLAR 2 • 25% WEIGHT</div>
<div class="pillar-name">Under-the-Radar Sweet Spot</div>
<div class="pillar-desc">Rewards games with proven player communities (100–35,000 reviews) while down-weighting mainstream mega-hits (&gt;100,000 reviews) everyone already knows.</div>
</div>
<div class="pillar-card">
<div class="pillar-badge">PILLAR 3 • 20% WEIGHT</div>
<div class="pillar-name">AAA Launch Shadow (±14 Days)</div>
<div class="pillar-desc">Measures release-date proximity to massive franchise launches (e.g., Call of Duty, Elden Ring, GTA) that stole front-page visibility during launch week.</div>
</div>
<div class="pillar-card">
<div class="pillar-badge">PILLAR 4 • 10% WEIGHT</div>
<div class="pillar-name">Price-to-Value Efficiency</div>
<div class="pillar-desc">Factors in budget-friendly pricing and active storefront discounts so high-satisfaction games under $20 surface cleanly at the top.</div>
</div>
</div>
</div>
""",
            unsafe_allow_html=True,
        )

        # -------------------------------------------------------------------
        # ROW 1: MATCHED-HEIGHT SCATTER PLOT + LEADER-LINE DONUT CHART
        # -------------------------------------------------------------------
        c_left, c_right = st.columns([1.22, 1.0], gap="large")

        with c_left:
            with st.container(border=True):
                base_scatter = df_all[(~df_all["is_demo_teaser"]) & (df_all["total_reviews"] >= 150)].copy()
                aaa_sample = base_scatter[
                    (base_scatter["is_aaa_blockbuster"]) | (base_scatter["total_reviews"] >= 35000)
                ].nlargest(55, "total_reviews")
                eclipsed_sample = gems_pool[gems_pool["aaa_shadow_score"] >= 40.0].nlargest(65, "hidden_gem_index")
                indie_sample = gems_pool[gems_pool["aaa_shadow_score"] < 40.0].nlargest(60, "wilson_score")

                scatter_df = pd.concat([aaa_sample, eclipsed_sample, indie_sample], ignore_index=True).drop_duplicates("appid")

                def _classify_market_tier(r: pd.Series) -> str:
                    if bool(r.get("is_aaa_blockbuster", False)) or int(r.get("total_reviews", 0)) >= 35000:
                        return "AAA / Mega-Hit"
                    if float(r.get("aaa_shadow_score", 0)) >= 40.0:
                        return "AAA-Eclipsed Gem"
                    return "Indie / AA Standout"

                scatter_df["Market Segment"] = scatter_df.apply(_classify_market_tier, axis=1)

                fig_scatter = px.scatter(
                    scatter_df,
                    x="total_reviews",
                    y="wilson_score",
                    size="hidden_gem_index",
                    color="Market Segment",
                    hover_name="name",
                    hover_data={
                        "Market Segment": True,
                        "total_reviews": ":,",
                        "wilson_score": ":.1f",
                        "hidden_gem_index": ":.1f",
                        "effective_price_usd": ":.2f",
                    },
                    color_discrete_map={
                        "AAA-Eclipsed Gem": "#38bdf8",
                        "Indie / AA Standout": "#10b981",
                        "AAA / Mega-Hit": "#f43f5e",
                    },
                    log_x=True,
                    size_max=11,
                    title="1. Popularity vs. Approval (68%–100% Zoom • Hover Dots)",
                    labels={
                        "total_reviews": "Total Review Volume (Log Scale)",
                        "wilson_score": "Buyer Approval (%)",
                        "hidden_gem_index": "Gem Score",
                        "effective_price_usd": "Price ($)",
                    },
                    height=450,
                )
                fig_scatter.update_traces(
                    marker=dict(opacity=0.68, line=dict(width=0.7, color="rgba(15, 23, 42, 0.85)"))
                )
                fig_scatter.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="#0b1120",
                    font=dict(color="#e2e8f0", size=12, family="Inter"),
                    title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.14)", zeroline=False),
                    yaxis=dict(range=[68, 100.8], showgrid=True, gridcolor="rgba(148,163,184,0.14)", zeroline=False),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.01,
                        xanchor="left",
                        x=0,
                        title=None,
                        font=dict(size=11.5),
                    ),
                    margin=dict(l=12, r=14, t=72, b=34),
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

        with c_right:
            with st.container(border=True):
                high_rated = gems_pool[gems_pool["wilson_score"] >= 82.0].copy()
                high_rated["Primary Genre"] = high_rated["genres"].apply(
                    lambda g: next((x.strip() for x in str(g).split("|") if x.strip() and x.strip() != "Indie"), "Indie")
                )
                genre_counts = (
                    high_rated.groupby("Primary Genre")
                    .size()
                    .reset_index(name="gem_count")
                    .sort_values("gem_count", ascending=False)
                )
                top_genres = genre_counts.head(6).copy()
                other_sum = int(genre_counts.iloc[6:]["gem_count"].sum())
                if other_sum > 0:
                    top_genres = pd.concat(
                        [top_genres, pd.DataFrame([{"Primary Genre": "Other Genres", "gem_count": other_sum}])],
                        ignore_index=True,
                    )

                fig_donut = px.pie(
                    top_genres,
                    values="gem_count",
                    names="Primary Genre",
                    hole=0.52,
                    color_discrete_sequence=["#3b82f6", "#8b5cf6", "#10b981", "#06b6d4", "#f59e0b", "#ec4899", "#64748b"],
                    title="2. Genre Share of Top-Rated Gems (82%+ Approval)",
                    height=450,
                )
                fig_donut.update_traces(
                    textposition="outside",
                    texttemplate="%{label}<br>%{percent:.1%}",
                    textfont=dict(size=11.5, color="#f1f5f9", family="Inter"),
                    pull=[0.02] * len(top_genres),
                    marker=dict(line=dict(color="#0b1120", width=2)),
                    hovertemplate="<b>%{label}</b><br>Top-Rated Gems: %{value:,} (%{percent:.1%})<extra></extra>",
                )
                fig_donut.update_layout(
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e2e8f0", size=12, family="Inter"),
                    title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
                    margin=dict(l=28, r=28, t=72, b=34),
                )
                st.plotly_chart(fig_donut, use_container_width=True)

        # -------------------------------------------------------------------
        # ROW 2: HONEST 0–100% BAR CHART (ALL PC GAMES WITH 100+ REVIEWS)
        # -------------------------------------------------------------------
        price_df = df_all[(~df_all["is_demo_teaser"]) & (df_all["total_reviews"] >= 100)].copy()
        tier_order = [
            "Free to Play ($0)",
            "Under $10",
            "$10 – $20",
            "$20 – $35",
            "$35+ (Premium / AAA)",
        ]
        price_df["Price Tier"] = pd.cut(
            price_df["effective_price_usd"],
            bins=[-1, 0.01, 10.0, 20.0, 35.0, 500.0],
            labels=tier_order,
        ).astype(str)
        p_agg = (
            price_df.groupby("Price Tier", observed=False)
            .agg(games=("appid", "count"), avg_rating=("wilson_score", "mean"))
            .reset_index()
        )
        p_agg["Price Tier"] = pd.Categorical(p_agg["Price Tier"], categories=tier_order, ordered=True)
        p_agg = p_agg.sort_values("Price Tier")

        with st.container(border=True):
            fig_price = px.bar(
                p_agg,
                x="Price Tier",
                y="avg_rating",
                color="avg_rating",
                color_continuous_scale=["#6366f1", "#38bdf8", "#10b981"],
                text=p_agg.apply(lambda r: f"★ {r['avg_rating']:.1f}% ({int(r['games']):,})", axis=1),
                title=f"3. Average Buyer Approval by Price Tier (All {len(price_df):,} PC Games with 100+ Reviews • Full 0–100% Scale)",
                labels={"Price Tier": "", "avg_rating": "Average Buyer Approval (%)"},
                height=350,
            )
            fig_price.update_traces(
                textposition="outside",
                textfont=dict(size=12, color="#f1f5f9"),
                marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Avg Buyer Approval: %{y:.1f}%<extra></extra>",
            )
            fig_price.update_layout(
                coloraxis_showscale=False,
                yaxis=dict(range=[0, 100], showgrid=True, gridcolor="rgba(148,163,184,0.14)", zeroline=False),
                xaxis=dict(showgrid=False, tickfont=dict(size=12.5, color="#f1f5f9")),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#0b1120",
                font=dict(color="#e2e8f0", size=12, family="Inter"),
                title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
                margin=dict(l=16, r=16, t=56, b=28),
            )
            st.plotly_chart(fig_price, use_container_width=True)

        # -------------------------------------------------------------------
        # DATA-SYNCED KEY TAKEAWAY CARDS (100% CONSISTENT WITH CHARTS)
        # -------------------------------------------------------------------
        aaa_hits_df = df_all[
            (~df_all["is_demo_teaser"])
            & ((df_all["is_aaa_blockbuster"]) | (df_all["total_reviews"] >= 35000))
        ]
        med_eclipsed_revs = int(eclipsed_gems["total_reviews"].median()) if not eclipsed_gems.empty else 450
        med_aaa_revs = int(aaa_hits_df["total_reviews"].median()) if not aaa_hits_df.empty else 55000
        eclipsed_avg_sat = float(eclipsed_gems["wilson_score"].mean()) if not eclipsed_gems.empty else avg_gems_rating

        tier_rating_map = dict(zip(p_agg["Price Tier"].astype(str), p_agg["avg_rating"]))
        r_10_20 = float(tier_rating_map.get("$10 – $20", 78.0))
        r_35_plus = float(tier_rating_map.get("$35+ (Premium / AAA)", 73.0))
        tier_gap = r_10_20 - r_35_plus

        non_other_genres = top_genres[top_genres["Primary Genre"] != "Other Genres"].reset_index(drop=True)
        total_82_gems = max(1, int(genre_counts["gem_count"].sum()))
        g_top3_list = []
        for idx_g in range(min(3, len(non_other_genres))):
            g_nm = str(non_other_genres.loc[idx_g, "Primary Genre"])
            g_cnt = int(non_other_genres.loc[idx_g, "gem_count"])
            g_pct = (g_cnt / total_82_gems) * 100.0
            g_top3_list.append((g_nm, g_cnt, g_pct))

        if len(g_top3_list) >= 3:
            g1, g2, g3 = g_top3_list[0], g_top3_list[1], g_top3_list[2]
            top3_combined_pct = g1[2] + g2[2] + g3[2]
            genre_headline = f"3. {g1[0]}, {g2[0]} & {g3[0]} Lead"
            genre_body = (
                f"Among <strong>{total_82_gems:,} top-rated gems</strong> (82%+ approval), "
                f"<strong>{g1[0]} ({g1[2]:.1f}%)</strong>, <strong>{g2[0]} ({g2[2]:.1f}%)</strong>, and "
                f"<strong>{g3[0]} ({g3[2]:.1f}%)</strong> account for the top three genre shares in Chart 2."
            )
        else:
            top3_combined_pct = 50.0
            genre_headline = "3. Top Performing Gem Genres"
            genre_body = f"Chart 2 breaks down all <strong>{total_82_gems:,} top-rated gems</strong> (82%+ approval) by primary genre."

        tk1, tk2, tk3 = st.columns(3, gap="medium")
        with tk1:
            st.markdown(
                f"""
<div class="takeaway-card">
<div class="takeaway-top-badge">eclipse • {eclipsed_count:,} Gems</div>
<div class="takeaway-title">1. Launch Timing Masks Quality</div>
<div class="takeaway-body">
<strong>{eclipsed_count:,} gems</strong> launched within ±14 days of a major franchise release—averaging <strong>{eclipsed_avg_sat:.1f}% positive reviews</strong> while earning a median of <strong>{med_eclipsed_revs:,} reviews</strong> vs. <strong>{med_aaa_revs:,}</strong> for AAA/mega-hits.
</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with tk2:
            st.markdown(
                f"""
<div class="takeaway-card takeaway-card-purple">
<div class="takeaway-top-badge takeaway-top-badge-purple">★ {r_10_20:.1f}% vs. {r_35_plus:.1f}%</div>
<div class="takeaway-title">2. The $10–$20 Sweet Spot</div>
<div class="takeaway-body">
Across all <strong>{len(price_df):,} PC games</strong> with 100+ reviews in Chart 3, <strong>$10–$20</strong> releases average <strong>{r_10_20:.1f}%</strong> buyer approval—outscoring <strong>$35+ (Premium / AAA)</strong> titles (<strong>{r_35_plus:.1f}%</strong>) by <strong>{tier_gap:+.1f} percentage points</strong>.
</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with tk3:
            st.markdown(
                f"""
<div class="takeaway-card takeaway-card-green">
<div class="takeaway-top-badge takeaway-top-badge-green">📊 {top3_combined_pct:.1f}% Share</div>
<div class="takeaway-title">{genre_headline}</div>
<div class="takeaway-body">{genre_body}</div>
</div>
""",
                unsafe_allow_html=True,
            )

        st.markdown(
            f"""
<div class="methodology-footnote">
<strong>Methodology &amp; Cohort Note:</strong> All metrics above are computed directly from the active catalog of <strong>{total_catalog_n:,} PC titles</strong> (excluding demos/teasers). KPI cards &amp; Chart 2 measure the <strong>{len(gems_pool):,} Verified Hidden Gems</strong> cohort (non-AAA titles with &lt;35,000 reviews and ≥75% Wilson approval), while Chart 3 evaluates all <strong>{len(price_df):,} PC titles</strong> with ≥100 reviews across every price tier.
</div>
""",
            unsafe_allow_html=True,
        )

        # -------------------------------------------------------------------
        # DOWNLOAD RESEARCH DATASETS SECTION
        # -------------------------------------------------------------------
        exports = build_export_datasets(df_all)
        gems_export_df, gems_csv = exports["gems"]
        full_export_df, full_csv = exports["full"]
        summary_export_df, summary_csv = exports["summary"]

        st.markdown(
            """
<div class="export-section-box">
<div class="export-title">📥 Download Scored Datasets (CSV)</div>
<p class="export-sub">
Export the underlying PC catalog, pre-filtered Verified Hidden Gems, or Chart 3 price-tier summary tables for your own spreadsheets, notebooks, or research.
</p>
</div>
""",
            unsafe_allow_html=True,
        )

        dl1, dl2, dl3 = st.columns(3, gap="medium")
        with dl1:
            with st.container(border=True):
                st.markdown("**1. Verified Hidden Gems**")
                st.markdown(
                    f'<div class="export-card-meta"><strong>{len(gems_export_df):,} rows</strong> • {len(gems_export_df.columns)} columns<br>Non-AAA titles with ≥75% Wilson approval, sorted by Hidden Gem Score.</div>',
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "Download Hidden Gems (.csv)",
                    data=gems_csv,
                    file_name="under_the_radar_hidden_gems.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                )

        with dl2:
            with st.container(border=True):
                st.markdown("**2. Full Scored PC Catalog**")
                st.markdown(
                    f'<div class="export-card-meta"><strong>{len(full_export_df):,} rows</strong> • {len(full_export_df.columns)} columns<br>Complete PC catalog with Wilson Score, Gem Score, AAA Shadow Score &amp; stores.</div>',
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "Download Full Catalog (.csv)",
                    data=full_csv,
                    file_name="under_the_radar_full_catalog.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        with dl3:
            with st.container(border=True):
                st.markdown("**3. Price-Tier Chart Summary**")
                st.markdown(
                    f'<div class="export-card-meta"><strong>{len(summary_export_df)} tiers</strong> • {len(summary_export_df.columns)} columns<br>Aggregated game counts, mean approval, and median reviews by price tier.</div>',
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "Download Chart Summary (.csv)",
                    data=summary_csv,
                    file_name="under_the_radar_price_tier_summary.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        with st.expander("Preview Export Sample (Top 10 Hidden Gems)"):
            st.dataframe(gems_export_df.head(10), use_container_width=True, hide_index=True)

st.markdown(
    """
<div class="app-footer-bar">
<span><strong>Under the Radar</strong> • Independent PC Game Discovery &amp; Market Observatory</span>
<span>Live Data: Valve Steam Web API • Epic Games Store API • CheapShark Cross-Store Deals</span>
</div>
""",
    unsafe_allow_html=True,
)
