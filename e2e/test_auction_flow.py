"""End-to-end test through the real UI (Playwright).

Needs the app running with seeded demo accounts:
    backend:  python -m scripts.seed && uvicorn app.main:app
    frontend: npm run dev            (or the single-container build on :8000)

    pip install -r e2e/requirements.txt && playwright install chromium
    E2E_BASE_URL=http://localhost:5173 pytest e2e
    (E2E_BROWSER_CHANNEL=msedge uses an installed Edge instead of downloading Chromium)
"""
import os
import re
import uuid
from datetime import date, datetime, timedelta

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:5173")
SHOTS = os.environ.get("E2E_SCREENSHOT_DIR")  # set to capture a frame per step (used to build the demo GIF)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL") or None)
        yield b
        b.close()


def new_page(browser: Browser) -> Page:
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.set_default_timeout(15_000)
    return page


_frame = 0


def shot(page: Page, name: str) -> None:
    global _frame
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        _frame += 1
        page.screenshot(path=os.path.join(SHOTS, f"{_frame:02d}-{name}.png"))


def sign_in_as(page: Page, demo_label: str) -> None:
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name=re.compile(demo_label)).click()
    expect(page.get_by_role("heading", name="British Auctions")).to_be_visible()


def local(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def test_buyer_creates_auction_supplier_bid_extends_it_live(browser: Browser):
    name = f"E2E Nagpur -> Surat {uuid.uuid4().hex[:5]}"

    # --- Buyer creates a British auction that closes in 6 minutes (already inside X = 10) ---
    buyer = new_page(browser)
    buyer.goto(f"{BASE}/login")
    shot(buyer, "login")
    sign_in_as(buyer, "Buyer")
    shot(buyer, "listing")
    buyer.get_by_role("link", name="Create RFQ").first.click()

    now = datetime.now()
    buyer.get_by_label("RFQ name").fill(name)
    buyer.get_by_label("Origin").fill("Nagpur")
    buyer.get_by_label("Destination").fill("Surat")
    buyer.get_by_label("Pickup / Service date").fill((date.today() + timedelta(days=3)).isoformat())
    buyer.get_by_label(re.compile(r"^Bid start")).fill(local(now - timedelta(minutes=1)))
    buyer.get_by_label(re.compile(r"^Bid close")).fill(local(now + timedelta(minutes=6)))
    buyer.get_by_label("Forced bid close").fill(local(now + timedelta(minutes=30)))
    buyer.get_by_label("Trigger window (X minutes)").fill("10")
    buyer.get_by_label("Extension duration (Y minutes)").fill("5")
    buyer.get_by_text("Lowest bidder (L1) change in last X minutes").click()
    shot(buyer, "create-rfq")
    buyer.get_by_role("button", name="Create RFQ").click()

    expect(buyer.get_by_role("heading", name=name)).to_be_visible()
    expect(buyer.get_by_text("Active", exact=True).first).to_be_visible()
    expect(buyer.get_by_text("Lowest bidder (L1) change in last X minutes").first).to_be_visible()
    rfq_url = buyer.url
    original_close = buyer.locator('.kv dt:text-is("Current bid close") + dd').inner_text()   # "Current bid close"

    # --- A second supplier is watching the same auction ---
    watcher = new_page(browser)
    sign_in_as(watcher, "BlueDart")
    watcher.goto(rfq_url)
    expect(watcher.locator(".empty-title", has_text="No bids yet")).to_be_visible()

    # --- Supplier bids inside the window: becomes L1, which extends the auction ---
    supplier = new_page(browser)
    sign_in_as(supplier, "Gati")
    supplier.goto(rfq_url)
    form = supplier.locator(".bid-card")
    form.get_by_label("Freight").fill("41000")
    form.get_by_label("Origin").fill("1500")
    form.get_by_label("Destination").fill("1200")
    expect(form.get_by_text(re.compile("will extend the auction by 5 min"))).to_be_visible()
    shot(supplier, "bid-preview")
    form.get_by_role("button", name="Submit quote").click()

    expect(form.get_by_text(re.compile(r"Bid placed: you are L1\. Auction extended"))).to_be_visible()
    expect(supplier.locator(".log").get_by_text("Time extended", exact=True)).to_be_visible()
    expect(supplier.locator(".log-reason").first).to_contain_text("Lowest bidder (L1) changed")
    shot(supplier, "extended")

    # --- The watcher's screen updated by itself (WebSocket), no reload ---
    expect(watcher.locator("tr.row-l1")).to_contain_text("Gati Express")
    expect(watcher.locator(".row-l1")).to_contain_text("43,700")
    expect(watcher.get_by_text(re.compile("Auction extended: now closes at"))).to_be_visible()
    shot(watcher, "watcher-live")

    # --- Rules enforced in the UI: a supplier can't raise their own price; buyers can't bid ---
    form.get_by_label("Freight").fill("50000")
    expect(form.get_by_text(re.compile("Must be below your current quote"))).to_be_visible()

    buyer.reload()
    expect(buyer.get_by_text("You're signed in as the buyer")).to_be_visible()
    assert buyer.locator('.kv dt:text-is("Current bid close") + dd').inner_text() != original_close   # close time moved
    shot(buyer, "buyer-view")
