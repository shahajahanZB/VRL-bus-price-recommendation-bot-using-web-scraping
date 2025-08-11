# results_scraper.py
from playwright.sync_api import Page, TimeoutError
import pandas as pd
import re
from typing import List, Dict, Optional
import os

def _extract_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r'(\d+)', s.replace(',', ''))
    return int(m.group(1)) if m else None

def _clean_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    return ' '.join(s.split()).strip()

def _first_text(locator) -> str:
    try:
        if locator.count() > 0:
            return _clean_text(locator.first.inner_text())
    except Exception:
        pass
    return ""

def scrape_results(page: Page, max_items: Optional[int] = None, wait_for_selector_timeout: int = 10000) -> List[Dict]:
    """
    Scrape bus results from the current page.
    Returns list of dicts with keys:
      'Bus ID','Bus Name','Bus Type','Boarding Time','Dropping Time','Duration',
      'Rating','Seats Available','Window Seats','Price','Original Price','Savings'
    """
    try:
        page.wait_for_selector(".busroutedetails", timeout=wait_for_selector_timeout)
    except TimeoutError:
        print("[scraper] No .busroutedetails found within timeout.")
        return []

    cards = page.locator(".busroutedetails")
    total_found = cards.count()
    if total_found == 0:
        print("[scraper] No bus cards found.")
        return []

    total = total_found if max_items is None else min(total_found, max_items)
    print(f"[scraper] Found {total_found} cards on page; will scrape first {total}.")

    results = []
    for i in range(total):
        print(f"[scraper] ({i+1}/{total}) Processing card...")
        card = cards.nth(i)
        # Bus ID
        try:
            bus_id = card.get_attribute("id") or ""
        except Exception:
            bus_id = ""

        # Bus name
        bus_name = _first_text(card.locator(".busnametype > .busboldlabel")) or _first_text(card.locator(".busboldlabel"))

        # Bus type (e.g. "Non AC / Sleeper")
        bus_type = _first_text(card.locator(".modifydatasleep")) or _first_text(card.locator(".busnametype .modifydatasleep"))

        # Boarding and Dropping times
        boarding = _first_text(card.locator(".busroutedatatime .busstarttime .busboldlabel"))
        if not boarding:
            boarding = _first_text(card.locator(".busroutedatatimembl .busstarttime .busboldlabel"))

        dropping = _first_text(card.locator(".busroutedatatime .busendtime .busboldlabel"))
        if not dropping:
            dropping = _first_text(card.locator(".busroutedatatimembl .busendtime .busboldlabel"))

        # Duration
        duration = _first_text(card.locator(".busroutedatatime .busroutearrow .buslighttext_small"))
        if not duration:
            duration = _first_text(card.locator(".busroutedatatimembl .busroutearrow .buslighttext_small"))

        # Rating
        rating = _first_text(card.locator(".rattinglabel label")) or _first_text(card.locator(".busrattingmbl .rattinglabel label"))

        # Seats available and window seats
        seats_text = _first_text(card.locator(".busseatmodify .buslighttext"))
        seats_available = _extract_int(seats_text) if seats_text else None
        window_text = _first_text(card.locator(".busseatmodify .windowseat"))
        window_seats = _extract_int(window_text) if window_text else None

        # Price, original price, savings
        price_label = _first_text(card.locator(".busfairdetails .busboldlabel label"))
        if not price_label:
            pb = _first_text(card.locator(".busfairdetails .busboldlabel"))
            price_label = re.sub(r'[^\d]', '', pb) if pb else ""
        price = _extract_int(price_label)

        original_price_text = _first_text(card.locator(".busfairdetails del.lighttext"))
        original_price = _extract_int(original_price_text)

        saving = _first_text(card.locator(".busfairdetails .savingamount label"))
        savings = _extract_int(saving)

        record = {
            "Bus ID": bus_id,
            "Bus Name": bus_name or None,
            "Bus Type": bus_type or None,
            "Boarding Time": boarding or None,
            "Dropping Time": dropping or None,
            "Duration": duration or None,
            "Rating": rating or None,
            "Seats Available": seats_available,
            "Window Seats": window_seats,
            "Price": price,
            "Original Price": original_price,
            "Savings": savings
        }
        print(f"[scraper] ({i+1}/{total}) -> {bus_name or 'Unnamed Bus'} | Price: {price or 'N/A'} | Seats: {seats_available or 'N/A'}")
        results.append(record)

    return results

def save_to_csv(rows: List[Dict], source: str, dest: str, date_str: str, out_dir: str = ".") -> str:
    """
    Save rows (list of dicts) to a CSV file (UTF-8 with BOM).
    Returns the path written.
    """
    if not rows:
        print("[scraper] No rows to save.")
        return ""

    df = pd.DataFrame(rows)
    cols = ["Bus ID", "Bus Name", "Bus Type", "Boarding Time", "Dropping Time", "Duration",
            "Rating", "Seats Available", "Window Seats", "Price", "Original Price", "Savings"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    safe_source = re.sub(r'\W+', '_', source)[:40]
    safe_dest = re.sub(r'\W+', '_', dest)[:40]
    safe_date = date_str.replace("/", "-").replace(" ", "_")
    fname = f"vrl_results_{safe_source}_{safe_dest}_{safe_date}.csv"
    out_path = os.path.join(out_dir, fname)

    df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"[scraper] Saved {len(df)} rows to {out_path}")
    return out_path
