import asyncio, random, time
from typing import Iterable
from pathlib import Path
from playwright.async_api import async_playwright, Response, Route
from playwright_stealth import stealth_async

# --------------------------------------------------------------------------- #
# Configuration helpers
# --------------------------------------------------------------------------- #

# A small pool of realistic desktop + mobile user agents; extend as you like.
UA_POOL: Iterable[str] = [
    # Chrome desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome mobile
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

# File extensions we *usually* don’t need for text extraction
MEDIA_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".svg",
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    ".mp3",
    ".ogg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)

# --------------------------------------------------------------------------- #
# Core async worker
# --------------------------------------------------------------------------- #


async def _fetch_html_async(
    url: str,
    *,
    wait_until: str = "networkidle",
    scroll: bool = True,
    stealth: bool = False,
    block_media: bool = False,
    retry_403: bool = False,
    max_retries: int = 2,
) -> str:
    """
    Fetch fully rendered HTML with optional anti-bot, stealth and media-blocking.

    * stealth=True     → random UA, realistic locale/viewport/timezone, WebGL tricks
    * block_media=True → abort requests for images/video/fonts
    * retry_403=True   → if first visit yields 403, retry w/ alt UA + no-cache headers
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # ----- build context options ------------------------------------------------
        context_opts = {}
        if stealth:
            context_opts |= {
                "user_agent": random.choice(tuple(UA_POOL)),
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "viewport": {"width": 1366, "height": 768},
                # ↓ fingerprint tweaks
                "color_scheme": "light",
            }

        context = await browser.new_context(**context_opts)
        page = await context.new_page()

        # ── DEEPER stealth patch (optional) ──────────────────────────────────
        if stealth:
            await stealth_async(page)  # masks WebGL, navigator.plugins, etc.

        # ----- request interception -------------------------------------------------
        if block_media:
            await page.route(
                "**/*",
                lambda route: _maybe_abort_media(route, MEDIA_EXTENSIONS),
            )

        if retry_403:
            await _inject_403_retry_logic(page, max_retries)

        # ----- main navigation ------------------------------------------------------
        await page.goto(url, wait_until=wait_until)

        if scroll:
            await _auto_scroll(page)

        html = await page.content()
        await browser.close()
        return html


# --------------------------------------------------------------------------- #
# Public sync wrapper
# --------------------------------------------------------------------------- #


def fetch_html(
    url: str,
    **kwargs,
) -> str:
    return asyncio.run(_fetch_html_async(url, **kwargs))


# --------------------------------------------------------------------------- #
# Utility helpers
# --------------------------------------------------------------------------- #


async def _auto_scroll(page):
    """Quick ‘scroll to bottom’ helper to trigger lazy loads."""
    await page.evaluate(
        """
        () => new Promise(res => {
            const dist = 1024, delay = 40;
            let scrolled = 0;
            const timer = setInterval(() => {
                window.scrollBy(0, dist);
                scrolled += dist;
                if (scrolled >= document.body.scrollHeight) {
                    clearInterval(timer);
                    setTimeout(res, 400);
                }
            }, delay);
        })
        """
    )


def _maybe_abort_media(route: Route, banned_exts: Iterable[str]):
    """Abort media/font requests to save bandwidth."""
    url = route.request.url.lower()
    if any(url.endswith(ext) for ext in banned_exts):
        return asyncio.create_task(route.abort())
    return asyncio.create_task(route.continue_())


async def _inject_403_retry_logic(page, max_retries: int):
    """
    Listens for 403 responses. If encountered, it:
      1. Cancels further loading
      2. Picks a new UA + adds ‘Cache-Control: no-cache’
      3. Retries navigation (up to *max_retries*)
    """
    attempts = {"count": 0}

    async def on_response(resp: Response):
        if resp.status != 403:
            return
        if attempts["count"] >= max_retries:
            return
        attempts["count"] += 1

        print(f"[403] Retry #{attempts['count']} for {resp.url}")
        # Pick a fresh UA
        new_ua = random.choice(tuple(UA_POOL))
        await page.context.set_extra_http_headers({"Cache-Control": "no-cache"})
        await page.context.set_user_agent(new_ua)

        # Small back-off before retrying
        await asyncio.sleep(0.8 * attempts["count"])
        await page.goto(resp.url, wait_until="networkidle")

    page.on("response", on_response)


# --------------------------------------------------------------------------- #
# Example usage (remove or guard behind `if __name__ == "__main__":` in prod)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    from pathlib import Path
    from urllib.parse import urlparse
    from datetime import datetime

    # Prompt the user for a URL
    url = input("Please enter the URL to fetch: ").strip()
    if not url:
        print("Error: no URL provided.")
        exit(1)

    html = fetch_html(
        url,
        stealth=True,
        block_media=True,
        retry_403=True,
    )

    # ── build output path ──
    project_root = (
        Path(__file__).resolve().parent.parent
    )  #  ↑ one level up from scrapers/
    out_dir = project_root / "sources" / "html"
    out_dir.mkdir(parents=True, exist_ok=True)

    # filename: <host>-YYYYMMDD-HHMMSS.html
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    host = urlparse(url).hostname.replace(".", "_")
    out_file = out_dir / f"{host}-{ts}.html"

    out_file.write_text(html, encoding="utf-8")
    print(f"Saved rendered HTML →  {out_file.relative_to(project_root)}")
