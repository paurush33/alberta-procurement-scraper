import json
import logging
import random
import time
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Set
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager

# ==============================
# CONFIG
# ==============================
URL = "https://purchasing.alberta.ca/search"
OUT_PATH = Path("opportunities.jsonl")

HEADLESS = False
PAGELOAD_TIMEOUT = 60
WAIT_TIMEOUT = 35

START_PAGE = 1
# set to None to keep going until navigation fails
END_PAGE: Optional[int] = 1289
PER_PAGE_MAX: Optional[int] = None

SLEEP_AFTER_NAV = 0.8
BASE_RATE_LIMIT = 0.7
LONG_PAUSE_EVERY = 25
LONG_PAUSE_SECONDS = 10
MAX_RETRIES_PER_PAGE = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

# Common selector for result cards
CSS_RESULTS_SEL = "apc-opportunity-search-result, .result-item, li.result, div.search-result"

# ===== JavaScript helpers (work through Shadow DOM and normal DOM) =====
JS_QSA_ALL_SHADOW = """
const selector = arguments[0];
function allShadowHosts(root) {
  const hosts = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let node;
  while (node = walker.nextNode()) if (node.shadowRoot) hosts.push(node);
  return hosts;
}
function deepQuerySelectorAll(root, sel) {
  const out = Array.from(root.querySelectorAll(sel));
  for (const h of allShadowHosts(root)) out.push(...deepQuerySelectorAll(h.shadowRoot, sel));
  return out;
}
return deepQuerySelectorAll(document, selector);
"""

JS_QS_ALL_SHADOW_TEXT = """
const pageStr = String(arguments[0]).trim();
function allShadowHosts(root) {
  const hosts = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let node;
  while (node = walker.nextNode()) if (node.shadowRoot) hosts.push(node);
  return hosts;
}
function deepNodes(root) {
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let node;
  while (node = walker.nextNode()) out.push(node);
  for (const h of allShadowHosts(root)) out.push(...deepNodes(h.shadowRoot));
  return out;
}
const nodes = deepNodes(document);
const hits = [];
for (const el of nodes) {
  try {
    const txt = (el.innerText||"").trim();
    if (txt === pageStr) hits.push(el);
  } catch(e) {}
}
return hits;
"""

JS_GET_FIRST_RESULT_FP = """
function allShadowHosts(root) {
  const hosts = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let node;
  while (node = walker.nextNode()) if (node.shadowRoot) hosts.push(node);
  return hosts;
}
function deepQuery(root, sel) {
  let el = root.querySelector(sel);
  if (el) return el;
  for (const h of allShadowHosts(root)) {
    el = deepQuery(h.shadowRoot, sel);
    if (el) return el;
  }
  return null;
}
const card = deepQuery(document, "apc-opportunity-search-result, .result-item, li.result, div.search-result");
if (!card) return ["",""];
let link = card.querySelector("a[href^='/posting/']") || card.querySelector("a");
if (!link) return ["",""];
return [(link.innerText||"").trim(), (link.getAttribute("href")||"").trim()];
"""

JS_SCROLL_PAGER_INTO_VIEW = """
const cand = document.querySelector("apc-paginator, .pagination, nav[aria-label='pagination'], .paginator, .mat-paginator");
if (cand) cand.scrollIntoView({block:'center'});
return !!cand;
"""

# ==============================
# DRIVER SETUP
# ==============================
def setup_driver() -> webdriver.Firefox:
    opts = Options()
    opts.headless = HEADLESS
    drv = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=opts)
    drv.set_page_load_timeout(PAGELOAD_TIMEOUT)
    try:
        drv.maximize_window()
    except Exception:
        pass
    return drv

# ==============================
# JS BRIDGE HELPERS
# ==============================
def qsa_all_shadow(drv, css: str):
    return drv.execute_script(JS_QSA_ALL_SHADOW, css)

def find_elements_by_text_shadow(drv, text: str):
    return drv.execute_script(JS_QS_ALL_SHADOW_TEXT, text)

def first_result_fingerprint(drv) -> Tuple[str, str]:
    t, href = drv.execute_script(JS_GET_FIRST_RESULT_FP)
    return (t or "", href or "")

def scroll_pager_into_view(drv):
    try:
        drv.execute_script(JS_SCROLL_PAGER_INTO_VIEW)
    except Exception:
        pass

# ==============================
# WAITS
# ==============================
def wait_for_any_result(drv, timeout=WAIT_TIMEOUT):
    t0 = time.time()
    while time.time() - t0 < timeout:
        els = qsa_all_shadow(drv, CSS_RESULTS_SEL)
        if els:
            return True
        time.sleep(0.4)
    raise TimeoutException("No results appeared")

def wait_for_page_change(drv, prev_fp: Tuple[str, str], timeout=WAIT_TIMEOUT):
    t0 = time.time()
    while time.time() - t0 < timeout:
        fp = first_result_fingerprint(drv)
        if fp != ("", "") and fp != prev_fp:
            return True
        time.sleep(0.3)
    raise TimeoutException("Page did not change")

