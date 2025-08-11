# datepicker.py
"""
Robust datepicker helper for VRL (bootstrap-like datepicker).
Provides: pick_bootstrap_date(page, day, month, year) -> bool

Depends on: utils.choose_first_visible (optional, but not required).
"""
import time
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# month abbreviations used in the widget
MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def debug(msg):
    print(f"[datepicker] {msg}")

def wait_for_datepicker_visible(page, timeout=4000):
    """Wait until any div.datepicker has computed display != 'none'."""
    try:
        page.wait_for_function(
            "timeout => !!Array.from(document.querySelectorAll('div.datepicker')).some(el=>window.getComputedStyle(el).display!=='none')",
            arg=0,
            timeout=timeout
        )
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False

def try_click_element(page, locator):
    """Attempt several click methods on a Locator. Returns True if any succeeded."""
    try:
        locator.scroll_into_view_if_needed()
    except Exception:
        pass

    # direct click (preferred)
    try:
        locator.click(force=True)
        page.wait_for_timeout(160)
        return True
    except Exception:
        pass

    # JS click via element handle
    try:
        handle = locator.element_handle()
        if handle:
            page.evaluate("(el) => { el.scrollIntoView({block:'center'}); el.click(); }", handle)
            page.wait_for_timeout(160)
            return True
    except Exception:
        pass

    # dispatch mouse events fallback
    try:
        handle = locator.element_handle()
        if handle:
            page.evaluate("""
                el => {
                    el.scrollIntoView({block:'center'});
                    const r = el.getBoundingClientRect();
                    const evDown = new MouseEvent('mousedown', {bubbles:true,clientX:r.left+2,clientY:r.top+2});
                    const evUp = new MouseEvent('mouseup', {bubbles:true,clientX:r.left+2,clientY:r.top+2});
                    el.dispatchEvent(evDown);
                    el.dispatchEvent(evUp);
                }
            """, handle)
            page.wait_for_timeout(160)
            return True
    except Exception:
        pass

    return False

def open_datepicker(page):
    """
    Robustly find and open the datepicker.
    Returns (True, message) on success, (False, message) on failure.
    """
    candidates = [
        "input#txtJourneyDate",
        "input[id*='JourneyDate']",
        "input[placeholder*='Date']",
        "input[placeholder*='date']",
        ".input-group.date input",
        ".tab-bookingform input[type='text']",
        "div.datepicker-trigger",
        ".booking-date", ".journey-date",
        "div[class*='journey'] input",
        "div[class*='date'] input",
        "input[name*='Date']",
    ]

    for sel in candidates:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                # iterate find visible instance
                for i in range(loc.count()):
                    l = loc.nth(i)
                    try:
                        if not l.is_visible():
                            continue
                    except Exception:
                        continue
                    debug(f"Trying to open datepicker by clicking '{sel}'")
                    if try_click_element(page, l):
                        if wait_for_datepicker_visible(page, timeout=3500):
                            return True, f"Opened datepicker by clicking '{sel}'"
                        debug(f"Clicked '{sel}' but datepicker did not appear; continuing tries.")
        except Exception:
            continue

    # fallback: find element containing a date-like string and click it
    try:
        found = page.evaluate("""
            () => {
                const re = /\\d{2}[-\\/]\\d{2}[-\\/]\\d{4}/;
                const els = Array.from(document.querySelectorAll('body *:not(script):not(style)'));
                for (const el of els) {
                    try {
                        const t = (el.innerText || '').trim();
                        if (re.test(t)) {
                            el.setAttribute('data-pw-date-trigger','1');
                            el.scrollIntoView({block:'center'});
                            return true;
                        }
                    } catch(e){}
                }
                return false;
            }
        """)
        if found:
            loc = page.locator('[data-pw-date-trigger="1"]')
            if loc.count() > 0:
                debug("Clicking element that contains date-like text (marked).")
                if try_click_element(page, loc.first):
                    if wait_for_datepicker_visible(page, timeout=3500):
                        page.evaluate("() => { document.querySelectorAll('[data-pw-date-trigger]').forEach(e=>e.removeAttribute('data-pw-date-trigger')); }")
                        return True, "Opened datepicker by clicking visible date-text element"
                    debug("Clicked date-text element but datepicker not visible.")
    except Exception:
        pass

    # last resort: try jQuery datepicker show if present
    try:
        hasjq = page.evaluate("() => !!window.jQuery")
        if hasjq:
            ran = page.evaluate("""
                () => {
                    try {
                        for (const el of document.querySelectorAll('input,div')) {
                            try {
                                if (window.jQuery && window.jQuery(el).data('datepicker')) {
                                    window.jQuery(el).datepicker('show');
                                    return true;
                                }
                            } catch(e){}
                        }
                    } catch(e){}
                    return false;
                }
            """)
            if ran and wait_for_datepicker_visible(page, timeout=3000):
                return True, "Opened datepicker via jQuery .datepicker('show')"
    except Exception:
        pass

    return False, "Could not find or open datepicker (tried many triggers)."

def which_view_visible(page):
    """Return 'days','months','years' depending on which container is displayed."""
    try:
        if page.locator("div.datepicker-days").evaluate("el => window.getComputedStyle(el).display !== 'none'"):
            return "days"
    except Exception:
        pass
    try:
        if page.locator("div.datepicker-months").evaluate("el => window.getComputedStyle(el).display !== 'none'"):
            return "months"
    except Exception:
        pass
    try:
        if page.locator("div.datepicker-years").evaluate("el => window.getComputedStyle(el).display !== 'none'"):
            return "years"
    except Exception:
        pass
    return None

