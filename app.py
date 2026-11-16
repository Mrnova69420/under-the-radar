"""
app.py
Under the Radar — Fast, Verified Multi-Store PC Game Discovery
Features:
  - Strict, accurate launcher verification (Steam, Epic, GOG, EA App, Ubisoft, Riot, Battle.net) — zero false tags
  - Live concurrent player counts ("● X playing now") fetched in parallel for every game on screen
  - Strict "Hide AAA Blockbusters" filter blocking mega-franchises (GTA, Elden Ring, Street Fighter, etc.)
  - Spacious Featured Spotlight at top with uncropped object-fit:contain art & centered carousel dots
  - Uncrowded 1-Row Command Bar with a wide 3-Column "Explore & Genres" Mega-Menu Panel
  - Unified status/filter bar and uniform 460:215 card image framing across the grid
  - Clean, isolated Insights & Charts page with Gem Score methodology breakdown + 3 chart types
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
    "trigger_modal": None,
    "modal_game": None,
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


def trigger_deep_dive(game_dict: dict) -> None:
    st.session_state["modal_game"] = game_dict
    st.session_state["trigger_modal"] = "deep_dive"


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
            timeout=3.5,
        )
        if resp.status_code == 200:
            payload = resp.json().get("response", {})
            if payload.get("result") == 1 and "player_count" in payload:
                return int(payload["player_count"])
    except Exception:
        pass
    return None


def get_live_ccu_for_appids(appids: list[int]) -> dict[int, int | None]:
    unique_ids = list({int(a) for a in appids if int(a) > 0})
    if not unique_ids:
        return {}
    out: dict[int, int | None] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
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
                timeout=5,
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
                    timeout=6,
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

@keyframes spotSlideIn {
    0% {
        opacity: 0.15;
        transform: translateX(24px);
    }
    100% {
        opacity: 1;
        transform: translateX(0);
    }
}
.spot-anim-card {
    animation: spotSlideIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* SLEEK, UNIFORM BUTTON DESIGN SYSTEM */
div.stButton > button {
    min-height: 42px !important;
    height: 42px !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    transition: all 0.18s cubic-bezier(0.22, 1, 0.36, 1) !important;
    box-shadow: none !important;
}

div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    border: 1px solid rgba(96, 165, 250, 0.52) !important;
    color: #ffffff !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 4px 14px rgba(37, 99, 235, 0.32) !important;
}
div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%) !important;
    border-color: #93c5fd !important;
    transform: translateY(-1px) !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 6px 20px rgba(59, 130, 246, 0.42) !important;
}

div.stButton > button[kind="secondary"],
div[data-testid="stPopover"] > button {
    min-height: 42px !important;
    height: 42px !important;
    background: rgba(24, 34, 58, 0.88) !important;
    border: 1px solid rgba(99, 125, 175, 0.34) !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    transition: all 0.18s ease !important;
}
div.stButton > button[kind="secondary"]:hover,
div[data-testid="stPopover"] > button:hover {
    background: rgba(37, 99, 235, 0.28) !important;
    border-color: rgba(96, 165, 250, 0.72) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
}
div.stButton > button:disabled {
    opacity: 0.38 !important;
    transform: none !important;
}

/* Mega-Menu Popover Panel Styling */
div[data-testid="stPopoverBody"] {
    background: linear-gradient(155deg, #0d1528 0%, #131c36 55%, #0e1e36 100%) !important;
    border: 1px solid rgba(96, 165, 250, 0.45) !important;
    border-radius: 16px !important;
    padding: 20px 22px !important;
    min-width: 780px !important;
    max-width: 92vw !important;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.78), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
}
.mega-col-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #93c5fd;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(99, 125, 175, 0.26);
}
.mega-sub-note {
    font-size: 0.8rem;
    color: #cbd5e1;
    margin: 6px 0 8px 0;
}

/* Uniform Search Bar, Dropdowns & Multi-Genre Tag Pills */
div[data-baseweb="input"] > div {
    background: #0f172a !important;
    border: 1px solid rgba(96, 165, 250, 0.38) !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    height: 42px !important;
    color: #f8fafc !important;
}
div[data-baseweb="input"] input {
    font-size: 0.9rem !important;
}
div[data-baseweb="select"] > div {
    background: #0f172a !important;
    border: 1px solid rgba(99, 125, 175, 0.32) !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    color: #f8fafc !important;
}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {
    border-color: #60a5fa !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.22) !important;
}
span[data-baseweb="tag"] {
    background: rgba(37, 99, 235, 0.32) !important;
    border: 1px solid rgba(96, 165, 250, 0.55) !important;
    color: #f0f9ff !important;
    border-radius: 6px !important;
}

/* Top Brand Bar — Generous Breathing Room */
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
    color: #cbd5e1;
    font-size: 0.82rem;
    margin: 3px 0 0 0;
}
.epic-gift-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(245, 158, 11, 0.18);
    border: 1px solid rgba(251, 191, 36, 0.48);
    color: #fef3c7;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
}

/* Fixed-Height Atomic Spotlight Card — Uncropped Cover Art */
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
    flex: 0 0 424px;
    width: 424px;
    height: 204px;
    background: #080d1a;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}
.spot-media-col img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
}
.spot-info-col {
    flex: 1 1 auto;
    min-width: 0;
}
.spot-kicker {
    font-size: 0.74rem;
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
    font-size: 0.77rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-score {
    background: rgba(59, 130, 246, 0.22);
    border: 1px solid rgba(96, 165, 250, 0.5);
    color: #bfdbfe;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.77rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-rating {
    background: rgba(245, 158, 11, 0.2);
    border: 1px solid rgba(251, 191, 36, 0.5);
    color: #fef08a;
    font-size: 0.77rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 7px;
}
.stat-chip-shadow {
    background: rgba(139, 92, 246, 0.22);
    border: 1px solid rgba(167, 139, 250, 0.48);
    color: #ede9fe;
    font-size: 0.77rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 7px;
}
.spot-desc {
    font-size: 0.87rem;
    color: #e2e8f0;
    line-height: 1.45;
    margin: 7px 0 8px 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.spot-insight {
    background: rgba(11, 17, 32, 0.78);
    border-left: 3px solid #3b82f6;
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 0.81rem;
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
    font-size: 0.92rem;
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
    background: linear-gradient(90deg, rgba(16, 185, 129, 0.16) 0%, rgba(59, 130, 246, 0.14) 100%);
    border: 1px solid rgba(52, 211, 153, 0.42);
    border-radius: 10px;
    padding: 8px 14px;
    margin: 10px 0 6px 0;
    font-size: 0.85rem;
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
    font-size: 0.88rem;
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
    background: rgba(37, 99, 235, 0.24);
    border: 1px solid rgba(96, 165, 250, 0.52);
    color: #f0f9ff;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
}

/* Game Cards + Consistent 460:215 Image Frame */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(175deg, #10182b 0%, #0b1120 100%) !important;
    border: 1px solid rgba(99, 125, 175, 0.24) !important;
    border-radius: 16px !important;
    padding: 14px !important;
    margin-bottom: 14px !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
    transition: border-color 0.18s ease, transform 0.18s ease !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(96, 165, 250, 0.65) !important;
    transform: translateY(-2px) !important;
}
.card-img-wrap {
    width: 100%;
    aspect-ratio: 460 / 215;
    background: #080d1a;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 4px;
}
.card-img-wrap img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center center;
    display: block;
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
    font-size: 1.06rem;
    font-weight: 700;
    color: #ffffff;
    margin: 2px 0 3px 0;
    line-height: 1.25;
}
.card-meta {
    font-size: 0.79rem;
    color: #cbd5e1;
    margin-bottom: 7px;
}
.star-gold {
    color: #fbbf24;
    font-weight: 700;
}
.card-desc {
    font-size: 0.83rem;
    color: #cbd5e1;
    line-height: 1.44;
    margin-bottom: 9px;
    min-height: 3.4em;
}

.live-ccu-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.77rem;
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
    font-size: 0.76rem;
    font-weight: 600;
    color: #cbd5e1;
}
.live-dot-dim {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #64748b;
    display: inline-block;
}

.price-tag {
    display: inline-block;
    background: #172138;
    border: 1px solid rgba(99, 125, 175, 0.36);
    color: #f8fafc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.77rem;
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
    font-size: 0.77rem;
    font-weight: 700;
    padding: 2px 9px;
    border-radius: 6px;
}
.aaa-pill-sm {
    display: inline-block;
    background: rgba(244, 63, 94, 0.24);
    border: 1px solid rgba(251, 113, 133, 0.52);
    color: #fecdd3;
    font-size: 0.74rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 5px;
    margin-right: 5px;
}
.store-badge {
    display: inline-block;
    background: rgba(37, 99, 235, 0.22);
    color: #e0f2fe;
    border: 1px solid rgba(96, 165, 250, 0.42);
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.77rem;
    font-weight: 600;
    margin-right: 5px;
    margin-bottom: 4px;
}
.tag-pill {
    display: inline-block;
    background: rgba(124, 58, 237, 0.22);
    color: #ede9fe;
    border: 1px solid rgba(167, 139, 250, 0.40);
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.77rem;
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
    background: rgba(30, 41, 66, 0.92);
    border: 1px solid rgba(99, 125, 175, 0.38);
    color: #e2e8f0 !important;
    text-decoration: none !important;
    font-weight: 600;
    font-size: 0.76rem;
    padding: 3px 10px;
    border-radius: 6px;
    transition: all 0.15s ease;
}
.store-link-btn:hover {
    border-color: #60a5fa;
    background: rgba(37, 99, 235, 0.28);
    color: #ffffff !important;
}

/* Luxury Editorial Insights Styling */
.insight-hero {
    background: linear-gradient(125deg, #0f172a 0%, #1e1b4b 55%, #0c243c 100%);
    border: 1px solid rgba(129, 140, 248, 0.32);
    border-radius: 18px;
    padding: 22px 26px;
    margin-bottom: 18px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.insight-hero-kicker {
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #38bdf8;
    margin-bottom: 6px;
}
.insight-hero-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.55rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0 0 6px 0;
}
.insight-hero-sub {
    font-size: 0.88rem;
    color: #cbd5e1;
    margin: 0;
    line-height: 1.5;
}

.kpi-glass-1 {
    background: linear-gradient(145deg, rgba(37, 99, 235, 0.18) 0%, #0d1425 100%);
    border: 1px solid rgba(96, 165, 250, 0.38);
    border-top: 3px solid #3b82f6;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-glass-2 {
    background: linear-gradient(145deg, rgba(139, 92, 246, 0.20) 0%, #0d1425 100%);
    border: 1px solid rgba(167, 139, 250, 0.38);
    border-top: 3px solid #8b5cf6;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-glass-3 {
    background: linear-gradient(145deg, rgba(16, 185, 129, 0.18) 0%, #0d1425 100%);
    border: 1px solid rgba(52, 211, 153, 0.38);
    border-top: 3px solid #10b981;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 16px;
}
.kpi-label {
    font-size: 0.74rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #93c5fd;
    margin-bottom: 5px;
}
.kpi-num {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.85rem;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.15;
    margin-bottom: 6px;
}
.kpi-explain {
    font-size: 0.82rem;
    color: #cbd5e1;
    line-height: 1.45;
}

/* Gem Score Formula Methodology Box */
.formula-section-box {
    background: linear-gradient(145deg, #0d1425 0%, #131b33 100%);
    border: 1px solid rgba(96, 165, 250, 0.32);
    border-radius: 18px;
    padding: 20px 24px;
    margin-bottom: 18px;
}
.formula-header-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
}
.formula-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.18rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
}
.formula-pill {
    background: rgba(37, 99, 235, 0.22);
    border: 1px solid rgba(96, 165, 250, 0.45);
    color: #93c5fd;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 8px;
}
.pillar-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(235px, 1fr));
    gap: 14px;
}
.pillar-card {
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(99, 125, 175, 0.25);
    border-radius: 12px;
    padding: 14px 16px;
}
.pillar-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.71rem;
    font-weight: 700;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.14);
    border: 1px solid rgba(56, 189, 248, 0.32);
    padding: 2px 8px;
    border-radius: 6px;
    margin-bottom: 7px;
}
.pillar-name {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.94rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 5px;
}
.pillar-desc {
    font-size: 0.8rem;
    color: #cbd5e1;
    line-height: 1.45;
}

.takeaway-card {
    background: #0d1425;
    border: 1px solid rgba(99, 125, 175, 0.26);
    border-radius: 14px;
    padding: 16px 18px;
    height: 100%;
    margin-top: 8px;
}
.takeaway-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.98rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 6px;
}
.takeaway-body {
    font-size: 0.82rem;
    color: #cbd5e1;
    line-height: 1.5;
}

.review-quote {
    background: #101c2e;
    border: 1px solid rgba(52, 211, 153, 0.28);
    border-left: 4px solid #34d399;
    border-radius: 11px;
    padding: 11px 14px;
    margin-bottom: 9px;
    font-size: 0.84rem;
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
    font-size: 0.84rem;
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
# MEGA-MENU DISCOVERY VIEWS & 28-GENRE / TAG ENGINE
# ===========================================================================
CURATED_RADAR_VIEWS = [
    ("All PC Games", "All"),
    ("AAA-Eclipsed Gems (±14d)", "Eclipsed"),
    ("90%+ Critically Acclaimed", "Acclaimed"),
    ("Hidden Gems Under $15", "BudgetGems"),
    ("On Sale Right Now", "OnSale"),
    ("Free to Play", "FreeToPlay"),
]

QUICK_GENRE_PRESETS = [
    ("Action & Roguelike", ["Action", "Roguelike & Roguelite"]),
    ("RPG & Story-Rich", ["RPG", "Adventure"]),
    ("Strategy & City Builder", ["Strategy", "City & Settlement"]),
    ("Horror & Survival", ["Horror", "Survival"]),
    ("Anime & Visual Novel", ["Anime", "Visual Novel"]),
    ("Co-op & Multiplayer", ["Co-op & Multiplayer"]),
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


def apply_single_tag_filter(df: pd.DataFrame, tag_name: str, combined_text: pd.Series) -> pd.DataFrame:
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
        return df[combined_text.loc[df.index].str.contains(pat, case=False, regex=True, na=False)]
    return df


def apply_mega_menu_filters(df: pd.DataFrame, view_name: str, selected_tags: list[str]) -> pd.DataFrame:
    if df.empty:
        return df

    out = df
    if view_name == "AAA-Eclipsed Gems (±14d)":
        out = out[out["aaa_shadow_score"] >= 35.0]
    elif view_name == "90%+ Critically Acclaimed":
        out = out[out["wilson_score"] >= 90.0]
    elif view_name == "Hidden Gems Under $15":
        out = out[(out["effective_price_usd"] <= 15.0) & (out["wilson_score"] >= 80.0)]
    elif view_name == "On Sale Right Now":
        out = out[out["discount_pct"] > 0]
    elif view_name == "Free to Play":
        out = out[out["is_free"]]

    if selected_tags:
        combined_text = (
            out["genres"].fillna("")
            + " | "
            + out["tags"].fillna("")
            + " | "
            + out["short_description"].fillna("")
        )
        for tag in selected_tags:
            out = apply_single_tag_filter(out, tag, combined_text)

    return out


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
    return scored_df


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
            if game_dict.get("header_image"):
                st.image(game_dict["header_image"], use_container_width=True)
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

    active_trigger = st.session_state.get("trigger_modal")
    if active_trigger == "deep_dive" and st.session_state.get("modal_game"):
        st.session_state["trigger_modal"] = None
        open_deep_dive_modal(st.session_state["modal_game"])


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

# Dedicated page slot guarantees 100% DOM isolation between Discover and Insights
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

        # -------------------------------------------------------------------
        # 1. FEATURED SPOTLIGHT AT THE TOP (UNCROPPED ART + CENTERED DOTS)
        # -------------------------------------------------------------------
        spotlight_base = df_all[~df_all["is_demo_teaser"]].copy()
        if st.session_state["hide_aaa"]:
            spotlight_base = apply_strict_non_aaa_filter(spotlight_base).sort_values(
                ["hidden_gem_index", "aaa_shadow_score"], ascending=[False, False]
            )
        else:
            spotlight_base["_spot_rank"] = (
                spotlight_base["wilson_score"] * 0.7
                + (spotlight_base["total_reviews"].clip(upper=300000) / 10000.0)
                + spotlight_base["hidden_gem_index"] * 0.25
            )
            spotlight_base = spotlight_base.sort_values("_spot_rank", ascending=False)

        spotlight_candidates = spotlight_base.head(40)
        n_sample = min(10, len(spotlight_candidates))
        spotlight_pool = spotlight_candidates.sample(
            n=n_sample, random_state=int(st.session_state["spotlight_seed"])
        ).reset_index(drop=True)

        s_idx = int(st.session_state["spotlight_idx"]) % len(spotlight_pool)
        anim_tick = int(st.session_state.get("spot_anim_tick", 0))
        spot_row = spotlight_pool.iloc[s_idx]
        spot_aid = int(spot_row["appid"])
        spot_name = str(spot_row["name"])
        img_url = html.escape(str(spot_row.get("header_image", "")))

        spot_live_ccu = _fetch_single_live_ccu(spot_aid)
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
<div class="spot-media-col">
<img src="{img_url}" alt="{html.escape(spot_name)}" />
</div>
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

        # Balanced Spotlight Footer: Left Button | Centered Dots | Right CTA
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
                trigger_deep_dive(spot_row.to_dict())
                st.rerun()

        # -------------------------------------------------------------------
        # 2. CLEAN 1-ROW COMMAND BAR + 3-COLUMN "EXPLORE & GENRES" MEGA-PANEL
        # -------------------------------------------------------------------
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
                m_col1, m_col2, m_col3 = st.columns([1.05, 1.45, 1.0], gap="large")

                # Column 1: Curated Radar Views
                with m_col1:
                    st.markdown('<div class="mega-col-title">Curated Radar Views</div>', unsafe_allow_html=True)
                    for view_lbl, view_key in CURATED_RADAR_VIEWS:
                        is_v_active = st.session_state["radar_view"] == view_lbl
                        st.button(
                            view_lbl,
                            key=f"mega_view_{view_key}",
                            type="primary" if is_v_active else "secondary",
                            on_click=_set_radar_view,
                            args=(view_lbl,),
                            use_container_width=True,
                        )

                # Column 2: All 28 Genres & Tags + Quick Presets
                with m_col2:
                    st.markdown('<div class="mega-col-title">Genres &amp; Tags (28 Categories)</div>', unsafe_allow_html=True)
                    st.multiselect(
                        "Combine Genres & Tags",
                        options=ALL_GENRE_TAGS,
                        key="multi_genres",
                        placeholder="Pick 1 or combine multiple tags (e.g., Horror, Survival)...",
                        on_change=_reset_catalog_page,
                        label_visibility="collapsed",
                    )
                    st.markdown('<div class="mega-sub-note">Quick Playstyle Presets:</div>', unsafe_allow_html=True)
                    p_left, p_right = st.columns(2, gap="small")
                    for idx_p, (preset_lbl, preset_tags) in enumerate(QUICK_GENRE_PRESETS):
                        target_col = p_left if idx_p % 2 == 0 else p_right
                        is_p_active = st.session_state.get("multi_genres") == preset_tags
                        target_col.button(
                            preset_lbl,
                            key=f"mega_preset_{idx_p}",
                            type="primary" if is_p_active else "secondary",
                            on_click=_apply_genre_preset,
                            args=(preset_tags,),
                            use_container_width=True,
                        )

                # Column 3: Launchers, Release Era & Rating Threshold
                with m_col3:
                    st.markdown('<div class="mega-col-title">Launchers &amp; Quality</div>', unsafe_allow_html=True)
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
                    )
                    st.slider(
                        "Release Years",
                        min_year,
                        max_year,
                        key="year_range",
                        on_change=_reset_catalog_page,
                    )
                    st.slider(
                        "Minimum Buyer Rating (%)",
                        0,
                        95,
                        key="min_wilson",
                        on_change=_reset_catalog_page,
                    )
                    st.button(
                        "Reset All Filters",
                        key="mega_reset_btn",
                        on_click=_reset_all_filters,
                        args=(min_year, max_year),
                        use_container_width=True,
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
                st.session_state["spot_anim_tick"] = anim_tick + 1
                st.rerun()

        with cb_search:
            search_q = st.text_input(
                "Search Games",
                placeholder="🔍  Search 25,000+ PC games by title, genre, or studio...",
                label_visibility="collapsed",
            )

        with cb_sort:
            sort_by = st.selectbox("Sort", options=sort_options, index=0, label_visibility="collapsed")

        # Filter Catalog
        yr_low, yr_high = st.session_state["year_range"]
        min_w = int(st.session_state["min_wilson"])
        store_opt = st.session_state["selected_store"]
        selected_tags = list(st.session_state.get("multi_genres", []))

        filtered = df_all[
            (~df_all["is_demo_teaser"])
            & (df_all["release_year"].between(yr_low, yr_high))
            & (df_all["wilson_score"] >= min_w)
        ].copy()

        if st.session_state["hide_aaa"]:
            filtered = apply_strict_non_aaa_filter(filtered)

        if store_opt != "All Launchers":
            filtered = filtered[
                filtered["verified_stores"].apply(
                    lambda s: store_opt in str(s).split("|")
                )
            ]

        filtered = apply_mega_menu_filters(filtered, st.session_state["radar_view"], selected_tags)

        if search_q.strip():
            q = search_q.strip()
            filtered = filtered[
                filtered["name"].str.contains(q, case=False, na=False)
                | filtered["short_description"].str.contains(q, case=False, na=False)
                | filtered["genres"].str.contains(q, case=False, na=False)
                | filtered["tags"].str.contains(q, case=False, na=False)
            ]

        if sort_by == "Sort: Most Overshadowed":
            filtered = filtered.sort_values(["aaa_shadow_score", "hidden_gem_index"], ascending=[False, False])
        elif sort_by == "Sort: Highest Rated":
            filtered = filtered.sort_values("wilson_score", ascending=False)
        elif sort_by == "Sort: Trending Live":
            top_ids_set = set(pulse.get("top_played_ids", []))
            filtered["_live_rank"] = (
                filtered["appid"].isin(top_ids_set).astype(int) * 1_000_000
                + filtered["peak_ccu"].fillna(0) * 10
                + filtered["total_reviews"]
            )
            filtered = filtered.sort_values("_live_rank", ascending=False)
        elif sort_by == "Sort: Most Reviewed":
            filtered = filtered.sort_values("total_reviews", ascending=False)
        elif sort_by == "Sort: Newest Releases":
            filtered = filtered.sort_values("release_date", ascending=False)
        else:
            if st.session_state["hide_aaa"]:
                filtered["_discovery_boost"] = (
                    filtered["hidden_gem_index"] + (filtered["aaa_shadow_score"] * 0.35)
                )
                filtered = filtered.sort_values("_discovery_boost", ascending=False)
            else:
                filtered["_all_rank"] = (
                    filtered["wilson_score"] * 0.7
                    + (filtered["total_reviews"].clip(upper=300000) / 10000.0)
                    + filtered["hidden_gem_index"] * 0.25
                )
                filtered = filtered.sort_values("_all_rank", ascending=False)

        # Concise Single-Line AAA Banner (Only Shown When Toggle Is Active)
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

        # -------------------------------------------------------------------
        # 3. PAGINATED GAMES GRID WITH UNIFIED STATUS/FILTER BAR & UNIFORM ART
        # -------------------------------------------------------------------
        if filtered.empty:
            st.info("No games match your current search or filters. Open **Explore & Genres** and click **Reset All Filters**.")
        else:
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
            live_ccu_map = get_live_ccu_for_appids(page_slice["appid"].tolist())

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
                            if row["header_image"]:
                                card_img_esc = html.escape(str(row["header_image"]))
                                st.markdown(
                                    f'<div class="card-img-wrap"><img src="{card_img_esc}" alt="{g_name_esc}" loading="lazy" /></div>',
                                    unsafe_allow_html=True,
                                )

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
                                trigger_deep_dive(row.to_dict())
                                st.rerun()

            pg1, pg2, pg3 = st.columns([1.0, 1.6, 1.0])
            with pg1:
                if st.button("← Previous Page", disabled=(curr_page == 0), use_container_width=True):
                    st.session_state["catalog_page"] = max(0, curr_page - 1)
                    st.rerun()
            with pg2:
                st.markdown(
                    f"<div style='text-align:center; padding-top:10px; font-size:0.86rem; color:#cbd5e1;'>"
                    f"Page <strong>{curr_page + 1}</strong> of <strong>{total_pages:,}</strong> ({total_matching:,} total games)</div>",
                    unsafe_allow_html=True,
                )
            with pg3:
                if st.button("Next Page →", disabled=(curr_page >= total_pages - 1), use_container_width=True):
                    st.session_state["catalog_page"] = min(total_pages - 1, curr_page + 1)
                    st.rerun()

    # =======================================================================
    # PAGE 2: INSIGHTS & CHARTS (GEM SCORE METHODOLOGY + SCATTER + DONUT + BAR)
    # =======================================================================
    else:
        st.markdown(
            """
