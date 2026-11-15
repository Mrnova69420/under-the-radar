"""
analytics.py
Latent Semantic Vector Embedding Engine (128-D TruncatedSVD + Structured Mechanical Facets),
95% Wilson Score Lower Bound, Gaussian AAA Launch Shadow Kernel, 2D Gameplay Space Coordinates,
9-Criteria Alternative Evaluation, and Clean Usable Dataset Export Builder.
"""

import re
from typing import Dict, List, Set, Tuple
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
import streamlit as st

PLATFORM_NOISE = {
    "steam achievements",
    "steam cloud",
    "steam trading cards",
    "full controller support",
    "partial controller support",
    "captions available",
    "steam workshop",
    "stats",
    "steam leaderboards",
    "remote play on phone",
    "remote play on tablet",
    "remote play on tv",
    "remote play together",
    "family sharing",
    "in-app purchases",
    "valve anti-cheat enabled",
    "includes level editor",
    "commentary available",
    "hdr available",
    "steam timeline",
}

FACET_LABELS: Dict[str, str] = {
    "fps": "First-Person Perspective",
    "tps": "Third-Person Perspective",
    "tactical_round": "Tactical Round / Objective FPS",
    "battle_royale": "Battle Royale Loop",
    "extraction": "Extraction Loop",
    "large_scale_war": "Large-Scale Combined-Arms Warfare",
    "hero_arena": "Ability-First Hero Arena",
    "abilities": "Operator / Hero Utility",
    "high_mobility": "High-Mobility Movement",
    "ballistics": "Realistic Ballistics & Positioning",
    "pvp": "Competitive Online PvP",
    "coop": "Squad Co-op",
    "open_world": "Open-World Sandbox",
    "crime": "Crime & Heists",
    "driving": "Vehicles & Driving",
    "retro_boomer": "Retro / Boomer Shooter",
    "shmup_2d": "2D Bullet Hell / Top-Down",
    "melee": "Melee / Martial Arts Combat",
    "fighting": "Fighting / Brawler",
    "soulslike": "Soulslike Stamina & Boss Combat",
    "rpg": "RPG Progression",
    "crpg": "Turn-Based / Isometric CRPG",
    "roguelike": "Roguelike Run Progression",
    "strategy": "RTS / Grand Strategy",
    "builder_sim": "Colony / Management / Life Sim",
    "survival": "Survival & Crafting",
    "horror": "Psychological / Survival Horror",
    "platformer_2d": "2D Metroidvania / Platformer",
    "casual_party": "Casual / Party / Puzzle / VN",
}

FACET_RULES: Dict[str, str] = {
    "fps": r"\b(?:first[- ]person|fps|precise gunplay)\b",
    "tps": r"\b(?:third[- ]person|cover shooter)\b",
    "tactical_round": r"\b(?:tactical shooter|counter[- ]terrorist|swat|5v5|defuse|bomb[- ]plant|cqb|round[- ]based|destruction|insurgency|zero hour|ground branch|due process|fragpunk|valorant|rainbow six)\b",
    "battle_royale": r"\b(?:battle royale|last team standing|last squad|shrinking zone|safe zone|battlegrounds|pubg|apex legends|naraka|farlight|super people|bloodhunt|realm royale|spellbreak)\b",
    "extraction": r"\b(?:extraction shooter|extract|tarkov|hunt: showdown|arena breakout|dark and darker|marauders)\b",
    "large_scale_war": r"\b(?:large[- ]scale|combined arms|platoon|armored vehicles|tanks and helicopters|mil[- ]?sim|squad|hell let loose|battlefield|arma)\b",
    "hero_arena": r"\b(?:overwatch|paladins|marvel rivals|team fortress|payload|capture point)\b",
    "abilities": r"\b(?:operators|agents|shard cards|gadgets|abilities|hero shooter)\b",
    "high_mobility": r"\b(?:fast[- ]paced|parkour|jetpack|grappling hook|high mobility|movement shooter|slide)\b",
    "ballistics": r"\b(?:realistic|ballistics|bullet drop|hardcore|military|tactical)\b",
    "pvp": r"\b(?:online pvp|competitive|esports|ranked|team[- ]based|pvp|5v5)\b",
    "coop": r"\b(?:online co[- ]op|co[- ]op|cooperative)\b",
    "open_world": r"\b(?:open[- ]world|open world|sandbox|living city)\b",
    "crime": r"\b(?:crime|criminal|heist|gang|mafia|underworld|outlaw|grand theft auto|saints row|sleeping dogs|watch_dogs)\b",
    "driving": r"\b(?:driving|racing|motorcycles|drift|motorsport)\b",
    "retro_boomer": r"\b(?:boomer shooter|retro|old school|pixel graphics|pixel art|parody)\b",
    "shmup_2d": r"\b(?:bullet hell|shoot 'em up|shmup|twin stick shooter|top[- ]down shooter)\b",
    "melee": r"\b(?:hack and slash|swordplay|martial arts|katana|samurai)\b",
    "fighting": r"\b(?:fighting|2d fighter|beat 'em up|brawler)\b",
    "soulslike": r"\b(?:soulslike|souls[- ]like|dark fantasy|boss rush|stamina|parry|elden ring|dark souls|sekiro)\b",
    "rpg": r"\b(?:rpg|role[- ]playing|jrpg|action rpg|skill tree)\b",
    "crpg": r"\b(?:crpg|turn[- ]based combat|dungeons & dragons|isometric rpg|party[- ]based rpg|baldur's gate)\b",
    "roguelike": r"\b(?:roguelike|roguelite|permadeath|deckbuilder)\b",
    "strategy": r"\b(?:strategy|rts|real[- ]time strategy|4x|grand strategy|starcraft|age of empires)\b",
    "builder_sim": r"\b(?:city builder|colony sim|management|tycoon|automation|base building|farming sim|life sim)\b",
    "survival": r"\b(?:survival|crafting|open world survival craft|post[- ]apocalyptic)\b",
    "horror": r"\b(?:horror|psychological horror|survival horror|lovecraftian)\b",
    "platformer_2d": r"\b(?:platformer|metroidvania|side[- ]?scroller|precision platformer|2d platformer|hollow knight)\b",
    "casual_party": r"\b(?:hidden object|point & click|visual novel|otome|dating sim|anime|interactive fiction|walking simulator|match 3|solitaire|puzzle|board game|card game|collector's edition|party game|family friendly|kids|cartoon|minigames)\b",
}


