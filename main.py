# main.py
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time
import pandas as pd
from banner_remover import remove_modals_and_overlays
from form_filler import fill_form
from results_scraper import scrape_results, save_to_csv
from analyzer import pick_best_bus

def get_user_input():
    default_source = "Bangalore"
    default_dest = "Mumbai"
    source = input(f"Enter source city (default: {default_source}): ").strip() or default_source
    dest = input(f"Enter destination city (default: {default_dest}): ").strip() or default_dest

    today = datetime.today()
    max_date = today + timedelta(days=365*2)
    print(f"[+] Date constraint: today or later. Max allowed: {max_date.date()}")

    while True:
        date_str = input("Enter journey date (DD/MM/YYYY) or 'q' to quit: ").strip()
        if date_str.lower() == 'q':
            exit()
        try:
            dd, mm, yyyy = map(int, date_str.split("/"))
            chosen_date = datetime(yyyy, mm, dd)
            if chosen_date < today:
                print("[!] Date cannot be in the past.")
                continue
            if chosen_date > max_date:
                print("[!] Date too far in the future.")
                continue
            return source, dest, dd, mm, yyyy
        except Exception:
            print("[!] Invalid date format. Use DD/MM/YYYY.")

def wait_for_search_results_quick(page, timeout_seconds=7.0):
    print(f"[+] Waiting up to {timeout_seconds}s for search results...")
    start = time.time()
    result_selectors = [
        "div#searchResults",
        "div[id*='searchResults']",
        ".resultsContainer",
        ".busroutedetails",
        "div.availableroutes",
        "table"
    ]
    while (time.time() - start) < timeout_seconds:
        try:
            current_url = page.url or ""
            if "/availableroutes" in current_url:
                return True
            for sel in result_selectors:
                el = page.query_selector(sel)
                if el:
                    try:
                        if el.bounding_box():
                            return True
                    except Exception:
                        return True
        except Exception:
            pass
        time.sleep(0.25)
    return False

def main():
    source, dest, dd, mm, yyyy = get_user_input()
    date_str = f"{dd:02d}-{mm:02d}-{yyyy}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(20000)

        print("[+] Opening VRL website...")
        page.goto("https://www.vrlbus.in/", wait_until="load", timeout=60000)

        time.sleep(3.5)
        remove_modals_and_overlays(page)

        # fill form
        form_results = fill_form(page, source, dest, dd, mm, yyyy)

        # click search
        print("[+] Clicking Search...")
        search_selectors = ["#searchBtn", "button#searchBtn", "button:has-text('Search')", "button:has-text('Search Buses')"]
        clicked = False
        for s in search_selectors:
            try:
                if page.locator(s).count() > 0:
                    page.locator(s).first.click(force=True)
                    clicked = True
                    print(f"[+] Clicked search with selector: {s}")
                    break
            except Exception:
                pass

        if not clicked:
            print("[!] Could not find search button — aborting.")
            browser.close()
            return

        # wait for results (fast poll, reload fallback)
        results_ready = wait_for_search_results_quick(page, timeout_seconds=7.0)
        if not results_ready:
            print("[!] Results not detected within 7s, attempting a reload.")
            try:
                page.reload(wait_until="load", timeout=15000)
            except Exception:
                pass
            results_ready = wait_for_search_results_quick(page, timeout_seconds=5.0)

        if not results_ready:
            print("[!] Results appear not to have loaded. You may need to refresh manually.")
        else:
            print("[+] Results detected — scraping...")

        # scrape all results
        rows = scrape_results(page, max_items=None, wait_for_selector_timeout=10000)
        if not rows:
            print("[!] No results scraped.")
            browser.close()
            return

        csv_path = save_to_csv(rows, source, dest, date_str, out_dir="results")
        print(f"[+] CSV saved to {csv_path}")

        # analyze locally (no LLM)
        print("[+] Running analyzer to choose best bus (drop-time preferences applied)...")
        best = pick_best_bus(csv_path, verbose=True)
        if best is not None:
            print("\n=== BEST BUS (full row) ===")
            # print all columns nicely
            for k, v in best.to_dict().items():
                print(f"{k}: {v}")
            # if booking link available, print clickable URL
            bk = best.get("Booking Link", None)
            if bk and not pd.isna(bk):
                print("\n[+] Booking link (open in browser):")
                print(bk)
            print("==========================\n")
        else:
            print("[!] Analyzer could not determine a best bus.")

        input("Press Enter to close browser and finish...")
        browser.close()

if __name__ == "__main__":
    main()
