"""Regenerate the README screenshots and docs/demo.gif by driving the real app.

    python -m scripts.seed --reset            (in backend/, so the demo data is fresh)
    pip install -r e2e/requirements.txt pillow
    E2E_BASE_URL=http://localhost:8000 python e2e/record_demo.py
"""
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:5173")
DOCS = Path(__file__).resolve().parent.parent / "docs"
SHOTS = DOCS / "screenshots"
VIEW = {"width": 1440, "height": 900}

frames: list[tuple[Path, int]] = []   # (png, milliseconds on screen)


def capture(page: Page, name: str, hold_ms: int = 2200, full_page: bool = False, keep: bool = False) -> None:
    path = (SHOTS if keep else DOCS / ".frames") / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(400)
    page.screenshot(path=str(path), full_page=full_page)
    if not full_page:
        frames.append((path, hold_ms))


def sign_in(page: Page, label: str) -> None:
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name=re.compile(label)).click()
    expect(page.get_by_role("heading", name="British Auctions")).to_be_visible()


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL") or None)
        light = {"viewport": VIEW, "color_scheme": "light"}

        buyer = browser.new_context(**light).new_page()
        buyer.goto(f"{BASE}/login")
        expect(buyer.get_by_text("Demo accounts")).to_be_visible()
        capture(buyer, "login", keep=True)

        sign_in(buyer, "Buyer")
        capture(buyer, "listing", hold_ms=3000, keep=True)

        buyer.get_by_role("link", name=re.compile("Chennai")).click()
        expect(buyer.get_by_text("Force closed at")).to_be_visible()
        capture(buyer, "details-force-closed", hold_ms=3000)
        capture(buyer, "details", full_page=True, keep=True)

        # Create an auction that is already inside its trigger window.
        buyer.get_by_role("link", name="Create RFQ").first.click()
        now = datetime.now()
        fmt = "%Y-%m-%dT%H:%M"
        buyer.get_by_label("RFQ name").fill("Nagpur -> Surat | 32ft MXL, express")
        buyer.get_by_label("Origin").fill("Nagpur (MIHAN)")
        buyer.get_by_label("Destination").fill("Surat (Sachin GIDC)")
        buyer.get_by_label("Pickup / Service date").fill((date.today() + timedelta(days=3)).isoformat())
        buyer.get_by_label(re.compile(r"^Bid start")).fill((now - timedelta(minutes=30)).strftime(fmt))
        buyer.get_by_label(re.compile(r"^Bid close")).fill((now + timedelta(minutes=4)).strftime(fmt))
        buyer.get_by_label("Forced bid close").fill((now + timedelta(minutes=25)).strftime(fmt))
        buyer.get_by_text("Lowest bidder (L1) change in last X minutes").click()
        capture(buyer, "create-rfq", hold_ms=3000, keep=True)
        buyer.get_by_role("button", name="Create RFQ").click()
        expect(buyer.get_by_text("Active", exact=True).first).to_be_visible()
        rfq_url = buyer.url

        # Two suppliers bid inside the window. Both change the L1 (the first bid creates one), so both extend.
        for label, freight, shot in (("BlueDart", "52000", None), ("Gati", "49500", "supplier-bid")):
            sup = browser.new_context(**light).new_page()
            sign_in(sup, label)
            sup.goto(rfq_url)
            form = sup.locator(".bid-card")
            form.get_by_label("Freight").fill(freight)
            form.get_by_label("Origin").fill("1800")
            form.get_by_label("Destination").fill("1500")
            if shot:
                expect(form.get_by_text(re.compile("will extend the auction"))).to_be_visible()
                capture(sup, shot, hold_ms=3200)
            form.get_by_role("button", name=re.compile("Submit quote")).click()
            expect(form.get_by_text(re.compile("Bid placed"))).to_be_visible()
            if shot:
                expect(sup.locator(".log-reason").first).to_be_visible()
                capture(sup, "supplier-extended", hold_ms=3600)
                capture(sup, "live-auction", full_page=True, keep=True)

        # The buyer's screen updated live (WebSocket).
        expect(buyer.get_by_text(re.compile("Auction extended: now closes at"))).to_be_visible()
        capture(buyer, "buyer-live-update", hold_ms=4000)
        browser.close()

    images = []
    for path, _ in frames:
        im = Image.open(path).convert("RGB")
        im = im.resize((1100, round(im.height * 1100 / im.width)), Image.LANCZOS)
        images.append(im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    images[0].save(DOCS / "demo.gif", save_all=True, append_images=images[1:],
                   duration=[ms for _, ms in frames], loop=0, optimize=True)
    for path, _ in frames:
        if path.parent.name == ".frames":
            path.unlink()
    (DOCS / ".frames").rmdir()
    print(f"Wrote {DOCS / 'demo.gif'} ({len(frames)} frames) and screenshots in {SHOTS}")


if __name__ == "__main__":
    main()