def compute_wilson_score(positive: pd.Series, total: pd.Series, z: float = 1.96) -> pd.Series:
    n = total.clip(lower=1).astype(float)
    phat = (positive.astype(float) / n).clip(0.0, 1.0)
    z2 = z * z
    numerator = phat + z2 / (2 * n) - z * np.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
    denominator = 1 + z2 / n
    return ((numerator / denominator) * 100.0).round(2)


def extract_structured_facets(row: pd.Series) -> Set[str]:
    name_l = str(row.get("name", "")).lower()
    genres_l = str(row.get("genres", "")).lower()
    tags_l = str(row.get("tags", "")).lower()
    cats_l = str(row.get("categories", "")).lower()
    desc_l = str(row.get("short_description", "")).lower()

    blob = f"{name_l} {genres_l.replace('|', ' ')} {tags_l.replace('|', ' ')} {cats_l.replace('|', ' ')} {desc_l}"
    facets: Set[str] = set()

    for facet, pattern in FACET_RULES.items():
        if re.search(pattern, blob):
            facets.add(facet)

    if "casual" in genres_l or "collector's edition" in name_l or "party edition" in name_l:
        facets.add("casual_party")

    if "battle royale" in tags_l or any(k in name_l for k in ["pubg", "battlegrounds", "apex legends", "naraka", "farlight 84", "super people", "bloodhunt"]):
        facets.update({"battle_royale", "pvp"})
        facets -= {"tactical_round", "large_scale_war", "hero_arena", "casual_party"}
    elif any(k in name_l for k in ["counter-strike", "valorant", "rainbow six", "insurgency: sandstorm", "zero hour", "ground branch", "due process", "fragpunk", "spectre divide"]):
        facets.update({"fps", "tactical_round", "pvp"})
        facets -= {"battle_royale", "large_scale_war", "hero_arena", "retro_boomer", "casual_party"}
    elif any(k in name_l for k in ["tarkov", "hunt: showdown", "arena breakout", "dark and darker", "marauders"]):
        facets.update({"extraction", "pvp"})
        facets -= {"battle_royale", "tactical_round"}
    elif any(k in name_l for k in ["overwatch", "team fortress", "paladins", "marvel rivals"]):
        facets.update({"hero_arena", "pvp"})
        facets -= {"battle_royale", "tactical_round"}
    elif any(k in name_l for k in ["squad", "hell let loose", "arma", "battlefield"]):
        facets.update({"fps", "large_scale_war", "pvp"})
        facets -= {"battle_royale", "tactical_round"}

    if "online pvp" in cats_l:
        facets.add("pvp")
    if "online co-op" in cats_l:
        facets.add("coop")

    return facets


