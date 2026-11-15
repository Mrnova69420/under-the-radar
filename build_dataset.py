"""
build_dataset.py
Builds a comprehensive ~25,000-game Steam catalog with user-defined tags,
average playtime, peak CCU, and accurate Free-to-Play classification.
"""

import argparse
import os
import pandas as pd
import requests

HF_PARQUET_API = "https://datasets-server.huggingface.co/parquet?dataset=FronkonGames/steam-games-dataset"


def flatten_list_col(val) -> str:
    if isinstance(val, dict):
        return "|".join([str(k).strip() for k in val.keys() if str(k).strip()])
    if isinstance(val, (list, tuple)):
        return "|".join([str(x).strip() for x in val if str(x).strip()])
    if hasattr(val, "tolist"):
        return "|".join([str(x).strip() for x in val.tolist() if str(x).strip()])
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def build_catalog(target: int = 25000, min_reviews: int = 40, out_path: str = "data/steam_catalog.csv") -> int:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    print("Fetching dataset index from Hugging Face...", flush=True)
    meta = requests.get(HF_PARQUET_API, timeout=15).json()
    parquet_urls = [f["url"] for f in meta.get("parquet_files", []) if f.get("split") == "train"]

    if not parquet_urls:
        raise RuntimeError("Could not locate Parquet files for FronkonGames/steam-games-dataset.")

    frames = []
    for idx, url in enumerate(parquet_urls, start=1):
        print(f"Downloading & filtering partition {idx}/{len(parquet_urls)}...", flush=True)
        part = pd.read_parquet(url)

        part["positive_reviews"] = pd.to_numeric(part["positive"], errors="coerce").fillna(0).astype(int)
        part["negative_reviews"] = pd.to_numeric(part["negative"], errors="coerce").fillna(0).astype(int)
        part["total_reviews"] = part["positive_reviews"] + part["negative_reviews"]
        part = part[part["total_reviews"] >= min_reviews].copy()
        frames.append(part)

    raw = pd.concat(frames, ignore_index=True)
    print(f"Found {len(raw):,} real Steam games with >= {min_reviews} reviews.", flush=True)

    raw["parsed_dt"] = pd.to_datetime(raw["release_date"], errors="coerce")
    raw = raw.dropna(subset=["parsed_dt"]).copy()
    raw = raw.sort_values("total_reviews", ascending=False).head(target).copy()

    appid_col = raw["appID"] if "appID" in raw.columns else raw["appid"]
    genres_str = raw["genres"].apply(flatten_list_col)
    tags_str = raw["tags"].apply(flatten_list_col) if "tags" in raw.columns else pd.Series([""] * len(raw), index=raw.index)
    price_num = pd.to_numeric(raw["price"], errors="coerce").fillna(0.0).round(2)

    is_f2p = (price_num == 0.0) & (
        genres_str.str.contains("Free To Play", case=False, na=False)
        | tags_str.str.contains("Free to Play", case=False, na=False)
    )

    clean_df = pd.DataFrame(
        {
            "appid": pd.to_numeric(appid_col, errors="coerce").fillna(0).astype(int),
            "name": raw["name"].astype(str).str.strip(),
            "release_date": raw["parsed_dt"].dt.strftime("%Y-%m-%d"),
            "release_year": raw["parsed_dt"].dt.year.astype(int),
            "price_usd": price_num,
            "discount_pct": 0,
            "is_free": is_f2p,
            "positive_reviews": raw["positive_reviews"],
            "negative_reviews": raw["negative_reviews"],
            "total_reviews": raw["total_reviews"],
            "avg_playtime_hrs": (pd.to_numeric(raw.get("average_playtime_forever", 0), errors="coerce").fillna(0) / 60.0).round(1),
            "peak_ccu": pd.to_numeric(raw.get("peak_ccu", 0), errors="coerce").fillna(0).astype(int),
            "metacritic_score": pd.to_numeric(raw.get("metacritic_score", 0), errors="coerce").replace(0, pd.NA),
            "genres": genres_str,
            "tags": tags_str,
            "categories": raw["categories"].apply(flatten_list_col),
            "developers": raw["developers"].apply(flatten_list_col),
            "publishers": raw["publishers"].apply(flatten_list_col),
            "short_description": raw["short_description"].fillna("").astype(str).str.replace("\n", " ", regex=False).str.strip(),
            "header_image": raw["header_image"].fillna("").astype(str).str.strip(),
        }
    )

    clean_df = clean_df[clean_df["appid"] > 0].drop_duplicates(subset=["appid"])
    clean_df.to_csv(out_path, index=False)
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"\nDone! Saved {len(clean_df):,} real Steam games ({size_mb:.2f} MB) to {out_path}.", flush=True)
    return len(clean_df)


def main():
    parser = argparse.ArgumentParser(description="Build 25k real Steam catalog CSV.")
    parser.add_argument("--target", type=int, default=25000, help="Max reviewed games to keep.")
    parser.add_argument("--min-reviews", type=int, default=40, help="Minimum buyer reviews.")
    parser.add_argument("--out", type=str, default="data/steam_catalog.csv", help="Output CSV path.")
    args = parser.parse_args()
    build_catalog(target=args.target, min_reviews=args.min_reviews, out_path=args.out)


if __name__ == "__main__":
    main()