# ==============================
# PARSING
# ==============================
def parse_current_page(drv, per_page_max: Optional[int], seen: Set[str]) -> List[dict]:
    out: List[dict] = []
    cards = qsa_all_shadow(drv, CSS_RESULTS_SEL)
    for idx, card in enumerate(cards):
        if per_page_max and idx >= per_page_max:
            break
        try:
            link = drv.execute_script(
                "return arguments[0].querySelector(\"a[href^='/posting/']\") || arguments[0].querySelector('a');",
                card,
            )
            if not link:
                continue
            title = (link.get_attribute("innerText") or "").strip()
            url = (link.get_attribute("href") or "").strip()
            if not url or url in seen:
                continue
            url = urljoin(URL, url)

            desc_el = drv.execute_script(
                "return arguments[0].querySelector(\"span.search-result__description, .result-description, .summary, .teaser\");",
                card,
            )
            desc = (desc_el.get_attribute("innerText") or "").strip() if desc_el else None

            out.append({"Title": title, "URL": url, "Description": desc})
            seen.add(url)
        except Exception:
            continue
    return out

# ==============================
# NAVIGATION
# ==============================
def try_type_page_number(drv, target_page: int) -> bool:
    scroll_pager_into_view(drv)
    inputs = qsa_all_shadow(
        drv,
        "apc-paginator input[aria-label='Page Number'], input[aria-label='Page number'], input[type='number']",
    )
    if inputs:
        ip = inputs[0]
        try:
            drv.execute_script("arguments[0].focus();", ip)
            ip.clear()
            ip.send_keys(str(target_page))
            ip.send_keys(Keys.ENTER)
            return True
        except Exception:
            try:
                drv.execute_script(
                    """
                    const el = arguments[0], val = arguments[1];
                    el.focus(); el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter'}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter'}));
                    """,
                    ip,
                    str(target_page),
                )
                return True
            except Exception:
                return False
    return False

def try_click_numeric_link(drv, target_page: int) -> bool:
    scroll_pager_into_view(drv)
    hits = find_elements_by_text_shadow(drv, str(target_page))
    for el in hits:
        try:
            tag = (el.tagName or "").lower()
            clickable = tag in ("a", "button") or (el.getAttribute("role") or "").lower() == "button"
            if not clickable:
                child = drv.execute_script("return arguments[0].querySelector('a,button')", el)
                if child:
                    el = child

            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.1)
            try:
                el.click()
            except WebDriverException:
                drv.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue
    return False

def goto_page(drv, target_page: int, prev_fp: Tuple[str, str]) -> None:
    """Navigate to target_page with retries & backoff; raises if it truly fails."""
    for attempt in range(1, MAX_RETRIES_PER_PAGE + 1):
        ok = try_type_page_number(drv, target_page)
        if not ok:
            ok = try_click_numeric_link(drv, target_page)
        if ok:
            try:
                wait_for_page_change(drv, prev_fp, timeout=WAIT_TIMEOUT + attempt * 5)
                return
            except TimeoutException:
                pass

        sleep_for = (BASE_RATE_LIMIT + attempt * 1.2) + random.uniform(0.2, 0.8)
        logging.warning(f"Retry {attempt}/{MAX_RETRIES_PER_PAGE} to reach page {target_page} (sleep {sleep_for:.1f}s)")
        time.sleep(sleep_for)
        scroll_pager_into_view(drv)

    raise RuntimeError(f"Failed to navigate to page {target_page} after {MAX_RETRIES_PER_PAGE} attempts")

# ==============================
# MAIN LOOP
# ==============================
def run():
    drv = None
    seen: Set[str] = set()
    pages_done = 0
    total_rows = 0
    try:
        drv = setup_driver()
        logging.info(f"Opening {URL}")
        drv.get(URL)
        wait_for_any_result(drv, WAIT_TIMEOUT)

        prev_fp = first_result_fingerprint(drv)
        current = 1

        if START_PAGE > 1:
            logging.info(f"Jump to page {START_PAGE}")
            goto_page(drv, START_PAGE, prev_fp)
            time.sleep(SLEEP_AFTER_NAV)
            current = START_PAGE

        with OUT_PATH.open("a", encoding="utf-8") as out:
            while True:
                logging.info(f"Scraping page {current} …")

                # Try to force lazy content to load
                try:
                    for _ in range(4):
                        drv.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.3)
                except Exception:
                    pass

                rows = parse_current_page(drv, PER_PAGE_MAX, seen)
                for r in rows:
                    out.write(json.dumps(r, ensure_ascii=False) + "\n")
                out.flush()
                total_rows += len(rows)
                pages_done += 1
                logging.info(f"Page {current}: +{len(rows)} rows (total {total_rows})")

                if END_PAGE is not None and current >= END_PAGE:
                    break

                prev_fp = first_result_fingerprint(drv)
                target = current + 1
                try:
                    goto_page(drv, target, prev_fp)
                except Exception as e:
                    logging.error(f"Navigation to page {target} failed: {e}")
                    break

                time.sleep(SLEEP_AFTER_NAV + random.uniform(0.1, 0.5))
                current = target

                if pages_done % LONG_PAUSE_EVERY == 0:
                    logging.info(f"Cooling down {LONG_PAUSE_SECONDS}s to avoid throttle…")
                    time.sleep(LONG_PAUSE_SECONDS)

        logging.info(f"Saved {total_rows} records across {pages_done} pages to {OUT_PATH}")
    finally:
        if drv:
            try:
                drv.quit()
            except Exception:
                pass

if __name__ == "__main__":
    sys.exit(run() or 0)

