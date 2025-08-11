# main.py
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time

from banner_remover import remove_modals_and_overlays
from form_filler import fill_form
from results_scraper import scrape_results, save_to_csv

def get_user_input():
    default_source = "Bangalore"
    default_dest = "Mumbai"

    source = input(f"Enter source city (default: {default_source}): ").strip() or default_source
    dest = input(f"Enter destination city (default: {default_dest}): ").strip() or default_dest

    today = datetime.today()
    max_date = today + timedelta(days=365*2)
    print(f"[+] Date constraint: must be today or future (not earlier than {today.date()}). Max allowed: {max_date.date()}")

    while True:
        date_str = input("Enter journey date (DD/MM/YYYY) or 'q' to quit: ").strip()
        if date_str.lower() == 'q':
            exit()
        try:
            dd, mm, yyyy = map(int, date_str.replace("-", "/").split("/"))
            chosen_date = datetime(yyyy, mm, dd)
            if chosen_date.date() < today.date():
                print("[!] Date cannot be in the past. Try again.")
                continue
            if chosen_date > max_date:
                print("[!] Date too far in the future. Try again.")
                continue
            return source, dest, dd, mm, yyyy
        except Exception:
            print("[!] Invalid date format. Please use DD/MM/YYYY.")

def wait_for_search_results_quick(page, timeout_seconds=7.0):
    print(f"[+] Waiting up to {timeout_seconds}s for search results (returns early if ready)...")
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
                try:
                    el = page.query_selector(sel)
                    if el:
                        try:
                            if el.bounding_box():
                                return True
                        except Exception:
                            return True
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.25)
    return False

def main():
    source, dest, dd, mm, yyyy = get_user_input()
    date_display = f"{str(dd).zfill(2)}-{str(mm).zfill(2)}-{yyyy}"

    run_summary = {
        "page_opened": False,
        "modal_removed": False,
        "source_filled": False,
        "destination_filled": False,
        "date_selected": False,
        "search_clicked": False
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(20000)

        print("[+] Opening VRL website...")
        page.goto("https://www.vrlbus.in/", wait_until="load", timeout=60000)
        run_summary["page_opened"] = True

        print("[+] Waiting 3.5s to let page elements (banners/modals) settle...")
        time.sleep(3.5)

        remove_modals_and_overlays(page)
        run_summary["modal_removed"] = True
        print("[+] Modal removal: Removed modals/overlays")

        form_results = fill_form(page, source, dest, dd, mm, yyyy)
        run_summary.update(form_results)

        print("[+] Attempting to click Search button...")
        search_selectors = [
            "#searchBtn",
            "button#searchBtn",
            "button:has-text('Search')",
            "button:has-text('Search Buses')",
            "button[type='submit']"
        ]
        clicked = False
        for s in search_selectors:
            try:
                if page.locator(s).count() > 0:
                    page.locator(s).first.click(force=True)
                    run_summary["search_clicked"] = True
                    print(f"[+] Clicked search with selector: {s}")
                    clicked = True

                    results_ready = wait_for_search_results_quick(page, timeout_seconds=7.0)
                    if results_ready:
                        print("[+] Search results detected.")
                    else:
                        print("[!] Search results NOT detected within 7s. Attempting one reload and re-check.")
                        try:
                            page.reload(wait_until="load", timeout=15000)
                            if wait_for_search_results_quick(page, timeout_seconds=3.0):
                                print("[+] Results detected after reload.")
                            else:
                                print("[!] Still no results after reload.")
                        except Exception as e:
                            print("[!] Reload failed:", e)
                    break
            except Exception:
                pass

        if not clicked:
            print("[!] Could not find/click a search button. Aborting scraping.")
        else:
            print("[+] Starting to scrape bus results...")
            rows = scrape_results(page, max_items=None, wait_for_selector_timeout=10000)
            if rows:
                out_path = save_to_csv(rows, source, dest, date_display)
                print(f"[+] Scraped {len(rows)} rows and saved to: {out_path}")
            else:
                print("[!] No rows scraped. Check if results loaded or site changed structure.")

        print("[+] Run summary:")
        for k, v in run_summary.items():
            print(f"[+]   {k}: {v}")

        input("Press Enter to close browser and finish...")
        browser.close()

if __name__ == "__main__":
    main()
