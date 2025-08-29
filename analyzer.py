# analyzer.py
"""
Analyzer that picks the best bus entirely offline.

New behavior:
 - Prefers buses whose DROPPING TIME lies in [06:30, 09:00] (ideal window).
 - If at least one bus is inside that window, those buses get highest drop_score.
 - If none are inside the window, the algorithm prefers earliest dropping time.
 - Combined with other factors (price, rating, window seats, seats, duration).
 - Returns the best pandas Series row (with Booking Link available if scraped).
"""

import re
from typing import Optional, Dict
import pandas as pd
import math

# --- parsing helpers (same as before) ---
def _to_int(x) -> Optional[int]:
    if pd.isna(x):
        return None
    m = re.search(r'(\d[\d,]*)', str(x))
    if not m:
        return None
    try:
        return int(m.group(1).replace(',', ''))
    except:
        return None

def _to_float_rating(x) -> Optional[float]:
    if pd.isna(x):
        return None
    s = str(x)
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except:
        return None

def _time_to_minutes(t: str) -> Optional[int]:
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return None
    s = str(t).strip()
    if not s:
        return None
    s = s.upper().replace('.', '')
    # Try formats: "06:30 PM", "6:30PM", "18:30", "6:30"
    m = re.match(r'^\s*(\d{1,2})\s*[:\-]\s*(\d{2})\s*(AM|PM)?\s*$', s)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2)); ampm = (m.group(3) or "").strip()
        if ampm == "PM" and hh != 12:
            hh += 12
        if ampm == "AM" and hh == 12:
            hh = 0
        return hh*60 + mm
    m2 = re.match(r'^\s*(\d{1,2})\s*(AM|PM)\s*$', s)
    if m2:
        hh = int(m2.group(1)); mm = 0; ampm = m2.group(2)
        if ampm == "PM" and hh != 12:
            hh += 12
        if ampm == "AM" and hh == 12:
            hh = 0
        return hh*60 + mm
    # fallback '0630' or '1830'
    m3 = re.match(r'^\s*(\d{2})(\d{2})\s*$', s)
    if m3:
        hh = int(m3.group(1)); mm = int(m3.group(2))
        return hh*60 + mm
    return None

def _duration_to_minutes(d: str) -> Optional[int]:
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return None
    s = str(d).strip().lower()
    if not s:
        return None
    h = 0; m = 0
    mh = re.search(r'(\d+)\s*h', s)
    mm = re.search(r'(\d+)\s*m', s)
    if mh: h = int(mh.group(1))
    if mm: m = int(mm.group(1))
    if mh or mm:
        return h*60 + m
    # fallback '10:30'
    m2 = re.match(r'^(\d{1,2})[:\-](\d{2})$', s)
    if m2:
        return int(m2.group(1))*60 + int(m2.group(2))
    m3 = re.search(r'(\d+)', s)
    if m3:
        val = int(m3.group(1))
        if val <= 24:
            return val*60
        return val
    return None

# normalization helper
def _normalize_series(s: pd.Series, invert: bool = False) -> pd.Series:
    s2 = s.astype(float)
    if s2.isnull().all():
        return pd.Series([0.5]*len(s2), index=s2.index)
    mn = s2.min(skipna=True); mx = s2.max(skipna=True)
    if mx == mn:
        return pd.Series([0.5]*len(s2), index=s2.index)
    norm = (s2 - mn) / (mx - mn)
    if invert:
        norm = 1.0 - norm
    return norm.clip(0.0, 1.0).fillna(0.5)

