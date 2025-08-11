# form_filler.py
import time
from playwright.sync_api import TimeoutError
from datepicker import pick_bootstrap_date

def choose_first_visible(page, selectors, wait_ms=500):
    """Return first selector that is visible on page."""
    for s in selectors:
        try:
            page.wait_for_selector(s, timeout=wait_ms)
            return s
        except TimeoutError:
            continue
    return None

def pick_autocomplete(page, selector, text, timeout=5000):
    """Type text then try to pick a suggestion."""
    try:
        page.click(selector, force=True)
    except:
        try:
            page.locator(selector).first.focus()
        except:
            pass

    try:
        page.fill(selector, "")
    except:
        pass
    page.type(selector, text, delay=70)

    suggestion_selectors = [
        "ul.ui-autocomplete li",
        "div[role='listbox'] li",
        "div[role='listbox'] div[role='option']",
        ".MuiAutocomplete-listbox li",
        ".autocomplete-suggestion",
    ]
    end_time = time.time() + timeout/1000.0
    while time.time() < end_time:
        for s in suggestion_selectors:
            try:
                loc = page.locator(s)
                if loc.count() > 0:
                    for i in range(loc.count()):
                        try:
                            txt = loc.nth(i).inner_text().strip()
                            if text.lower() in txt.lower():
                                loc.nth(i).click()
                                return True
                        except:
                            continue
                    loc.first.click()
                    return True
            except:
                pass
        time.sleep(0.2)

    try:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        return True
    except:
        return False

def fill_form(page, source, dest, dd, mm, yyyy):
    results = {
        "source_filled": False,
        "destination_filled": False,
        "date_selected": False
    }

    # Fill Source
    print(f"[+] Attempting to fill source: {source}")
    source_candidates = [
        "input#FromCity", "input#fromPlaceName",
        "input[placeholder*='Source']", "input[aria-label*='Source']"
    ]
    src_sel = choose_first_visible(page, source_candidates, wait_ms=800)
    if src_sel and pick_autocomplete(page, src_sel, source):
        results["source_filled"] = True
    print(f"[+] Source fill result: {results['source_filled']}")

    time.sleep(0.6)

    # Fill Destination
    print(f"[+] Attempting to fill destination: {dest}")
    dest_candidates = [
        "input#ToCity", "input#toPlaceName",
        "input[placeholder*='Destination']", "input[aria-label*='Destination']"
    ]
    dst_sel = choose_first_visible(page, dest_candidates, wait_ms=800)
    if dst_sel and pick_autocomplete(page, dst_sel, dest):
        results["destination_filled"] = True
    print(f"[+] Destination fill result: {results['destination_filled']}")

    time.sleep(0.6)

    # Pick Date
    print(f"[+] Attempting to select date: {dd:02d}-{mm:02d}-{yyyy}")
    results["date_selected"] = pick_bootstrap_date(page, dd, mm, yyyy)
    print(f"[+] Date selection result: {results['date_selected']}")

    return results