def _extract_franchise_prefix(name: str) -> str:
    clean = re.sub(r"[™®:]", "", str(name).lower()).strip()
    words = [w for w in clean.split() if w not in {"the", "a", "an"}]
    if len(words) >= 2 and f"{words[0]} {words[1]}" in {
        "grand theft", "call of", "elder scrolls", "red dead", "watch dogs",
        "saints row", "just cause", "half life", "half-life", "team fortress",
        "left 4", "dark souls", "resident evil", "street fighter",
        "mortal kombat", "age of", "total war", "sid meier's", "company of",
    }:
        return f"{words[0]} {words[1]}"
    return words[0] if words else clean


def _build_semantic_document(row: pd.Series, facets: Set[str]) -> str:
    tags = [t.strip().lower() for t in str(row.get("tags", "")).split("|") if t.strip()]
    genres = [g.strip().lower() for g in str(row.get("genres", "")).split("|") if g.strip()]
    cats = [
        c.strip().lower()
        for c in str(row.get("categories", "")).split("|")
        if c.strip() and c.strip().lower() not in PLATFORM_NOISE
    ]
    desc = str(row.get("short_description", "")).lower()

    facet_tokens = [f"facet_{f}" for f in facets for _ in range(4)]
    tag_tokens = [re.sub(r"[^a-z0-9]+", "_", t) for t in tags for _ in range(3)]
    genre_tokens = [re.sub(r"[^a-z0-9]+", "_", g) for g in genres for _ in range(2)]
    cat_tokens = [re.sub(r"[^a-z0-9]+", "_", c) for c in cats]
    return " ".join(facet_tokens + tag_tokens + genre_tokens + cat_tokens) + " " + desc


@st.cache_resource(show_spinner=False)
def _get_cached_semantic_space(catalog_sig: Tuple[int, int], _df: pd.DataFrame) -> Tuple[List[Set[str]], np.ndarray]:
    """Builds and caches the 128-D TruncatedSVD embedding matrix once in memory for sub-20ms queries."""
    working = _df.reset_index(drop=True)
    facets_list = [extract_structured_facets(row) for _, row in working.iterrows()]
    docs = [_build_semantic_document(working.iloc[i], facets_list[i]) for i in range(len(working))]

    vectorizer = TfidfVectorizer(stop_words="english", max_features=3000, ngram_range=(1, 2), sublinear_tf=True)
    tfidf_matrix = vectorizer.fit_transform(docs)

    n_samples, n_features = tfidf_matrix.shape
    n_components = min(128, n_samples - 1, n_features - 1)
    if n_components >= 2:
        svd = TruncatedSVD(n_components=n_components, random_state=42)
        dense_embeddings = normalize(svd.fit_transform(tfidf_matrix), norm="l2").astype(np.float32)
    else:
        dense_embeddings = normalize(tfidf_matrix, norm="l2").toarray().astype(np.float32)

    return facets_list, dense_embeddings


