import asyncio
import os
import re
import sys
from playwright.async_api import async_playwright

async def dump_reels(url):
    cookie_file = "cookies.txt"
    output_file = "reels_links.txt"
    
    print("==================================================")
    print("[INFO] Facebook Deep Reels Scraper (Standalone Mode)")
    print("==================================================")
    print(f"URL: {url}")
    print(f"Output: {output_file}")
    print("This script will scroll continuously and save links in real-time.")
    print("If it gets stuck, it will try to un-stick itself.")
    print("Press Ctrl+C at any time to stop and keep the links found so far.\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Run silently in background
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900},
            locale="th-TH"
        )
        
        # Load cookies
        cookies = []
        if os.path.exists(cookie_file):
            with open(cookie_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        parts = line.strip().split("\t")
                        if len(parts) >= 7:
                            cookies.append({
                                "domain": parts[0],
                                "path": parts[2],
                                "secure": parts[3].lower() == "true",
                                "expires": int(parts[4]) if parts[4] != "0" else None,
                                "name": parts[5],
                                "value": parts[6],
                            })
        
        valid_cookies = []
        for c in cookies:
            if c['expires'] is None:
                del c['expires']
            valid_cookies.append(c)
            
        await context.add_cookies(valid_cookies)
        
        page = await context.new_page()
        print("[INFO] Loading Facebook...", flush=True)
        
    # Determine creator identifier to avoid polluting links across different creators
    m_id = re.search(r'id=(\d+)', url) or re.search(r'facebook\.com/([^/?#]+)', url)
    creator_tag = m_id.group(1) if m_id else "creator"
    if creator_tag in ["profile.php", "watch", "reel", "reels"]:
        creator_tag = "creator"
    creator_links_file = f"reels_links_{creator_tag}.txt"

    # Start a clean set for this specific creator so foreign links from past runs are never mixed
    video_urls = set()
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        # Keep a timestamped or backup copy of old links so user never loses data
        try:
            shutil.copy2(output_file, "reels_links_previous.txt")
        except Exception:
            pass

    await page.goto(url, wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(5)
    
    print(f"[INFO] Target creator detected: {creator_tag}")
    print("[INFO] Starting isolated scroll (strictly ignoring suggested/recommended reels)...", flush=True)
    no_new_count = 0
    
    for i in range(1, 2500): # Safe upper bound
        prev_count = len(video_urls)
        
        # Extract URLs strictly from main profile container and check for Facebook recommendations boundary
        eval_result = await page.evaluate('''() => {
            const main = document.querySelector('div[role="main"]') || document.querySelector('div[role="feed"]') || document.body;
            
            // Markers that indicate Facebook has finished this profile's reels and transitioned into stranger recommendations
            const recommendationKeywords = [
                "แนะนำสำหรับคุณ", "วิดีโอแนะนำ", "reels แนะนำ", "โพสต์ที่คุณอาจชอบ", "แนะนำ", 
                "suggested for you", "suggested reels", "recommended for you", "more reels", 
                "explore more", "popular reels", "watch more reels"
            ];
            
            let suggestionBoundary = null;
            const headings = main.querySelectorAll('h2, h3, h4, span, div[role="heading"]');
            for (const h of headings) {
                const txt = (h.innerText || '').trim().toLowerCase();
                if (recommendationKeywords.some(k => txt === k || txt.startsWith(k))) {
                    suggestionBoundary = h;
                    break;
                }
            }
            
            const anchors = Array.from(main.querySelectorAll('a[href], [data-href]'));
            const validLinks = [];
            for (const a of anchors) {
                // If we hit recommendations boundary, ignore all subsequent links in the DOM
                if (suggestionBoundary && (suggestionBoundary.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) {
                    continue;
                }
                // Exclude links inside dialogs, sidebars, banners, or navigation
                if (a.closest('div[role="dialog"], div[role="complementary"], div[role="navigation"], div[role="banner"]')) {
                    continue;
                }
                const href = a.href || a.getAttribute('data-href') || '';
                if (href) validLinks.push(href);
            }
            return {
                links: validLinks,
                reachedSuggestions: !!suggestionBoundary
            };
        }''')
        
        for a_href in eval_result.get("links", []):
            clean = a_href.split('?')[0].rstrip('/')
            m = re.search(r'/(?:reel|reels|video|videos)/(\d+)', clean)
            if m and len(m.group(1)) >= 8:
                video_urls.add(f"https://www.facebook.com/reel/{m.group(1)}")
        
        curr_count = len(video_urls)
        
        if curr_count > prev_count:
            no_new_count = 0
            new_found = curr_count - prev_count
            print(f"[SUCCESS] Scroll {i}: Found {new_found} new clips of {creator_tag}. Total: {curr_count}", flush=True)
            
            # Save to file immediately (both global reels_links.txt and creator-specific file)
            with open(output_file, "w", encoding="utf-8") as f:
                for v in sorted(list(video_urls)):
                    f.write(v + "\n")
            with open(creator_links_file, "w", encoding="utf-8") as f:
                for v in sorted(list(video_urls)):
                    f.write(v + "\n")
        else:
            no_new_count += 1
            print(f"[SEARCHING] Scroll {i}: Checking next batch... ({no_new_count}/25)", flush=True)
            
            # Un-stick logic
            try:
                await page.evaluate("window.scrollBy(0, -2000);")
                await page.keyboard.press("PageUp")
                await asyncio.sleep(1.5)
            except Exception:
                pass
            
        # Stop immediately if Facebook reached the recommendation boundary
        if eval_result.get("reachedSuggestions"):
            print(f"\n[STOP] Reached end of creator's reels (Facebook 'Suggested Reels' / แนะนำสำหรับคุณ detected).", flush=True)
            print(f"[INFO] Stopping cleanly to ensure zero foreign clips are mixed in! Total clips: {curr_count}", flush=True)
            break
            
        if no_new_count >= 25:
            print(f"\n[STOP] Reached the end of this creator's video feed after {no_new_count} scrolls without new clips. Total gathered: {curr_count}", flush=True)
            break
            
        await page.keyboard.press("PageDown")
        await page.keyboard.press("End")
        await page.mouse.wheel(0, 5000)
        await asyncio.sleep(3.0) # Wait for Facebook to render
        
    await browser.close()
    print(f"\n[DONE] All {len(video_urls)} clips of {creator_tag} saved cleanly to {output_file} and {creator_links_file}", flush=True)
    print("[INFO] You can now copy all links from reels_links.txt to download them without any mixed clips!")

if __name__ == "__main__":
    url_to_scrape = "https://www.facebook.com/profile.php?id=100050575355583&sk=reels_tab"
    if len(sys.argv) > 1:
        url_to_scrape = sys.argv[1]
        
    try:
        asyncio.run(dump_reels(url_to_scrape))
    except KeyboardInterrupt:
        print("\n[STOP] Stopped by user. Your links are safely saved in reels_links.txt")
