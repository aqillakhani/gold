"""Record TikTok demo video using Playwright screen recording."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright

DEMO_BASE = "https://aqillakhani.github.io/gold-platform-site/demo"
OUTPUT = Path("data/media/demo/tiktok_demo_recording.webm")


async def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(OUTPUT.parent),
            record_video_size={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Step 1: Dashboard
        print("1/6 Dashboard...")
        await page.goto(f"{DEMO_BASE}/index.html", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        # Step 2: Connected Accounts
        print("2/6 Connected Accounts...")
        await page.goto(f"{DEMO_BASE}/accounts.html", wait_until="networkidle")
        await page.wait_for_timeout(2500)

        # Click "+ Connect Platform" to show OAuth modal
        print("   Clicking Connect Platform...")
        await page.click("text=Connect Platform")
        await page.wait_for_timeout(2500)

        # Click "Authorize with TikTok"
        print("   Clicking Authorize with TikTok...")
        await page.click("text=Authorize with TikTok")
        await page.wait_for_timeout(1000)

        # Step 3: TikTok OAuth
        print("3/6 TikTok OAuth...")
        await page.wait_for_url(f"**tiktok_oauth**", timeout=5000)
        await page.wait_for_timeout(2500)

        # Click Authorize
        print("   Clicking Authorize App...")
        await page.click("text=Authorize App")
        await page.wait_for_timeout(3500)  # Wait for loading animation + redirect

        # Step 4: OAuth Success
        print("4/6 OAuth Success...")
        await page.wait_for_url(f"**oauth_success**", timeout=5000)
        await page.wait_for_timeout(3000)

        # Click Continue to Upload
        print("   Clicking Continue to Upload...")
        await page.click("text=Continue to Upload")
        await page.wait_for_timeout(1000)

        # Step 5: Upload page
        print("5/6 Upload Content...")
        await page.wait_for_url(f"**upload**", timeout=5000)
        await page.wait_for_timeout(3000)

        # Click Publish
        print("   Clicking Publish...")
        await page.click("text=Publish to All Platforms")
        await page.wait_for_timeout(8000)  # Wait for progress animation + redirect

        # Step 6: Publish Success
        print("6/6 Publish Success...")
        await page.wait_for_url(f"**publish_success**", timeout=10000)
        await page.wait_for_timeout(4000)

        # Close to finalize video
        await context.close()
        await browser.close()

    # Find the recorded video file
    video_files = sorted(OUTPUT.parent.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    if video_files:
        latest = video_files[-1]
        if latest != OUTPUT:
            latest.rename(OUTPUT)
        print(f"\nRecording saved: {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KB)")
    else:
        print("ERROR: No video file found!")


if __name__ == "__main__":
    asyncio.run(main())