def click_datepicker_switch(page):
    """Click the visible switch header to toggle days->months->years."""
    try:
        page.locator("div.datepicker .datepicker-switch").first.click(force=True)
        page.wait_for_timeout(120)
        return True
    except Exception:
        return False

def click_year(page, year):
    """Try to click the requested year in years view; navigate decades if needed."""
    y_str = str(year)
    attempts = 8
    for _ in range(attempts):
        try:
            xp = f"xpath=//div[contains(@class,'datepicker-years')]//span[normalize-space(text())='{y_str}']"
            if page.locator(xp).count() > 0:
                page.locator(xp).first.click(force=True)
                page.wait_for_timeout(140)
                return True
        except Exception:
            pass
        # try advance decade
        try:
            if page.locator("div.datepicker-years th.next").count() > 0:
                page.locator("div.datepicker-years th.next").first.click(force=True)
                page.wait_for_timeout(140)
                continue
        except Exception:
            pass
        try:
            if page.locator("div.datepicker-years th.prev").count() > 0:
                page.locator("div.datepicker-years th.prev").first.click(force=True)
                page.wait_for_timeout(140)
                continue
        except Exception:
            pass
    return False

def click_month(page, month_idx):
    """Click a month by month index (1..12)."""
    name = MONTH_ABBR[month_idx-1]
    xp = f"xpath=//div[contains(@class,'datepicker-months')]//span[normalize-space(text())='{name}']"
    try:
        if page.locator(xp).count() > 0:
            page.locator(xp).first.click(force=True)
            page.wait_for_timeout(120)
            return True
    except Exception:
        pass
    return False

def click_day(page, day):
    """Click the day cell in the days view (ignores disabled cells)."""
    d = str(int(day))
    xpaths = [
        f"xpath=//div[contains(@class,'datepicker-days')]//td[contains(@class,'day') and not(contains(@class,'disabled')) and normalize-space(text())='{d}']",
        f"xpath=//div[contains(@class,'datepicker-days')]//td[normalize-space(text())='{d}' and not(contains(@class,'disabled'))]"
    ]
    for xp in xpaths:
        try:
            if page.locator(xp).count() > 0:
                page.locator(xp).first.click(force=True)
                page.wait_for_timeout(120)
                return True
        except Exception:
            continue

    # fallback iterate all day cells
    try:
        days = page.locator("div.datepicker .datepicker-days td.day")
        for i in range(days.count()):
            try:
                txt = days.nth(i).inner_text().strip()
                cls = (days.nth(i).get_attribute("class") or "")
                if txt == d and "disabled" not in cls:
                    days.nth(i).click(force=True)
                    page.wait_for_timeout(120)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def pick_bootstrap_date(page, day, month, year):
    """
    Orchestrate opening datepicker and selecting year->month->day.
    Returns True on success, False on failure.
    """
    ok, msg = open_datepicker(page)
    debug(f"open_datepicker: {ok} - {msg}")
    if not ok:
        # fallback: try to write raw value into common input selectors
        raw = f"{str(day).zfill(2)}-{str(month).zfill(2)}-{year}"
        for sel in ["input#txtJourneyDate", "input[id*='JourneyDate']", "input[name*='JourneyDate']"]:
            try:
                res = page.evaluate("(s,v)=>{ const el=document.querySelector(s); if(!el) return false; el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); return true; }", sel, raw)
                if res:
                    debug(f"Wrote date directly into {sel}")
                    return True
            except Exception:
                continue
        debug("Could not open datepicker and raw input fallback failed.")
        return False

    # now navigate inside datepicker
    for attempt in range(12):
        view = which_view_visible(page)
        try:
            switch_txt = page.locator("div.datepicker .datepicker-switch").first.text_content().strip()
        except Exception:
            switch_txt = ""
        debug(f"Attempt {attempt}: view={view}, header='{switch_txt}'")

        if view == "days":
            # if correct year visible, try to click day; otherwise go up to months
            if str(year) in switch_txt:
                if click_day(page, day):
                    debug("Clicked day in days view.")
                    return True
                debug("Day clickable check failed in days view.")
                return False
            # open months
            click_datepicker_switch(page)
            time.sleep(0.12)
            continue

        if view == "months":
            if str(year) in switch_txt:
                # pick month, then day
                if click_month(page, month):
                    if click_day(page, day):
                        debug("Selected month and day.")
                        return True
                    debug("Month clicked but day selection failed.")
                    return False
                debug("Month click failed.")
                # try to go to years
                click_datepicker_switch(page)
                time.sleep(0.12)
                continue
            else:
                # go to years view
                click_datepicker_switch(page)
                time.sleep(0.12)
                continue

        if view == "years":
            if click_year(page, year):
                # after year chosen, months view should show
                if click_month(page, month):
                    if click_day(page, day):
                        debug("Selected year, month and day.")
                        return True
                    debug("After choosing month, day click failed.")
                    return False
                debug("After selecting year, month choose failed.")
                return False
            debug("Year click failed in years view.")
            return False

        # fallback: click switch to move between views
        click_datepicker_switch(page)
        time.sleep(0.12)

    # last fallback: raw input write
    raw = f"{str(day).zfill(2)}-{str(month).zfill(2)}-{year}"
    for sel in ["input#txtJourneyDate", "input[id*='JourneyDate']", "input[name*='JourneyDate']"]:
        try:
            res = page.evaluate("(s,v)=>{ const el=document.querySelector(s); if(!el) return false; el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); return true; }", sel, raw)
            if res:
                debug(f"Fallback wrote date directly into {sel}")
                return True
        except Exception:
            continue

    debug("All attempts to pick date failed.")
    return False