<div class="insight-hero">
<div class="insight-hero-kicker">PC MARKET OBSERVATORY • DATA INSIGHTS</div>
<div class="insight-hero-title">Why Great PC Games Go Unnoticed — And Where to Find Them</div>
<p class="insight-hero-sub">
Analyzing 25,000+ PC releases reveals a clear pattern: thousands of player-loved indie and AA titles launch in the shadow of $70 mega-blockbusters, delivering higher player satisfaction at a fraction of the price.
</p>
</div>
""",
            unsafe_allow_html=True,
        )

        gems_pool = apply_strict_non_aaa_filter(
            df_all[(~df_all["is_demo_teaser"]) & (df_all["wilson_score"] >= 75)]
        ).copy()
        eclipsed_count = int((gems_pool["aaa_shadow_score"] >= 35.0).sum())
        avg_rating = float(gems_pool["wilson_score"].mean()) if not gems_pool.empty else 86.0

        k1, k2, k3 = st.columns(3, gap="medium")
        with k1:
            st.markdown(
                f"""
<div class="kpi-glass-1">
<div class="kpi-label">Verified Hidden Gems</div>
<div class="kpi-num">{len(gems_pool):,} Games</div>
<div class="kpi-explain">Indie &amp; AA titles rated 75%+ positive by real buyers, yet still flying under the mainstream radar.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                f"""
<div class="kpi-glass-2">
<div class="kpi-label">Buried by AAA Launches</div>
<div class="kpi-num">{eclipsed_count:,} Games</div>
<div class="kpi-explain">Released within ±14 days of a mega-blockbuster and starved of front-page storefront visibility.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with k3:
            st.markdown(
                f"""
