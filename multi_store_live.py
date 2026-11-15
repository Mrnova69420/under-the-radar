"""
multi_store_live.py
Live Multi-Storefront Telemetry, Cross-Launcher PC Game Registry, CheapShark Deal Aggregator,
Valve Steam Web API & Storefront Ingestion, and Verified Player Review Miner.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st

HEADERS = {
    "User-Agent": "UnderTheRadar-PCObservatory/2.0 (Educational Data Science Project)"
}

MULTI_STORE_REGISTRY: List[Dict] = [
    {
        "appid": 9000001,
        "name": "VALORANT",
        "release_date": "2020-06-02",
        "release_year": 2020,
        "price_usd": 0.0,
        "discount_pct": 0,
        "is_free": True,
        "positive_reviews": 412000,
        "negative_reviews": 68000,
        "total_reviews": 480000,
        "avg_playtime_hrs": 145.0,
        "peak_ccu": 520000,
        "genres": "Action|Free To Play",
        "tags": "Tactical Shooter|FPS|5v5|Hero Shooter|Competitive|Online PvP|Precise Gunplay|Abilities",
        "categories": "Online PvP|Multi-player|Cross-Platform Multiplayer",
        "developers": "Riot Games",
        "publishers": "Riot Games",
        "short_description": "Blend your style and experience on a global, competitive stage. You have 13 rounds to attack and defend your side using sharp gunplay and tactical abilities.",
        "header_image": "https://cdn2.unrealengine.com/egs-valorant-riotgames-g1a-00-1920x1080-95b4e2f30f26.jpg",
        "stores": "Riot Client|Epic Games Store",
    },
    {
        "appid": 9000002,
        "name": "Alan Wake 2",
        "release_date": "2023-10-27",
        "release_year": 2023,
        "price_usd": 49.99,
        "discount_pct": 0,
        "is_free": False,
        "positive_reviews": 44500,
        "negative_reviews": 3200,
        "total_reviews": 47700,
        "avg_playtime_hrs": 24.5,
        "peak_ccu": 18500,
        "genres": "Action|Adventure",
        "tags": "Survival Horror|Psychological Horror|Third-Person Shooter|Story Rich|Dark|Mystery",
        "categories": "Single-player",
        "developers": "Remedy Entertainment",
        "publishers": "Epic Games Publishing",
        "short_description": "A string of ritualistic murders threatens Bright Falls. Saga Anderson, an accomplished FBI agent, arrives to investigate in a dual-protagonist survival horror thriller.",
        "header_image": "https://cdn2.unrealengine.com/egs-alanwake2-remedyentertainment-g1a-00-1920x1080-217720171.jpg",
        "stores": "Epic Games Store",
    },
    {
        "appid": 9000003,
        "name": "StarCraft II",
        "release_date": "2010-07-27",
        "release_year": 2010,
        "price_usd": 0.0,
        "discount_pct": 0,
        "is_free": True,
        "positive_reviews": 195000,
        "negative_reviews": 14000,
        "total_reviews": 209000,
        "avg_playtime_hrs": 110.0,
        "peak_ccu": 65000,
        "genres": "Strategy|Free To Play",
        "tags": "RTS|Real-Time Strategy|Sci-fi|Competitive|Online PvP|Base Building|Esports",
        "categories": "Single-player|Online PvP|Online Co-op",
        "developers": "Blizzard Entertainment",
        "publishers": "Blizzard Entertainment",
        "short_description": "Wage war across the galaxy with three unique and diverse asymmetric factions in Blizzard's landmark real-time strategy competitive ladder and campaign.",
        "header_image": "https://blz-contentstack-images.akamaized.net/v3/assets/blt0e00eb71333df64e/blt603b66f92a35b874/65381629972683040a1d6f18/sc2-og-image.jpg",
        "stores": "Battle.net",
    },
    {
        "appid": 1172470,
        "name": "Apex Legends",
        "release_date": "2020-11-04",
        "release_year": 2020,
        "price_usd": 0.0,
        "discount_pct": 0,
        "is_free": True,
        "positive_reviews": 665000,
        "negative_reviews": 215000,
        "total_reviews": 880000,
        "avg_playtime_hrs": 132.0,
        "peak_ccu": 240000,
        "genres": "Action|Adventure|Free To Play",
        "tags": "Battle Royale|FPS|Hero Shooter|Multiplayer|Fast-Paced|High Mobility|Online PvP|Sci-fi",
        "categories": "Online PvP|Online Co-op|Cross-Platform Multiplayer",
        "developers": "Respawn Entertainment",
        "publishers": "Electronic Arts",
        "short_description": "Conquer with character in Apex Legends, a free-to-play Hero Battle Royale shooter where legendary characters with powerful abilities team up to battle for fame & fortune.",
        "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1172470/header.jpg",
        "stores": "Steam|EA App|Epic Games Store",
    },
    {
        "appid": 359550,
        "name": "Tom Clancy's Rainbow Six Siege",
        "release_date": "2015-12-01",
        "release_year": 2015,
        "price_usd": 19.99,
        "discount_pct": 0,
        "is_free": False,
        "positive_reviews": 945000,
        "negative_reviews": 175000,
        "total_reviews": 1120000,
        "avg_playtime_hrs": 168.0,
        "peak_ccu": 95000,
        "genres": "Action",
        "tags": "FPS|Tactical Shooter|5v5|Destruction|Competitive|Online PvP|CQB|Operators",
        "categories": "Online PvP|Online Co-op|Multi-player",
        "developers": "Ubisoft Montreal",
        "publishers": "Ubisoft",
        "short_description": "Master the art of destruction and gadgetry in Tom Clancy's Rainbow Six Siege. Face intense close quarters combat, high lethality, tactical decision making, and team play.",
        "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/359550/header.jpg",
        "stores": "Steam|Ubisoft Connect|Epic Games Store",
    },
    {
        "appid": 1237970,
        "name": "Titanfall 2",
        "release_date": "2016-10-28",
        "release_year": 2016,
        "price_usd": 29.99,
        "discount_pct": 0,
        "is_free": False,
        "positive_reviews": 198000,
        "negative_reviews": 10500,
        "total_reviews": 208500,
        "avg_playtime_hrs": 28.0,
        "peak_ccu": 14000,
        "genres": "Action",
        "tags": "FPS|Mechs|Parkour|High Mobility|Sci-fi|Story Rich|Fast-Paced|Online PvP",
        "categories": "Single-player|Online PvP|Online Co-op",
        "developers": "Respawn Entertainment",
        "publishers": "Electronic Arts",
        "short_description": "Call down your Titan and get ready for an exhilarating first-person shooter experience combining fluid wall-running pilot parkour with colossal mech combat.",
        "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1237970/header.jpg",
        "stores": "Steam|EA App|Epic Games Store",
    },
    {
        "appid": 1091500,
        "name": "Cyberpunk 2077",
        "release_date": "2020-12-10",
        "release_year": 2020,
        "price_usd": 59.99,
        "discount_pct": 0,
        "is_free": False,
        "positive_reviews": 610000,
        "negative_reviews": 115000,
        "total_reviews": 725000,
        "avg_playtime_hrs": 64.0,
        "peak_ccu": 58000,
        "genres": "RPG|Action",
        "tags": "Cyberpunk|Open World|RPG|Sci-fi|Story Rich|FPS|First-Person|Action RPG",
        "categories": "Single-player",
        "developers": "CD PROJEKT RED",
        "publishers": "CD PROJEKT RED",
        "short_description": "Cyberpunk 2077 is an open-world, action-adventure RPG set in the dark future of Night City — a dangerous megalopolis obsessed with power, glamor, and ceaseless body modification.",
        "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1091500/header.jpg",
        "stores": "Steam|GOG|Epic Games Store",
    },
    {
        "appid": 292030,
        "name": "The Witcher 3: Wild Hunt",
        "release_date": "2015-05-18",
        "release_year": 2015,
        "price_usd": 39.99,
        "discount_pct": 0,
        "is_free": False,
        "positive_reviews": 715000,
        "negative_reviews": 29000,
        "total_reviews": 744000,
        "avg_playtime_hrs": 78.0,
        "peak_ccu": 34000,
        "genres": "RPG|Adventure",
        "tags": "Open World|RPG|Story Rich|Dark Fantasy|Third-Person|Action RPG|Choices Matter",
        "categories": "Single-player",
        "developers": "CD PROJEKT RED",
        "publishers": "CD PROJEKT RED",
        "short_description": "You are Geralt of Rivia, mercenary monster slayer. Before you stands a war-torn, monster-infested continent you can explore at will.",
        "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/292030/header.jpg",
        "stores": "Steam|GOG|Epic Games Store",
    },
]


def infer_stores_for_row(row: pd.Series) -> List[str]:
    existing = [s.strip() for s in str(row.get("stores", "")).split("|") if s.strip()]
    stores_set = list(dict.fromkeys(existing))

    aid = int(row.get("appid", 0))
    pub_dev = f"{row.get('publishers', '')} {row.get('developers', '')}".lower()

    if aid < 9000000 and "Steam" not in stores_set:
        stores_set.insert(0, "Steam")

    if any(k in pub_dev for k in ["electronic arts", "respawn", "dice", "bioware", "popcap"]) and "EA App" not in stores_set:
        stores_set.append("EA App")
    if "ubisoft" in pub_dev and "Ubisoft Connect" not in stores_set:
        stores_set.append("Ubisoft Connect")
    if any(k in pub_dev for k in ["cd projekt", "gog", "larian", "obsidian", "supergiant"]) and "GOG" not in stores_set:
        stores_set.append("GOG")
    if "riot games" in pub_dev and "Riot Client" not in stores_set:
        stores_set.append("Riot Client")
    if "blizzard" in pub_dev and "Battle.net" not in stores_set:
        stores_set.append("Battle.net")
    if any(k in pub_dev for k in ["epic games", "remedy", "rockstar", "2k", "deep silver"]) and "Epic Games Store" not in stores_set:
        stores_set.append("Epic Games Store")

    return stores_set if stores_set else ["Steam"]


def build_store_links(row: pd.Series) -> Dict[str, str]:
    aid = int(row.get("appid", 0))
    name = str(row.get("name", "")).strip()
    q = quote_plus(name)
    stores = infer_stores_for_row(row)
    links: Dict[str, str] = {}

    for st_name in stores:
        if st_name == "Steam" and aid < 9000000:
            links["Steam"] = f"https://store.steampowered.com/app/{aid}/"
        elif st_name == "Epic Games Store":
            links["Epic"] = f"https://store.epicgames.com/en-US/browse?q={q}"
        elif st_name == "GOG":
            links["GOG"] = f"https://www.gog.com/en/games?query={q}"
        elif st_name == "EA App":
            links["EA App"] = f"https://www.ea.com/games?q={q}"
        elif st_name == "Ubisoft Connect":
            links["Ubisoft"] = f"https://store.ubisoft.com/us/search?q={q}"
        elif st_name == "Riot Client":
            links["Riot"] = "https://playvalorant.com/" if "valorant" in name.lower() else "https://www.riotgames.com/"
        elif st_name == "Battle.net":
            links["Battle.net"] = "https://shop.battle.net/"

    if not links:
        links["Steam"] = f"https://store.steampowered.com/app/{aid}/" if aid < 9000000 else f"https://store.epicgames.com/en-US/browse?q={q}"
    return links


def inject_multi_store_titles(df: pd.DataFrame) -> pd.DataFrame:
    working = df.copy()
    text_cols = [
        "name",
        "release_date",
        "genres",
        "tags",
        "categories",
        "developers",
        "publishers",
        "short_description",
        "header_image",
        "stores",
    ]
    for col in text_cols:
        if col not in working.columns:
            working[col] = ""
        working[col] = working[col].fillna("").astype(str)

    existing_names_lower = set(working["name"].str.lower().str.strip())
    existing_appids = set(working["appid"].astype(int))

    new_rows = []
    for entry in MULTI_STORE_REGISTRY:
        aid = int(entry["appid"])
        nm_l = entry["name"].lower().strip()
        if aid in existing_appids:
            mask = working["appid"] == aid
            working.loc[mask, "stores"] = str(entry["stores"])
            working.loc[mask, "name"] = str(entry["name"])
            working.loc[mask, "tags"] = str(entry["tags"])
            working.loc[mask, "categories"] = str(entry["categories"])
            working.loc[mask, "short_description"] = str(entry["short_description"])
        elif nm_l not in existing_names_lower:
            new_rows.append(entry.copy())

    if new_rows:
        working = pd.concat([working, pd.DataFrame(new_rows)], ignore_index=True)

    working["stores"] = working.apply(lambda r: "|".join(infer_stores_for_row(r)), axis=1)
    return working


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 5) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        return None
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_cheapshark_store_map() -> Dict[str, str]:
    data = _get_json("https://www.cheapshark.com/api/1.0/stores", timeout=5)
    store_map: Dict[str, str] = {
        "1": "Steam",
        "7": "GOG",
        "11": "Humble Store",
        "15": "Fanatical",
        "25": "Epic Games Store",
        "3": "GreenManGaming",
    }
    if isinstance(data, list):
        for item in data:
            sid = str(item.get("storeID", ""))
            sname = str(item.get("storeName", ""))
            if sid and sname:
                store_map[sid] = sname
    return store_map


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_cross_store_deals(appid: int, game_title: str) -> List[Dict]:
    store_map = get_cheapshark_store_map()
    deals_out: List[Dict] = []

    raw_deals = None
    if int(appid) < 9000000:
        raw_deals = _get_json(
            "https://www.cheapshark.com/api/1.0/deals",
            params={"steamAppID": int(appid), "pageSize": 15},
            timeout=5,
        )
    if not raw_deals:
        raw_deals = _get_json(
            "https://www.cheapshark.com/api/1.0/deals",
            params={"title": str(game_title), "exact": 1, "pageSize": 12},
            timeout=5,
        )

    seen_stores = set()
    if isinstance(raw_deals, list):
        for d in raw_deals:
            sid = str(d.get("storeID", ""))
            sname = store_map.get(sid, f"PC Store #{sid}")
            if sname in seen_stores:
                continue
            seen_stores.add(sname)
            sale_p = float(d.get("salePrice", 0.0))
            norm_p = float(d.get("normalPrice", sale_p))
            savings = int(round(float(d.get("savings", 0.0))))
            deal_id = str(d.get("dealID", ""))
            deals_out.append(
                {
                    "Store": sname,
                    "Current Price": "Free" if sale_p == 0 else f"${sale_p:.2f}",
                    "Normal Price": "Free" if norm_p == 0 else f"${norm_p:.2f}",
                    "Discount": f"-{savings}%" if savings > 0 else "Standard",
                    "Link": f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else "",
                }
            )
    return deals_out


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_player_reviews(appid: int, max_reviews: int = 4) -> List[Dict]:
    if int(appid) >= 9000000:
        return []
    data = _get_json(
        f"https://store.steampowered.com/appreviews/{int(appid)}",
        params={
            "json": 1,
            "filter": "all",
            "language": "english",
            "day_range": 365,
            "review_type": "all",
            "purchase_type": "steam",
            "num_per_page": 8,
        },
        timeout=5,
    )
    if not data or data.get("success") != 1:
        return []

    reviews = []
    for rev in data.get("reviews", []):
        txt = str(rev.get("review", "")).strip()
        txt_clean = re.sub(r"\[/?[^\]]+\]", " ", txt)
        txt_clean = " ".join(txt_clean.split())
        if len(txt_clean) < 45:
            continue
        author = rev.get("author", {})
        hrs = round(float(author.get("playtime_forever", 0)) / 60.0, 1)
        reviews.append(
            {
                "voted_up": bool(rev.get("voted_up", True)),
                "playtime_hrs": hrs,
                "votes_up": int(rev.get("votes_up", 0)),
                "snippet": txt_clean[:280] + ("..." if len(txt_clean) > 280 else ""),
            }
        )
        if len(reviews) >= max_reviews:
            break
    return reviews


@st.cache_data(ttl=900, show_spinner=False)
def get_live_concurrent_players(appid: int) -> Optional[int]:
    if int(appid) >= 9000000:
        for entry in MULTI_STORE_REGISTRY:
            if int(entry["appid"]) == int(appid):
                return int(entry.get("peak_ccu", 0))
        return None
    data = _get_json(
        "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
        params={"appid": int(appid)},
        timeout=4,
    )
    if data and data.get("response", {}).get("result") == 1:
        return int(data["response"].get("player_count", 0))
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_epic_free_promotions() -> List[Dict]:
    data = _get_json(
        "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions",
        params={"locale": "en-US", "country": "US", "allowCountries": "US"},
        timeout=5,
    )
    if not data:
        return []
    elements = (
        data.get("data", {})
        .get("Catalog", {})
        .get("searchStore", {})
        .get("elements", [])
    )
    promos = []
    for el in elements:
        price_info = el.get("price", {}).get("totalPrice", {})
        if price_info.get("discountPrice", -1) == 0:
            slug = el.get("productSlug") or el.get("urlSlug") or ""
            promos.append(
                {
                    "title": el.get("title", "Epic Free Title"),
                    "url": f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/en-US/free-games",
                }
            )
    return promos[:4]


@st.cache_data(ttl=1800, show_spinner=False)
def get_live_review_summary(appid: int) -> Optional[Dict]:
    input_payload = json.dumps(
        {
            "appid": int(appid),
            "filter": 0,
            "languages": ["all"],
            "purchase_type": 0,
            "num_per_page": 1,
        }
    )
    data = _get_json(
        "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/",
        params={"input_json": input_payload},
        timeout=5,
    )
    if not data:
        return None

    body = data.get("response", data)
    qs = body.get("query_summary", {})
    if not qs:
        return None

    pos = int(qs.get("total_positive", 0))
    neg = int(qs.get("total_negative", 0))
    if (pos + neg) <= 0:
        return None

    return {
        "positive_reviews": pos,
        "negative_reviews": neg,
        "total_reviews": pos + neg,
        "review_score_desc": qs.get("review_score_desc", "Verified Steam Reviews"),
    }


@st.cache_data(ttl=86400, show_spinner=False)
def get_live_store_snapshot(appid: int) -> Optional[Dict]:
    if int(appid) >= 9000000:
        return None
    details = _get_json(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": int(appid), "cc": "US", "l": "english"},
        timeout=5,
    )
    if not details or str(appid) not in details or not details[str(appid)].get("success"):
        return None

    data = details[str(appid)].get("data", {})
    raw_date = str(data.get("release_date", {}).get("date", ""))
    parsed_date = pd.to_datetime(raw_date, errors="coerce")
    release_str = parsed_date.strftime("%Y-%m-%d") if pd.notna(parsed_date) else None

    is_free = bool(data.get("is_free", False))
    price_obj = data.get("price_overview") or {}
    price_usd = None
    discount_pct = 0

    if is_free:
        price_usd = 0.0
    elif price_obj:
        price_usd = round(float(price_obj.get("initial", 0)) / 100.0, 2)
        discount_pct = int(price_obj.get("discount_percent", 0))
    else:
        for pg in data.get("package_groups", []):
            subs = pg.get("subs", [])
            if subs:
                cents = subs[0].get("price_in_cents_with_discount", 0)
                if cents and cents > 0:
                    price_usd = round(float(cents) / 100.0, 2)
                    break

    return {
        "release_date": release_str,
        "price_usd": price_usd,
        "discount_pct": discount_pct,
        "is_free": is_free,
        "data": data,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_steam_pulse() -> Dict:
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    top_played_ids: List[int] = []

    charts = _get_json("https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/")
    if charts and "response" in charts:
        for row in charts["response"].get("ranks", []):
            aid = int(row.get("appid", 0))
            if aid:
                top_played_ids.append(aid)

    live_discounts: Dict[int, Dict] = {}
    new_release_ids: List[int] = []

    featured = _get_json(
        "https://store.steampowered.com/api/featuredcategories/",
        params={"cc": "US", "l": "english"},
    )
    if featured:
        for item in featured.get("specials", {}).get("items", []):
            aid = int(item.get("id", 0))
            if aid:
                live_discounts[aid] = {
                    "discount_pct": int(item.get("discount_percent", 0)),
                    "final_price_usd": round(float(item.get("final_price", 0)) / 100.0, 2),
                }
        for item in featured.get("new_releases", {}).get("items", []):
            aid = int(item.get("id", 0))
            if aid:
                new_release_ids.append(aid)

    epic_promos = get_epic_free_promotions()

    return {
        "synced_at": synced_at,
        "top_played_ids": top_played_ids,
        "live_discounts": live_discounts,
        "new_release_ids": new_release_ids,
        "epic_free_promos": epic_promos,
    }


def inspect_single_appid_live(
    appid: int, catalog_df: Optional[pd.DataFrame] = None
) -> Tuple[Optional[Dict], str]:
    aid = int(appid)
    existing_row = None
    if catalog_df is not None and not catalog_df.empty and aid in catalog_df["appid"].values:
        existing_row = catalog_df[catalog_df["appid"] == aid].iloc[0].to_dict()

    snap = get_live_store_snapshot(aid)
    meta: Optional[Dict] = None

    if snap and "data" in snap:
        data = snap["data"]
        item_type = data.get("type", "game")
        if item_type != "game":
            return None, f"AppID {aid} is listed on Steam as '{item_type}', not a standalone game."

        release_str = snap["release_date"] or (existing_row["release_date"] if existing_row else "2024-01-01")
        release_year = int(release_str[:4])
        price_usd = snap["price_usd"] if snap["price_usd"] is not None else (float(existing_row["price_usd"]) if existing_row else 0.0)

        genres = [g.get("description", "") for g in data.get("genres", []) if g.get("description")]
        categories = [c.get("description", "") for c in data.get("categories", []) if c.get("description")]
        devs = [d for d in data.get("developers", []) if d]
        pubs = [p for p in data.get("publishers", []) if p]

        meta = {
            "appid": aid,
            "name": str(data.get("name", f"App {aid}")),
            "release_date": release_str,
            "release_year": release_year,
            "price_usd": price_usd,
            "discount_pct": snap["discount_pct"],
            "is_free": snap["is_free"],
            "avg_playtime_hrs": float(existing_row.get("avg_playtime_hrs", 5.0)) if existing_row else 5.0,
            "peak_ccu": int(existing_row.get("peak_ccu", 0)) if existing_row else 0,
            "metacritic_score": (data.get("metacritic") or {}).get("score", None),
            "genres": "|".join(genres),
            "tags": existing_row.get("tags", "") if existing_row else "",
            "categories": "|".join(categories),
            "developers": "|".join(devs),
            "publishers": "|".join(pubs),
            "short_description": str(data.get("short_description", "")).replace("\n", " ").strip(),
            "header_image": str(data.get("header_image", "")).strip(),
        }

    if meta is None and existing_row is not None:
        meta = existing_row.copy()

    if meta is None:
        return None, f"Could not reach Steam Storefront details for AppID {aid}."

    rev = get_live_review_summary(aid)
    if rev:
        meta["positive_reviews"] = rev["positive_reviews"]
        meta["negative_reviews"] = rev["negative_reviews"]
        meta["total_reviews"] = rev["total_reviews"]
    elif existing_row is not None:
        meta["positive_reviews"] = int(existing_row["positive_reviews"])
        meta["negative_reviews"] = int(existing_row["negative_reviews"])
        meta["total_reviews"] = int(existing_row["total_reviews"])
    else:
        return None, f"Fetched '{meta['name']}', but Steam returned 0 public buyer reviews."

    meta["live_players"] = get_live_concurrent_players(aid)
    return meta, ""


def _fetch_live_ccu_raw(appid: int) -> Optional[int]:
    if int(appid) >= 9000000:
        for entry in MULTI_STORE_REGISTRY:
            if int(entry["appid"]) == int(appid):
                return int(entry.get("peak_ccu", 0))
        return None
    try:
        r = requests.get(
            "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
            params={"appid": int(appid)},
            headers=HEADERS,
            timeout=4,
        )
        if r.status_code == 200:
            data = r.json()
            if data and data.get("response", {}).get("result") == 1:
                return int(data["response"].get("player_count", 0))
    except requests.RequestException:
        return None
    return None


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_live_enrichment_cached(
    appid_tuple: Tuple[int, ...], fetch_store_details: bool
) -> Dict[int, Dict]:
    """Caches live CCU & store price lookups for 15 minutes so UI button clicks take 0ms."""
    pulse = get_live_steam_pulse()
    discounts = pulse.get("live_discounts", {})
    appids = list(appid_tuple)

    with ThreadPoolExecutor(max_workers=8) as pool:
        live_players_list = list(pool.map(_fetch_live_ccu_raw, appids))

    result_map: Dict[int, Dict] = {}
    for idx, aid in enumerate(appids):
        disc_info = discounts.get(aid, {})
        snap = get_live_store_snapshot(aid) if (fetch_store_details and idx < 10 and aid < 9000000) else None
        result_map[aid] = {
            "live_players": live_players_list[idx],
            "disc_pct": disc_info.get("discount_pct", 0),
            "snap": snap,
        }
    return result_map


def enrich_top_candidates_live(
    df_subset: pd.DataFrame, max_items: int = 15, fetch_store_details: bool = True
) -> pd.DataFrame:
    top_df = df_subset.head(max_items).copy()
    if top_df.empty:
        return top_df

    appids_tuple = tuple(int(a) for a in top_df["appid"].tolist())
    enrichment_map = _fetch_live_enrichment_cached(appids_tuple, fetch_store_details)

    live_players_list = []
    live_discount_list = []
    live_price_list = []
    live_eff_price_list = []
    live_date_list = []
    live_free_list = []

    for _, row in top_df.iterrows():
        aid = int(row["appid"])
        info = enrichment_map.get(aid, {})
        base_p = float(row["price_usd"])
        disc_p = int(info.get("disc_pct", int(row.get("discount_pct", 0))))
        rel_d = str(row["release_date"])
        is_f = bool(row.get("is_free", False))

        snap = info.get("snap")
        if snap:
            if snap["release_date"]:
                rel_d = snap["release_date"]
            if snap["price_usd"] is not None:
                base_p = float(snap["price_usd"])
            if snap["discount_pct"] > 0:
                disc_p = int(snap["discount_pct"])
            is_f = bool(snap["is_free"])

        eff_p = round(base_p * (1.0 - disc_p / 100.0), 2)
        live_players_list.append(info.get("live_players"))
        live_discount_list.append(disc_p)
        live_price_list.append(base_p)
        live_eff_price_list.append(eff_p)
        live_date_list.append(rel_d)
        live_free_list.append(is_f)

    top_df["live_players"] = live_players_list
    top_df["discount_pct"] = live_discount_list
    top_df["price_usd"] = live_price_list
    top_df["effective_price_usd"] = live_eff_price_list
    top_df["release_date"] = live_date_list
    top_df["is_free"] = live_free_list
    return top_df


def bootstrap_starter_catalog(csv_path: str = "data/steam_catalog.csv") -> pd.DataFrame:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    pulse = get_live_steam_pulse()
    seed_ids = list(
        dict.fromkeys(
            pulse["top_played_ids"][:25]
            + pulse["new_release_ids"][:25]
            + list(pulse["live_discounts"].keys())[:25]
        )
    )
    rows = []
    for aid in seed_ids[:45]:
        rec, _ = inspect_single_appid_live(aid)
        if rec and rec["total_reviews"] >= 25:
            rec.pop("live_players", None)
            rows.append(rec)
        time.sleep(0.35)

    df = pd.DataFrame(rows).drop_duplicates(subset=["appid"])
    df = inject_multi_store_titles(df)
    if not df.empty:
        df.to_csv(csv_path, index=False)
    return df