def engineer_gem_metrics(df: pd.DataFrame, live_top_ids: List[int] = None) -> pd.DataFrame:
    data = df.copy()
    live_top_ids = set(live_top_ids or [])

    data["release_dt"] = pd.to_datetime(data["release_date"], errors="coerce")
    data = data.dropna(subset=["release_dt"]).copy()
    data["release_year"] = data["release_dt"].dt.year
    data["positive_reviews"] = pd.to_numeric(data["positive_reviews"], errors="coerce").fillna(0).astype(int)
    data["total_reviews"] = pd.to_numeric(data["total_reviews"], errors="coerce").fillna(1).clip(lower=1).astype(int)
    data["negative_reviews"] = (data["total_reviews"] - data["positive_reviews"]).clip(lower=0).astype(int)
    data["price_usd"] = pd.to_numeric(data["price_usd"], errors="coerce").fillna(0.0).clip(lower=0.0)
    data["discount_pct"] = pd.to_numeric(data.get("discount_pct", 0), errors="coerce").fillna(0).astype(int)
    data["avg_playtime_hrs"] = pd.to_numeric(data.get("avg_playtime_hrs", 0.0), errors="coerce").fillna(0.0)
    data["peak_ccu"] = pd.to_numeric(data.get("peak_ccu", 0), errors="coerce").fillna(0).astype(int)

    for col in ["genres", "tags", "categories", "developers", "publishers", "short_description", "header_image", "stores"]:
        if col not in data.columns:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str)

    if "is_free" not in data.columns:
        data["is_free"] = (data["price_usd"] == 0.0) & (
            data["genres"].str.contains("Free To Play", case=False, na=False)
            | data["tags"].str.contains("Free to Play", case=False, na=False)
        )
    else:
        data["is_free"] = data["is_free"].fillna(False).astype(bool)

    data["is_demo_teaser"] = data["name"].str.contains(
        r"\b(?:prologue|demo|playtest|trial|teaser|benchmark)\b", case=False, regex=True
    )

    cats_lower = data["categories"].str.lower()
    data["has_singleplayer"] = cats_lower.str.contains("single-player", na=False)
    data["has_online_mp"] = cats_lower.str.contains(
        "online pvp|online co-op|mmo|cross-platform multiplayer", regex=True, na=False
    )
    data["has_online_pvp"] = cats_lower.str.contains("online pvp", na=False)
    data["is_mp_only"] = data["has_online_mp"] & (~data["has_singleplayer"])

    data["positive_pct"] = ((data["positive_reviews"] / data["total_reviews"]) * 100.0).round(1)
    data["wilson_score"] = compute_wilson_score(data["positive_reviews"], data["total_reviews"])

    data["is_aaa_blockbuster"] = (
        (data["total_reviews"] >= 220000)
        | ((data["total_reviews"] >= 95000) & (data["price_usd"] >= 49.99))
        | (data["appid"].isin(list(live_top_ids)[:12]) & (data["total_reviews"] >= 95000))
    )

    blockbusters = data[data["is_aaa_blockbuster"]][["appid", "name", "release_dt", "total_reviews"]].copy()

    shadow_scores = np.zeros(len(data), dtype=float)
    culprit_names: List[str] = ["None"] * len(data)
    culprit_offsets: List[int] = [999] * len(data)

    if not blockbusters.empty:
        bb_dates = blockbusters["release_dt"].values.astype("datetime64[D]").astype(np.int64)
        bb_weights = np.log10(blockbusters["total_reviews"].values.clip(min=1000))
        bb_names = blockbusters["name"].values
        bb_ids = blockbusters["appid"].values

        game_dates = data["release_dt"].values.astype("datetime64[D]").astype(np.int64)
        game_ids = data["appid"].values
        game_is_aaa = data["is_aaa_blockbuster"].values

        sigma = 5.0
        for i in range(len(data)):
            if game_is_aaa[i]:
                continue
            day_diffs = game_dates[i] - bb_dates
            mask = (np.abs(day_diffs) <= 14) & (bb_ids != game_ids[i])
            if np.any(mask):
                valid_diffs = day_diffs[mask]
                valid_weights = bb_weights[mask]
                valid_names = bb_names[mask]

                impacts = valid_weights * np.exp(-(valid_diffs ** 2) / (2.0 * sigma ** 2))
                shadow_scores[i] = float(np.sum(impacts))

                best_idx = int(np.argmax(impacts))
                culprit_names[i] = str(valid_names[best_idx])
                culprit_offsets[i] = int(valid_diffs[best_idx])

    max_shadow = float(np.percentile(shadow_scores[shadow_scores > 0], 98)) if np.any(shadow_scores > 0) else 1.0
    data["aaa_shadow_score"] = np.clip((shadow_scores / max(max_shadow, 1e-6)) * 100.0, 0.0, 100.0).round(1)
    data["shadow_culprit"] = culprit_names
    data["shadow_day_offset"] = culprit_offsets

    log_rev = np.log10(data["total_reviews"].clip(lower=10))
    discovery_gap = 100.0 * np.exp(-((log_rev - 3.05) ** 2) / (2.0 * 0.85 ** 2))
    discovery_gap = np.where(data["is_aaa_blockbuster"], discovery_gap * 0.1, discovery_gap)
    data["obscurity_score"] = discovery_gap.round(1)

    effective_price = data["price_usd"] * (1.0 - data["discount_pct"] / 100.0)
    data["effective_price_usd"] = effective_price.round(2)
    playtime_boost = np.clip(np.log1p(data["avg_playtime_hrs"]) / 3.2, 0.45, 1.25)
    value_raw = (data["wilson_score"] / 100.0) * playtime_boost * (1.0 / np.log1p(effective_price + 2.0))
    v_min, v_max = float(value_raw.min()), float(value_raw.max())
    base_value = ((value_raw - v_min) / (v_max - v_min)) * 100.0 if v_max > v_min else 50.0
    mp_penalty = np.where(data["is_mp_only"] & (data["peak_ccu"] < 15), 0.5, 1.0)
    data["value_score"] = (base_value * mp_penalty).round(1)

    raw_hgi = (
        0.42 * data["wilson_score"]
        + 0.26 * data["obscurity_score"]
        + 0.20 * data["aaa_shadow_score"]
        + 0.12 * data["value_score"]
    )
    raw_hgi = np.where(data["is_demo_teaser"], raw_hgi * 0.65, raw_hgi)
    raw_hgi = np.where(data["is_mp_only"] & (data["peak_ccu"] < 15), raw_hgi * 0.70, raw_hgi)
    data["hidden_gem_index"] = np.clip(raw_hgi, 0.0, 100.0).round(1)

    stories = []
    for _, row in data.iterrows():
        if row["is_aaa_blockbuster"]:
            stories.append("AAA Blockbuster Gravity Well")
        elif row["shadow_culprit"] != "None" and row["aaa_shadow_score"] >= 20:
            offset = int(row["shadow_day_offset"])
            if offset == 0:
                timing = "the exact same day as"
            elif offset > 0:
                timing = f"{offset} day{'s' if offset > 1 else ''} after"
            else:
                timing = f"{abs(offset)} day{'s' if abs(offset) > 1 else ''} before"
            stories.append(
                f"Released {timing} {row['shadow_culprit']} — overshadowed despite {row['positive_pct']:.0f}% positive reviews."
            )
        else:
            stories.append(
                f"Under-discovered standout ({row['total_reviews']:,} reviews) with {row['wilson_score']:.1f}% buyer consensus."
            )
    data["shadow_story"] = stories
    return data