def pick_best_bus(csv_path: str, weights: Optional[Dict[str, float]] = None, verbose: bool = True):
    # default weights (price most important, rating next)
    default_weights = {
        "price": 3.0,
        "rating": 2.0,
        "window": 1.0,
        "seats": 0.6,
        "duration": 1.0,
        "boarding": 0.2,
        "dropping_pref": 1.1   # new metric weight for preferred dropping window
    }
    if weights is None:
        weights = default_weights
    else:
        merged = default_weights.copy()
        merged.update(weights)
        weights = merged

    df = pd.read_csv(csv_path)
    if df.empty:
        if verbose:
            print("[analyzer] CSV empty.")
        return None

    # Ensure columns exist
    for c in ["Price", "Rating", "Window Seats", "Seats Available", "Boarding Time", "Duration", "Dropping Time"]:
        if c not in df.columns:
            df[c] = None

    # parse numeric / time fields
    df["_price"] = df["Price"].apply(_to_int)
    df["_rating"] = df["Rating"].apply(_to_float_rating)
    df["_window"] = df["Window Seats"].apply(_to_int)
    df["_seats"] = df["Seats Available"].apply(_to_int)
    df["_board_mins"] = df["Boarding Time"].apply(_time_to_minutes)
    df["_dur_mins"] = df["Duration"].apply(_duration_to_minutes)
    df["_drop_mins"] = df["Dropping Time"].apply(_time_to_minutes)

    # fill missing with conservative defaults
    max_price = df["_price"].max(skipna=True)
    if pd.isna(max_price): max_price = 999999
    df["_price"] = df["_price"].fillna(max_price * 1.5)

    if df["_rating"].isnull().all():
        df["_rating"] = df["_rating"].fillna(0.0)
    else:
        df["_rating"] = df["_rating"].fillna(df["_rating"].min(skipna=True))

    df["_window"] = df["_window"].fillna(0)
    df["_seats"] = df["_seats"].fillna(0)

    max_dur = df["_dur_mins"].max(skipna=True)
    if pd.isna(max_dur): max_dur = 9999
    df["_dur_mins"] = df["_dur_mins"].fillna(max_dur * 1.5)

    max_board = df["_board_mins"].max(skipna=True)
    if pd.isna(max_board): max_board = 24*60
    df["_board_mins"] = df["_board_mins"].fillna(max_board + 60)

    # ---- dropping preference metric ----
    # ideal window [06:30, 09:00] -> [390, 540]
    IDEAL_START = 6*60 + 30
    IDEAL_END = 9*60

    has_in_window = df["_drop_mins"].apply(lambda x: x is not None and IDEAL_START <= x <= IDEAL_END).any()

    if has_in_window:
        # Score by closeness to window (1.0 for inside window)
        def drop_score_val(x):
            if x is None:
                return 0.0
            if IDEAL_START <= x <= IDEAL_END:
                return 1.0
            # distance to nearest boundary
            dist = min(abs(x - IDEAL_START), abs(x - IDEAL_END))
            # scale distance: larger distance -> lower score. denom picks sensitivity (720 min -> smooth)
            return max(0.0, 1.0 - (dist / 720.0))
        df["_drop_pref"] = df["_drop_mins"].apply(drop_score_val)
    else:
        # prefer earliest dropping time -> transform drop_mins so earlier = higher score
        # invert normalized drop_mins (smaller drop_mins -> larger score)
        # use normalization
        drop_vals = df["_drop_mins"].copy()
        # missing -> set to large so they are worst
        max_d = drop_vals.max(skipna=True)
        if pd.isna(max_d): max_d = 24*60
        drop_vals = drop_vals.fillna(max_d + 120)
        df["_drop_pref"] = _normalize_series(drop_vals, invert=True)

    # ---- normalize other metrics ----
    price_norm = _normalize_series(df["_price"], invert=True)
    rating_norm = _normalize_series(df["_rating"], invert=False)
    window_norm = _normalize_series(df["_window"], invert=False)
    seats_norm = _normalize_series(df["_seats"], invert=False)
    dur_norm = _normalize_series(df["_dur_mins"], invert=True)
    board_norm = _normalize_series(df["_board_mins"], invert=True)
    drop_pref_norm = _normalize_series(df["_drop_pref"], invert=False)  # already 0..1 but ensure scaling

    # combine weighted score
    score = (
        weights.get("price", 1.0) * price_norm +
        weights.get("rating", 1.0) * rating_norm +
        weights.get("window", 1.0) * window_norm +
        weights.get("seats", 1.0) * seats_norm +
        weights.get("duration", 1.0) * dur_norm +
        weights.get("boarding", 1.0) * board_norm +
        weights.get("dropping_pref", 1.0) * drop_pref_norm
    )

    df["_score"] = score
    df_sorted = df.sort_values("_score", ascending=False).reset_index(drop=True)

    if verbose:
        print("[analyzer] Top 5 candidates by score (higher better):")
        show_cols = ["Bus Name", "Price", "Rating", "Window Seats", "Seats Available", "Duration", "Boarding Time", "Dropping Time", "_score"]
        for idx, r in df_sorted.head(5).iterrows():
            print(f"  #{idx+1}: {str(r.get('Bus Name',''))[:60]} | price={r.get('Price')} rating={r.get('Rating')} windows={r.get('Window Seats')} seats={r.get('Seats Available')} dur={r.get('Duration')} drop={r.get('Dropping Time')} board={r.get('Boarding Time')} score={r['_score']:.4f}")

    best = df_sorted.iloc[0]
    return best
