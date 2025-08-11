# utils.py
import time
from playwright.sync_api import Page, TimeoutError

def choose_first_visible(page: Page, selectors, wait_ms=800):
    """Return first selector that is visible."""
    for s in selectors:
        try:
            page.wait_for_selector(s, timeout=wait_ms)
            return s
        except TimeoutError:
            continue
    return None

def pick_autocomplete(page: Page, selector, text, timeout=5000):
    """Type text then pick suggestion."""
    if not selector:
        return False

    try:
        page.click(selector, force=True)
        page.fill(selector, "")
        page.type(selector, text, delay=70)
    except Exception:
        return False

    suggestion_selectors = [
        "ul.ui-autocomplete li",
        "div[role='listbox'] li",
        "div[role='listbox'] div[role='option']"
    ]
    end = time.time() + timeout / 1000
    while time.time() < end:
        for s in suggestion_selectors:
            try:
                if page.locator(s).count() > 0:
                    page.locator(s).first.click()
                    return True
            except Exception:
                pass
        time.sleep(0.2)
    return False
