# results_scraper.py
from playwright.sync_api import Page, TimeoutError
import pandas as pd
import re
from typing import List, Dict, Optional
import os
from urllib.parse import urljoin

BASE_URL = "https://www.vrlbus.in"

def _extract_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r'(\d+)', str(s).replace(',', ''))
    return int(m.group(1)) if m else None

def _clean_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    return ' '.join(str(s).split()).strip()

def _first_text(locator) -> str:
    try:
        if locator.count() > 0:
            return _clean_text(locator.first.inner_text())
    except Exception:
        pass
    return ""

def _find_booking_link_from_card(card, page_url: str) -> Optional[str]:
    """
    Heuristics to find a booking link for a bus card:
      1) First <a href> with non-javascript and non-empty href
      2) Any element with onclick containing a URL
      3) Any attribute like data-href, data-url
      4) Search HTML snippet for href patterns
    Returns absolute URL or None.
    """
    try:
        # 1) any anchor with a usable href
        anchors = card.query_selector_all("a[href]")
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if not href:
                    continue
                href = href.strip()
                if href.lower().startswith("javascript:") or href.startswith("#"):
                    continue
                # make absolute
                abs_url = urljoin(BASE_URL, href)
                return abs_url
            except Exception:
                continue

        # 2) look for onclick attributes containing location or window.open
        elements = card.query_selector_all("*[onclick]")
        for el in elements:
            try:
                js = el.get_attribute("onclick") or ""
                # try to extract URL from e.g. location.href='...'; window.open('...')
                m = re.search(r"(?:location\.href|window\.open|window\.location)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)|(?:location\.href\s*=\s*['\"]([^'\"]+)['\"])", js)
                if m:
                    href = m.group(1) or m.group(2)
                    if href:
                        return urljoin(BASE_URL, href)
            except Exception:
                continue

        # 3) any data-* attribute carrying url
        elems = card.query_selector_all("*")
        for el in elems:
            try:
                for attr in ["data-href", "data-url", "data-link", "href"]:
                    v = el.get_attribute(attr)
                    if v and isinstance(v, str) and v.strip() and not v.strip().startswith("javascript"):
                        return urljoin(BASE_URL, v.strip())
            except Exception:
                continue

        # 4) search raw html for href patterns pointing to internal booking pages
        html = card.inner_html()
        m = re.search(r'href=[\'"]([^\'"]*(?:book|seat|select|avail|ticket|booking)[^\'"]*)[\'"]', html, re.I)
        if m:
            return urljoin(BASE_URL, m.group(1))

        # 5) search any URL-like string in html
        m2 = re.search(r'(https?:\/\/[^\s"\'<>]+)', html)
        if m2:
            return m2.group(1)
    except Exception:
        pass

    # fallback: None
    return None

def scrape_results(page: Page, max_items: Optional[int] = None, wait_for_selector_timeout: int = 10000) -> List[Dict]:
    """
    Scrape bus results from the current page.
    Returns list of dicts (including Booking Link if found).
    """
    try:
        page.wait_for_selector(".busroutedetails", timeout=wait_for_selector_timeout)
    except TimeoutError:
        print("[scraper] No .busroutedetails found within timeout.")
        return []

    cards = page.locator(".busroutedetails")
    total = cards.count()
    if total == 0:
        print("[scraper] No bus cards found.")
        return []

    limit = total if max_items is None else min(total, max_items)
    print(f"[scraper] Found {total} cards, scraping {limit}...")

    rows = []
    for i in range(limit):
        print(f"[scraper] ({i+1}/{limit}) processing...")
        card = cards.nth(i)
        try:
            bus_id = card.get_attribute("id") or ""
        except Exception:
            bus_id = ""

        bus_name = _first_text(card.locator(".busnametype > .busboldlabel")) or _first_text(card.locator(".busboldlabel"))
        bus_type = _first_text(card.locator(".modifydatasleep")) or _first_text(card.locator(".busnametype .modifydatasleep"))

        boarding = _first_text(card.locator(".busroutedatatime .busstarttime .busboldlabel"))
        if not boarding:
            boarding = _first_text(card.locator(".busroutedatatimembl .busstarttime .busboldlabel"))

        dropping = _first_text(card.locator(".busroutedatatime .busendtime .busboldlabel"))
        if not dropping:
            dropping = _first_text(card.locator(".busroutedatatimembl .busendtime .busboldlabel"))

        duration = _first_text(card.locator(".busroutedatatime .busroutearrow .buslighttext_small"))
        if not duration:
            duration = _first_text(card.locator(".busroutedatatimembl .busroutearrow .buslighttext_small"))

        rating = _first_text(card.locator(".rattinglabel label")) or _first_text(card.locator(".busrattingmbl .rattinglabel label"))

        seats_available = None
        try:
            seats_text = _first_text(card.locator(".busseatmodify .buslighttext label"))
            seats_available = _extract_int(seats_text) if seats_text else None
        except Exception:
            seats_available = None

        window_seats = None
        try:
            window_text = _first_text(card.locator(".busseatmodify .windowseat label"))
            window_seats = _extract_int(window_text) if window_text else None
        except Exception:
            window_seats = None

        # price
        price = None
        try:
            price_text = _first_text(card.locator(".busfairdetails .busboldlabel label"))
            if not price_text:
                pb = _first_text(card.locator(".busfairdetails .busboldlabel"))
                price_text = re.sub(r'[^\d]', '', pb) if pb else ""
            price = _extract_int(price_text)
        except Exception:
            price = None

        original_price = None
        try:
            op = _first_text(card.locator(".busfairdetails del.lighttext"))
            original_price = _extract_int(op)
        except Exception:
            original_price = None

        saving = None
        try:
            sv = _first_text(card.locator(".busfairdetails .savingamount label"))
            saving = _extract_int(sv)
        except Exception:
            saving = None

        # booking link heuristics
        booking_link = _find_booking_link_from_card(card, page.url)

        rows.append({
            "Bus ID": bus_id,
            "Bus Name": bus_name,
            "Bus Type": bus_type,
            "Boarding Time": boarding,
            "Dropping Time": dropping,
            "Duration": duration,
            "Rating": rating,
            "Seats Available": seats_available,
            "Window Seats": window_seats,
            "Price": price,
            "Original Price": original_price,
            "Savings": saving,
            "Booking Link": booking_link
        })

    return rows

def save_to_csv(rows: List[Dict], source: str, dest: str, date_str: str, out_dir: str = ".") -> str:
    if not rows:
        print("[scraper] No rows to save.")
        return ""

    df = pd.DataFrame(rows)
    cols = ["Bus ID", "Bus Name", "Bus Type", "Boarding Time", "Dropping Time", "Duration",
            "Rating", "Seats Available", "Window Seats", "Price", "Original Price", "Savings", "Booking Link"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    safe_source = re.sub(r'\W+', '_', source)[:40]
    safe_dest = re.sub(r'\W+', '_', dest)[:40]
    safe_date = date_str.replace("/", "-").replace(" ", "_")
    fname = f"vrl_results_{safe_source}_{safe_dest}_{safe_date}.csv"
    out_path = os.path.join(out_dir, fname)

    os.makedirs(out_dir, exist_ok=True)
    df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"[scraper] Saved {len(df)} rows to {out_path}")
    return out_path