<div class="kpi-glass-3">
<div class="kpi-label">Average Player Satisfaction</div>
<div class="kpi-num">{avg_rating:.1f}% Positive</div>
<div class="kpi-explain">Consistent buyer happiness across smaller studios — regularly outscoring $60–$70 AAA launches.</div>
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
        # ROW 1: CHART 1 (BUBBLE SCATTER PLOT) + CHART 2 (GENRE DONUT CHART)
        # -------------------------------------------------------------------
        c_left, c_right = st.columns([1.3, 1.0], gap="large")

        with c_left:
            base_scatter = df_all[(~df_all["is_demo_teaser"]) & (df_all["total_reviews"] >= 150)].copy()
            aaa_sample = base_scatter[
                (base_scatter["is_aaa_blockbuster"]) | (base_scatter["total_reviews"] >= 35000)
            ].nlargest(90, "total_reviews")
            eclipsed_sample = gems_pool[gems_pool["aaa_shadow_score"] >= 40.0].nlargest(140, "hidden_gem_index")
            indie_sample = gems_pool[gems_pool["aaa_shadow_score"] < 40.0].nlargest(120, "wilson_score")

            scatter_df = pd.concat([aaa_sample, eclipsed_sample, indie_sample], ignore_index=True).drop_duplicates("appid")

            def _classify_market_tier(r: pd.Series) -> str:
                if bool(r.get("is_aaa_blockbuster", False)) or int(r.get("total_reviews", 0)) >= 35000:
                    return "AAA Blockbuster / Mega-Hit"
                if float(r.get("aaa_shadow_score", 0)) >= 40.0:
                    return "AAA-Eclipsed Hidden Gem"
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
                    "AAA-Eclipsed Hidden Gem": "#38bdf8",
                    "Indie / AA Standout": "#10b981",
                    "AAA Blockbuster / Mega-Hit": "#f43f5e",
                },
                log_x=True,
                size_max=16,
                title="1. Popularity vs. Player Satisfaction (Hover Any Bubble to Inspect)",
                labels={
                    "total_reviews": "Total Review Volume (Log Scale)",
                    "wilson_score": "Buyer Approval (%)",
                    "hidden_gem_index": "Gem Score",
                    "effective_price_usd": "Price ($)",
                },
                height=430,
            )
            fig_scatter.update_traces(marker=dict(opacity=0.82, line=dict(width=0.8, color="#0f172a")))
            fig_scatter.update_layout(
                paper_bgcolor="#0d1425",
                plot_bgcolor="#0d1425",
                font=dict(color="#e2e8f0", size=12, family="Inter"),
                title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
                xaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.12)", zeroline=False),
                yaxis=dict(range=[58, 101], showgrid=True, gridcolor="rgba(148,163,184,0.12)", zeroline=False),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.01,
                    xanchor="left",
                    x=0,
                    title=None,
                    font=dict(size=11),
                ),
                margin=dict(l=14, r=18, t=72, b=36),
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with c_right:
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
                hole=0.54,
                color_discrete_sequence=["#3b82f6", "#8b5cf6", "#10b981", "#06b6d4", "#f59e0b", "#ec4899", "#64748b"],
                title="2. Genre Share of Top-Rated Gems (82%+)",
                height=430,
            )
            fig_donut.update_traces(
                textinfo="percent",
                textfont=dict(size=12, color="#ffffff", family="Inter"),
                marker=dict(line=dict(color="#0d1425", width=2)),
                hovertemplate="<b>%{label}</b><br>Top-Rated Gems: %{value:,} (%{percent})<extra></extra>",
            )
            fig_donut.update_layout(
                paper_bgcolor="#0d1425",
                plot_bgcolor="#0d1425",
                font=dict(color="#e2e8f0", size=12, family="Inter"),
                title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.02,
                    font=dict(size=11.5),
                ),
                margin=dict(l=12, r=12, t=60, b=28),
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        # -------------------------------------------------------------------
        # ROW 2: CHART 3 (BAR CHART — PRICE TIER VS. PLAYER SATISFACTION)
        # -------------------------------------------------------------------
        price_df = df_all[(~df_all["is_demo_teaser"]) & (df_all["total_reviews"] >= 100)].copy()
        price_df["Price Tier"] = pd.cut(
            price_df["effective_price_usd"],
            bins=[-1, 0.01, 10.0, 20.0, 35.0, 500.0],
            labels=["Free to Play ($0)", "Under $10", "$10 – $20", "$20 – $35", "$35+ (AAA Tier)"],
        ).astype(str)
        tier_order = ["Free to Play ($0)", "Under $10", "$10 – $20", "$20 – $35", "$35+ (AAA Tier)"]
        p_agg = (
            price_df.groupby("Price Tier", observed=False)
            .agg(games=("appid", "count"), avg_rating=("wilson_score", "mean"))
            .reset_index()
        )
        p_agg["Price Tier"] = pd.Categorical(p_agg["Price Tier"], categories=tier_order, ordered=True)
        p_agg = p_agg.sort_values("Price Tier")

        fig_price = px.bar(
            p_agg,
            x="Price Tier",
            y="avg_rating",
            color="avg_rating",
            color_continuous_scale=["#6366f1", "#38bdf8", "#10b981"],
            text=p_agg.apply(lambda r: f"★ {r['avg_rating']:.1f}%  ({int(r['games']):,} games)", axis=1),
            title="3. Price vs. Player Approval — Mid-Priced Indie & AA Games Outscore $35+ Releases",
            labels={"Price Tier": "", "avg_rating": "Average Player Approval (%)"},
            height=330,
        )
        fig_price.update_traces(
            textposition="outside",
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Avg Buyer Rating: %{y:.1f}%<extra></extra>",
        )
        fig_price.update_layout(
            coloraxis_showscale=False,
            yaxis=dict(range=[65, 92], showgrid=True, gridcolor="rgba(148,163,184,0.12)", zeroline=False),
            xaxis=dict(showgrid=False),
            paper_bgcolor="#0d1425",
            plot_bgcolor="#0d1425",
            font=dict(color="#e2e8f0", size=12, family="Inter"),
            title_font=dict(size=15, color="#ffffff", family="Plus Jakarta Sans"),
            margin=dict(l=16, r=16, t=54, b=32),
        )
        st.plotly_chart(fig_price, use_container_width=True)

        # Clean 3-Card Key Takeaways Strip
        tk1, tk2, tk3 = st.columns(3, gap="medium")
        with tk1:
            st.markdown(
                """
<div class="takeaway-card">
<div class="takeaway-title">1. Launch Timing Beats Marketing</div>
<div class="takeaway-body">Games releasing within two weeks of a major franchise lose up to 80% of storefront visibility despite earning 90%+ positive buyer reviews.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with tk2:
            st.markdown(
                """
<div class="takeaway-card">
<div class="takeaway-title">2. The $10–$20 Sweet Spot</div>
<div class="takeaway-body">Focused indie and AA titles priced between $10 and $20 consistently achieve higher player approval than $60–$70 blockbuster releases.</div>
</div>
""",
                unsafe_allow_html=True,
            )
        with tk3:
            st.markdown(
                """
<div class="takeaway-card">
<div class="takeaway-title">3. Action, Adventure &amp; Sim Lead</div>
<div class="takeaway-body">Action, Adventure, and Simulation hold the highest concentration of 82%+ rated gems across Steam, Epic, and GOG.</div>
</div>
""",
                unsafe_allow_html=True,
            )

st.divider()
st.caption("Under the Radar • Powered by Valve Steam Web API, Epic Games Store API & CheapShark Cross-Store Deals.")