def prepare_clean_export_df(df: pd.DataFrame) -> pd.DataFrame:
    clean = df[~df["is_demo_teaser"]].drop_duplicates(subset=["appid"]).copy()
    clean["clean_description"] = clean["short_description"].apply(
        lambda s: " ".join(re.sub(r"<[^>]+>", " ", str(s)).split())
    )
    clean["day_offset_from_aaa"] = clean["shadow_day_offset"].apply(
        lambda d: int(d) if int(d) != 999 else pd.NA
    )
    clean["segment"] = np.where(clean["is_aaa_blockbuster"], "AAA_Blockbuster", "Catalog_Title")

    export_df = pd.DataFrame(
        {
            "app_id": clean["appid"].astype(int),
            "title": clean["name"].str.strip(),
            "segment": clean["segment"],
            "pc_storefronts": clean["stores"].replace("", "Steam"),
            "release_date": clean["release_date"],
            "release_year": clean["release_year"].astype(int),
            "base_price_usd": clean["price_usd"].round(2),
            "effective_price_usd": clean["effective_price_usd"].round(2),
            "is_free_to_play": clean["is_free"].astype(bool),
            "positive_reviews": clean["positive_reviews"].astype(int),
            "negative_reviews": clean["negative_reviews"].astype(int),
            "total_reviews": clean["total_reviews"].astype(int),
            "positive_ratio_pct": clean["positive_pct"].round(1),
            "wilson_quality_score": clean["wilson_score"].round(2),
            "discovery_gap_score": clean["obscurity_score"].round(1),
            "aaa_shadow_score": clean["aaa_shadow_score"].round(1),
            "eclipsing_aaa_title": clean["shadow_culprit"],
            "day_offset_from_aaa": clean["day_offset_from_aaa"],
            "value_engagement_score": clean["value_score"].round(1),
            "hidden_gem_index": clean["hidden_gem_index"].round(1),
            "avg_playtime_hrs": clean["avg_playtime_hrs"].round(1),
            "peak_concurrent_players": clean["peak_ccu"].astype(int),
            "genres": clean["genres"],
            "tags": clean["tags"],
            "developers": clean["developers"].replace("", "Unknown"),
            "publishers": clean["publishers"].replace("", "Unknown"),
            "clean_description": clean["clean_description"],
        }
    ).sort_values("hidden_gem_index", ascending=False).reset_index(drop=True)

    return export_df


def format_shadow_event(row: pd.Series) -> str:
    if row["shadow_culprit"] == "None" or row["aaa_shadow_score"] < 20:
        return "Under-Discovered Gem"
    offset = int(row["shadow_day_offset"])
    if offset == 0:
        return f"Same day as {row['shadow_culprit']}"
    if offset > 0:
        return f"+{offset}d after {row['shadow_culprit']}"
    return f"{abs(offset)}d before {row['shadow_culprit']}"


def _compute_2d_gameplay_coords(row: pd.Series, facets: Set[str]) -> Tuple[float, float]:
    playtime = float(row.get("avg_playtime_hrs", 15.0))
    playtime_norm = min(35.0, np.log1p(playtime) * 6.5)

    tactical = 32.0 + playtime_norm * 0.65
    if facets & {"tactical_round", "ballistics", "strategy", "crpg", "builder_sim", "extraction"}:
        tactical += 26.0
    if facets & {"abilities", "survival", "large_scale_war"}:
        tactical += 12.0

    mechanical = 30.0 + playtime_norm * 0.70
    if facets & {"high_mobility", "soulslike", "fighting", "melee", "fps", "battle_royale"}:
        mechanical += 24.0
    if facets & {"tactical_round", "hero_arena"}:
        mechanical += 14.0

    return round(min(98.0, tactical), 1), round(min(98.0, mechanical), 1)


