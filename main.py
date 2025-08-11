# main.py
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time

from banner_remover import remove_modals_and_overlays
from form_filler import fill_form

def get_user_input():
    # Defaults
    default_source = "Bangalore"
    default_dest = "Mumbai"

    source = input(f"Enter source city (default: {default_source}): ").strip() or default_source
    dest = input(f"Enter destination city (default: {default_dest}): ").strip() or default_dest

    today = datetime.today()
    max_date = today + timedelta(days=365*2)  # max 2 years in future
    print(f"[+] Date constraint: must be today or future (not earlier than {today.date()}). Max allowed: {max_date.date()}")

    while True:
        date_str = input("Enter journey date (DD/MM/YYYY) or 'q' to quit: ").strip()
        if date_str.lower() == 'q':
            exit()
        try:
            dd, mm, yyyy = map(int, date_str.split("/"))
            chosen_date = datetime(yyyy, mm, dd)
            if chosen_date < today:
                print("[!] Date cannot be in the past. Try again.")
                continue
            if chosen_date > max_date:
                print("[!] Date too far in the future. Try again.")
                continue
            return source, dest, dd, mm, yyyy
        except Exception:
            print("[!] Invalid date format. Please use DD/MM/YYYY.")

def wait_for_search_results_quick(page, timeout_seconds=7.0):
    """
    Poll for search-results readiness up to `timeout_seconds`.
    Returns True if results detected early, otherwise False.
    Detection methods:
      - URL contains '/availableroutes'
      - presence of likely result containers (checked via page.query_selector)
    """
    print(f"[+] Waiting up to {timeout_seconds}s for search results (returns early if ready)...")
    start = time.time()
    result_selectors = [
        "div#searchResults",                  # explicit id
        "div[id*='searchResults']",
        ".resultsContainer",
        ".availableroutes",
        "table",                              # fallback table presence
        "div.availableroutes"                 # other possible class
    ]

    while (time.time() - start) < timeout_seconds:
        try:
            # 1) URL check
            current_url = page.url or ""
            if "/availableroutes" in current_url:
                # likely navigated to results page
                return True

            # 2) DOM check: fast query_selector (does not wait)
            for sel in result_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        # try to detect visible by bounding box (None if not visible)
                        try:
                            bb = el.bounding_box()
                            if bb:
                                return True
                        except Exception:
                            # if bounding_box fails, assume element exists -> treat as ready
                            return True
                except Exception:
                    continue
        except Exception:
            pass

        time.sleep(0.25)  # short sleep between polls

    # timed out
    return False

def main():
    source, dest, dd, mm, yyyy = get_user_input()

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

        # Remove banner/modal
        remove_modals_and_overlays(page)
        run_summary["modal_removed"] = True
        print("[+] Modal removal: Removed modals/overlays")

        # Fill form (expects fill_form(page, source, dest, dd, mm, yyyy) -> dict with keys)
        form_results = fill_form(page, source, dest, dd, mm, yyyy)
        # form_results should contain keys: source_filled, destination_filled, date_selected (True/False)
        run_summary.update(form_results)

        # Click Search button
        print("[+] Attempting to click Search button...")
        search_selectors = [
            "#searchBtn",
            "button#searchBtn",
            "button:has-text('Search')",
            "button:has-text('Search Buses')",
            "button[type='submit']"
        ]

        for s in search_selectors:
            try:
                if page.locator(s).count() > 0:
                    # click
                    page.locator(s).first.click(force=True)
                    run_summary["search_clicked"] = True
                    print(f"[+] Clicked search with selector: {s}")

                    # combined wait: early-return if page ready, max 7s
                    results_ready = wait_for_search_results_quick(page, timeout_seconds=7.0)
                    if results_ready:
                        print("[+] Search results detected (early or on time).")
                    else:
                        print("[!] Search results NOT detected within 7s.")
                        # optional: do a gentle reload once if results not detected
                        try:
                            print("[+] Attempting a single reload to recover results...")
                            page.reload(wait_until="load", timeout=15000)
                            # after reload, do one quick check (2s)
                            if wait_for_search_results_quick(page, timeout_seconds=2.0):
                                print("[+] Results detected after reload.")
                            else:
                                print("[!] Still no results after reload. You may need to refresh manually.")
                        except Exception as e:
                            print("[!] Reload attempt failed:", e)
                    break
            except Exception:
                pass

        # Show run summary
        print("[+] Run summary:")
        for k, v in run_summary.items():
            print(f"[+]   {k}: {v}")

        input("Press Enter to close browser and finish...")
        browser.close()

if __name__ == "__main__":
    main()