def _classify_diagnostic_tier(
    row: pd.Series, cand_facets: Set[str], anchor_facets: Set[str]
) -> str:
    revs = int(row.get("total_reviews", 0))
    playtime = float(row.get("avg_playtime_hrs", 0.0))

    if revs < 35000 and not bool(row.get("is_aaa_blockbuster", False)):
        return "💎 Underrated Gems"

    if "battle_royale" in anchor_facets:
        if cand_facets & {"high_mobility", "abilities", "melee"}:
            return "⚡ Faster / High-Mobility"
        if cand_facets & {"ballistics", "survival"}:
            return "🧠 More Tactical"
        return "🎯 Closest Direct"

    if "tactical_round" in anchor_facets:
        if any(k in str(row.get("name", "")).lower() for k in ["rainbow six", "zero hour", "due process", "insurgency"]):
            return "🧠 More Tactical"
        if playtime >= 85.0 or "ballistics" in cand_facets:
            return "⚡ Higher Skill Ceiling"
        return "🎯 Closest Direct"

    if cand_facets & {"strategy", "builder_sim", "crpg", "survival", "ballistics"}:
        return "🧠 More Tactical"
    if cand_facets & {"soulslike", "high_mobility", "fighting", "melee"} or playtime >= 75.0:
        return "⚡ Higher Skill Ceiling"
    return "🎯 Closest Direct"


def _build_evaluation_card_data(
    anchor_row: pd.Series,
    cand_row: pd.Series,
    anchor_facets: Set[str],
    cand_facets: Set[str],
) -> Dict[str, str]:
    a_name = str(anchor_row["name"])

    shared = [FACET_LABELS[f] for f in sorted(anchor_facets & cand_facets) if f in FACET_LABELS]
    unique_cand = [FACET_LABELS[f] for f in sorted(cand_facets - anchor_facets) if f in FACET_LABELS]
    unique_anchor = [FACET_LABELS[f] for f in sorted(anchor_facets - cand_facets) if f in FACET_LABELS]

    cand_tags = [t.strip() for t in str(cand_row.get("tags", "")).split("|") if t.strip()]
    cand_cats = [c.strip() for c in str(cand_row.get("categories", "")).split("|") if c.strip() and c.strip().lower() not in PLATFORM_NOISE]
    stores = [s.strip() for s in str(cand_row.get("stores", "Steam")).split("|") if s.strip()]

    shared_str = ", ".join(shared[:3]) if shared else ", ".join(cand_tags[:3])
    preserves = f"{shared_str} with {a_name}'s core competitive loop."

    if unique_cand and unique_anchor:
        tradeoff = f"Adds {', '.join(unique_cand[:2])}; drops {a_name}'s {', '.join(unique_anchor[:2])}."
    elif unique_cand:
        tradeoff = f"Layers in {', '.join(unique_cand[:2])} mechanics."
    else:
        tradeoff = f"Different pacing, map flow, and progression vs. {a_name}."

    if "ballistics" in cand_facets:
        gunplay = "Punishing TTK, bullet drop/recoil control, ballistic penetration, and disciplined cover positioning."
    elif "high_mobility" in cand_facets:
        gunplay = "High-velocity traversal, tracking-heavy recoil control, vertical movement tech, and fast target switching."
    elif "tactical_round" in cand_facets:
        gunplay = "High first-shot precision, lethal headshots, movement inaccuracy penalties, and spray/burst discipline."
    elif cand_facets & {"melee", "soulslike"}:
        gunplay = "Frame-tight melee hitboxes, stamina economy, parry/dodge windows, and deliberate spacing."
    elif cand_facets & {"crpg", "strategy"}:
        gunplay = "Tactical positioning, action-economy optimization, line-of-sight control, and ability synergies."
    else:
        gunplay = f"Responsive combat & handling centered on {', '.join(cand_tags[:3]) or 'core mechanics'}."

    modes_str = ", ".join(cand_cats[:3]) if cand_cats else "Structured competitive & objective modes"
    if "battle_royale" in cand_facets:
        comp_structure = f"Last-squad-standing Battle Royale with shrinking safe zones, scavenging, and {modes_str}."
    elif "tactical_round" in cand_facets:
        comp_structure = f"Round-based attack/defense objective structure with economy/loadouts and {modes_str}."
    else:
        comp_structure = f"Structured match/campaign progression featuring {modes_str}."

    tactical_depth = f"Rewards map knowledge, positioning, utility timing, and coordinated execution ({', '.join(cand_tags[:3]) or 'tactical play'})."

    avg_hrs = float(cand_row.get("avg_playtime_hrs", 0.0))
    skill_ceiling = (
        f"High long-term mastery curve (players average {max(avg_hrs, 14.0):.0f} hrs) with deep mechanical and macro optimization."
    )

    revs = int(cand_row.get("total_reviews", 0))
    wilson = float(cand_row.get("wilson_score", 0.0))
    player_base = f"{wilson:.1f}% buyer consensus across {revs:,} verified reviews on {', '.join(stores)}."

    accessibility = f"Natural transition for {a_name} players already comfortable with positioning, spacing, and objective tempo."

    eff_p = float(cand_row.get("effective_price_usd", cand_row.get("price_usd", 0.0)))
    price_lbl = "Free to Play ($0.00)" if eff_p == 0 else f"${eff_p:.2f} USD"
    value = f"{price_lbl} across {', '.join(stores)}."

    return {
        "preserves": preserves,
        "tradeoff": tradeoff,
        "gunplay": gunplay,
        "comp_structure": comp_structure,
        "tactical_depth": tactical_depth,
        "skill_ceiling": skill_ceiling,
        "player_base": player_base,
        "accessibility": accessibility,
        "value": value,
    }


def build_dna_recommender(
    df: pd.DataFrame,
    anchor_name: str,
    top_k: int = 12,
    require_mp: bool = False,
    max_price: float = 200.0,
    store_filter: str = "All PC Launchers",
    hide_mega_blockbusters: bool = False,
) -> Tuple[pd.Series, pd.DataFrame]:
    working = df.reset_index(drop=True)
    sig = (len(working), int(working["appid"].sum()))
    facets_list, dense_embeddings = _get_cached_semantic_space(sig, working)

    matching_idx = working[working["name"] == anchor_name].index
    anchor_pos = int(matching_idx[0]) if len(matching_idx) > 0 else 0
    anchor_row = working.loc[anchor_pos]
    anchor_facets: Set[str] = facets_list[anchor_pos]
    anchor_tags_l = str(anchor_row.get("tags", "")).lower()
    anchor_franchise = _extract_franchise_prefix(anchor_row["name"])

    semantic_sims = dense_embeddings @ dense_embeddings[anchor_pos]

    core_loops = {
        "fps", "tps", "tactical_round", "battle_royale", "extraction",
        "large_scale_war", "hero_arena", "open_world", "crime", "driving",
        "shmup_2d", "melee", "fighting", "soulslike", "rpg", "crpg",
        "roguelike", "strategy", "builder_sim", "survival", "horror",
        "platformer_2d", "casual_party",
    }
    anchor_core = anchor_facets & core_loops
    anchor_is_casual = "casual_party" in anchor_facets
    anchor_is_tactical_round = ("tactical_round" in anchor_facets) and ("fps" in anchor_facets)
    anchor_is_br = "battle_royale" in anchor_facets
    anchor_is_extraction = "extraction" in anchor_facets
    anchor_is_hero_arena = "hero_arena" in anchor_facets
    anchor_is_large_war = "large_scale_war" in anchor_facets
    anchor_is_3d_shooter = bool(anchor_core & {"fps", "tps", "battle_royale"})
    anchor_is_3d_open_world = bool(anchor_core & {"open_world", "crime"}) and not anchor_is_casual and not anchor_is_br
    anchor_is_2d = bool(anchor_core & {"shmup_2d", "platformer_2d"}) or ("2d" in anchor_tags_l and not anchor_is_3d_shooter)
    anchor_is_comp_mp = ("pvp" in anchor_facets) and (
        not bool(anchor_row.get("has_singleplayer", True))
        or bool(anchor_core & {"battle_royale", "hero_arena", "tactical_round", "extraction"})
    )

    min_quality = 62.0 if anchor_is_comp_mp else 72.0

    # Fast pre-filtering before row evaluation
    mask = (
        (working["name"] != anchor_row["name"])
        & (~working["is_demo_teaser"])
        & (working["wilson_score"] >= min_quality)
        & (working["effective_price_usd"] <= max_price)
        & (semantic_sims >= 0.08)
    )
    if hide_mega_blockbusters:
        mask &= ~working["is_aaa_blockbuster"]
    if store_filter != "All PC Launchers":
        mask &= working["stores"].str.contains(store_filter, case=False, na=False)
    if require_mp:
        mask &= working["has_online_mp"]

    candidate_indices = working.index[mask].tolist()

    valid_rows = []
    for i in candidate_indices:
        row = working.iloc[i]
        if len(anchor_franchise) >= 4 and _extract_franchise_prefix(row["name"]) == anchor_franchise:
            continue

        cand_facets: Set[str] = facets_list[i]
        cand_core = cand_facets & core_loops
        cand_tags_l = str(row.get("tags", "")).lower()
        cand_genres_l = str(row.get("genres", "")).lower()

        if not anchor_is_casual and ("casual_party" in cand_facets or "casual" in cand_genres_l):
            continue

        cand_is_2d = bool(cand_core & {"shmup_2d", "platformer_2d"}) or ("2d" in cand_tags_l and not bool(cand_core & {"fps", "tps", "battle_royale"}))
        if (anchor_is_3d_shooter or anchor_is_3d_open_world) and cand_is_2d:
            continue
        if anchor_is_2d and bool(cand_core & {"fps", "tps", "battle_royale"}):
            continue

        if anchor_is_tactical_round:
            if bool(cand_facets & {"battle_royale", "extraction", "large_scale_war", "hero_arena", "open_world", "retro_boomer"}) or "fps" not in cand_facets or "tactical_round" not in cand_facets:
                continue

        if anchor_is_br:
            if "battle_royale" not in cand_facets or bool(cand_facets & {"tactical_round", "large_scale_war", "hero_arena", "retro_boomer"}):
                continue

        if anchor_is_extraction and "extraction" not in cand_facets:
            continue

        if anchor_is_hero_arena:
            if "hero_arena" not in cand_facets and not ("abilities" in cand_facets and "pvp" in cand_facets and "battle_royale" not in cand_facets and "tactical_round" not in cand_facets):
                continue

        if anchor_is_large_war and "large_scale_war" not in cand_facets:
            continue

        if anchor_is_comp_mp and not bool(row.get("has_online_mp", False)) and "pvp" not in cand_facets:
            continue

        if anchor_is_3d_open_world:
            if ("action" not in cand_genres_l and "adventure" not in cand_genres_l) or not bool(cand_core & {"open_world", "crime", "tps", "fps", "driving"}):
                continue

        if anchor_core and not (anchor_core & cand_core):
            continue

        union_all = anchor_facets | cand_facets
        jaccard = (len(anchor_facets & cand_facets) / len(union_all)) if union_all else 0.0
        sem_sim = max(0.0, float(semantic_sims[i]))
        blended = (0.62 * sem_sim + 0.38 * jaccard) * 100.0
        display_match = round(min(98.5, 58.0 + blended * 0.62), 1)

        overlap_all = sorted(anchor_facets & cand_facets)
        nice_tags = [FACET_LABELS[f] for f in overlap_all if f in FACET_LABELS][:3]
        t_c, m_c = _compute_2d_gameplay_coords(row, cand_facets)

        rec = row.to_dict()
        rec["dna_similarity"] = display_match
        rec["shared_traits"] = " • ".join(nice_tags) if nice_tags else "Latent Gameplay DNA"
        rec["diagnostic_tier"] = _classify_diagnostic_tier(row, cand_facets, anchor_facets)
        rec["eval_9point"] = _build_evaluation_card_data(anchor_row, row, anchor_facets, cand_facets)
        rec["tactical_depth_coord"] = t_c
        rec["mechanical_intensity_coord"] = m_c
        rec["match_rank_score"] = 0.85 * display_match + 0.15 * float(row["hidden_gem_index"])
        valid_rows.append(rec)

    a_tac, a_mech = _compute_2d_gameplay_coords(anchor_row, anchor_facets)
    anchor_out = anchor_row.copy()
    anchor_out["tactical_depth_coord"] = a_tac
    anchor_out["mechanical_intensity_coord"] = a_mech

    if not valid_rows:
        return anchor_out, pd.DataFrame()

    candidates = pd.DataFrame(valid_rows).sort_values("match_rank_score", ascending=False).head(top_k).reset_index(drop=True)
    return anchor_out, candidates


def compute_5axis_dna(row: pd.Series) -> Dict[str, float]:
    facets = extract_structured_facets(row)

    def axis_val(target_set: Set[str], base: float = 20.0) -> float:
        hits = len(facets & target_set)
        return float(min(100.0, base + hits * 26.0))

    return {
        "Gunplay & Combat": axis_val({"fps", "tps", "tactical_round", "melee", "fighting"}),
        "Multiplayer & PvP": axis_val({"pvp", "coop", "battle_royale", "hero_arena", "extraction"}),
        "Open World & Survival": axis_val({"open_world", "crime", "driving", "survival", "battle_royale"}),
        "Story & Immersion": axis_val({"rpg", "crpg", "soulslike", "horror"}),
        "Tactics & Systems": axis_val({"strategy", "builder_sim", "roguelike", "platformer_2d", "tactical_round"}),
    }