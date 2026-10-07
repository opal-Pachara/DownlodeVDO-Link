import os
import asyncio
import re
import json
import logging
from urllib.parse import urlparse, urlunparse
from playwright.async_api import async_playwright
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

logger = logging.getLogger("FacebookScraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

def clean_fb_url(url: str) -> str:
    """Removes tracking parameters from Facebook Reel/Video links to avoid duplicates."""
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        return urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))
    except Exception:
        return url

def sanitize_folder_name(name: str) -> str:
    """Sanitizes strings to be safe for OS directory names."""
    if not name or not str(name).strip():
        return "Facebook_Page"
    name = str(name).replace('\xa0', ' ').strip()
    name = re.sub(r'^\(\d+\+?\)\s*', '', name).strip()
    name = re.sub(r'(\|\s*Facebook|[\-\|\•]\s*Reels|[\-\|\•]\s*Videos|\|.*$)', '', name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean_name if clean_name and clean_name != "Facebook_Page" else "Facebook_Page"

def extract_urls_from_text(text: str) -> list[str]:
    """
    Scans raw text, HTML, or multi-line strings (e.g. from a Cmd+A copy on a browser page)
    to discover and extract all unique video and Reel URLs automatically.
    """
    if not text:
        return []
    # Regex to capture standard video clip links across supported platforms
    url_pattern = re.compile(
        r'(https?://(?:www\.|m\.|mbasic\.|l\.)?(?:facebook\.com|instagram\.com|tiktok\.com|douyin\.com|iesdouyin\.com|reddit\.com)/(?:[^/"\'\s]+/videos/[^/"\'\s]+|reel/[^/"\'\s]+|reels/[^/"\'\s]+|watch/?\?[^\s"\'<>]+|@[^/"\'\s]+/video/[^/"\'\s]+|p/[^/"\'\s]+|v/[^/"\'\s]+|video/[^/"\'\s]+|note/[^/"\'\s]+|r/[^/"\'\s]+/comments/[^/"\'\s]+|comments/[^/"\'\s]+|[^\s"\'<>]+))|'
        r'(https?://(?:fb\.watch|v\.douyin\.com|redd\.it|v\.redd\.it)/[^\s"\'<>]+)',
        re.IGNORECASE
    )
    matches = url_pattern.findall(text)
    discovered = set()
    for m in matches:
        raw_url = m[0] or m[1]
        if raw_url:
            if any(junk in raw_url.lower() for junk in ["notif", "comment_id=", "ref=notif"]):
                continue
            clean = raw_url.split('?')[0].rstrip('/')
            # Avoid generic page routes or static navigation links
            if any(k in clean.lower() for k in ['/reel/', '/videos/', '/watch', 'fb.watch', '/video/', '/p/', 'v.douyin.com', 'douyin.com', 'note/', '/comments/', 'redd.it', 'v.redd.it']):
                discovered.add(clean)
    return list(discovered)

def load_netscape_cookies(cookie_file: str) -> list[dict]:
    """Parses a standard netscape cookies.txt file into Playwright-compatible cookie dictionaries."""
    cookies = []
    if not os.path.exists(cookie_file) or not os.path.isfile(cookie_file):
        return cookies
    try:
        with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    domain, flag, path, secure, expiry, name, value = parts[:7]
                    cookie_obj = {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path,
                        "secure": secure.lower() == "true",
                    }
                    try:
                        exp_int = int(expiry)
                        if exp_int > 0:
                            cookie_obj["expires"] = exp_int
                    except ValueError:
                        pass
                    cookies.append(cookie_obj)
        logger.info(f"Loaded {len(cookies)} cookies from {cookie_file}")
    except Exception as e:
        logger.warning(f"Failed to load Netscape cookies: {e}")
    return cookies

def get_auto_browser_cookies(domain: str = "facebook.com") -> list[dict]:
    """Automatically extracts session cookies from local browsers (Chrome, Edge, Safari, Firefox) to bypass login walls."""
    cookies = []
    try:
        import browser_cookie3
        # Attempt Chrome first as it is most commonly used
        for browser_fn, name in [(browser_cookie3.chrome, "Chrome"), (browser_cookie3.firefox, "Firefox"), (browser_cookie3.edge, "Edge"), (browser_cookie3.safari, "Safari")]:
            try:
                cj = browser_fn(domain_name=domain)
                for c in cj:
                    cookies.append({
                        "name": c.name,
                        "value": c.value,
                        "domain": c.domain if c.domain.startswith(".") else "." + c.domain.lstrip("."),
                        "path": c.path,
                        "secure": bool(c.secure),
                    })
                if cookies:
                    logger.info(f"Successfully loaded {len(cookies)} cookies from {name} for {domain}")
                    break
            except Exception as err:
                logger.debug(f"Could not load cookies from {name}: {err}")
    except ImportError:
        logger.warning("browser_cookie3 package not installed; skipping auto cookie extraction.")
    except Exception as e:
        logger.warning(f"Unexpected error during auto cookie extraction: {e}")
    return cookies

def get_facebook_harvest_targets(url: str) -> list[str]:
    """Generates Reels and Videos tab URLs to ensure 100% video harvest."""
    u = url.split("?")[0].rstrip("/")
    if "/reel/" in u or ("/videos/" in u and not u.endswith("/videos")):
        return [url]
    
    parsed = urlparse(url)
    targets = []
    if "profile.php" in parsed.path:
        from urllib.parse import parse_qs
        qs = parse_qs(parsed.query)
        if 'id' in qs:
            pid = qs['id'][0]
            targets.append(f"https://www.facebook.com/profile.php?id={pid}&sk=reels_tab")
            targets.append(f"https://www.facebook.com/profile.php?id={pid}&sk=videos")
    else:
        path = parsed.path.rstrip('/')
        base_path = re.sub(r'/(?:reels|reels_tab|videos)$', '', path, flags=re.IGNORECASE)
        base_url = f"https://www.facebook.com{base_path}"
        targets.append(f"{base_url}/reels/")
        targets.append(f"{base_url}/videos/")
    
    if url not in targets:
        targets.insert(0, url)
    return list(dict.fromkeys(targets))


async def scrape_graphql_cursor(page, video_urls: set, graphql_token_holder: dict):
    """
    Extracts the GraphQL __req token and pagination cursor from live network traffic,
    then directly calls Facebook's GraphQL API endpoint with cursor pagination.
    Each GraphQL page returns ~24 video IDs — far faster than browser scrolling.
    
    graphql_token_holder is a shared dict passed by reference so the browser
    response handler can push token + cursor data into it for this function to use.
    """
    import urllib.request
    import urllib.parse
    
    token = graphql_token_holder.get("token")
    cursor = graphql_token_holder.get("cursor")
    doc_id = graphql_token_holder.get("doc_id")
    variables_template = graphql_token_holder.get("variables")
    fb_dtsg = graphql_token_holder.get("fb_dtsg", "")
    
    if not token or not cursor or not variables_template:
        logger.info("GraphQL cursor pagination: no token/cursor available — browser scroll will handle harvest.")
        return
    
    logger.info(f"GraphQL cursor pagination: starting direct API harvest from cursor={cursor[:30]}...")
    consecutive_empty = 0
    pages_fetched = 0
    
    while consecutive_empty < 5:
        try:
            # Build GraphQL POST payload with updated cursor
            try:
                vars_dict = json.loads(variables_template)
                vars_dict["cursor"] = cursor
                vars_dict["count"] = 24
                updated_vars = json.dumps(vars_dict)
            except Exception:
                updated_vars = variables_template
            
            post_data = urllib.parse.urlencode({
                "variables": updated_vars,
                "doc_id": doc_id or "",
                "fb_dtsg": fb_dtsg,
                "__req": token,
                "__a": "1",
                "__comet_req": "15",
            }).encode()
            
            req = urllib.request.Request(
                "https://www.facebook.com/api/graphql/",
                data=post_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "X-FB-Friendly-Name": "CometProfileReelsTabFeedQuery",
                    "Accept": "*/*",
                }
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            
            # Extract video IDs from GraphQL response
            prev_count = len(video_urls)
            for m in re.findall(r'"video_id":"(\d+)"', raw):
                if len(m) >= 8: video_urls.add(f"https://www.facebook.com/reel/{m}")
            for m in re.findall(r'/reel/(\d+)', raw):
                if len(m) >= 8: video_urls.add(f"https://www.facebook.com/reel/{m}")
            for m in re.findall(r'"post_id":"(\d+)"', raw):
                if len(m) >= 8: video_urls.add(f"https://www.facebook.com/reel/{m}")
            for m in re.findall(r'"story_id":"(\d+)"', raw):
                if len(m) >= 8: video_urls.add(f"https://www.facebook.com/reel/{m}")
            
            new_found = len(video_urls) - prev_count
            pages_fetched += 1
            
            # Try to extract next cursor
            next_cursor_match = re.search(r'"end_cursor"\s*:\s*"([^"]+)"', raw)
            has_next_match = re.search(r'"has_next_page"\s*:\s*(true|false)', raw)
            has_next = has_next_match and has_next_match.group(1) == "true" if has_next_match else False
            
            if next_cursor_match and has_next:
                cursor = next_cursor_match.group(1)
                graphql_token_holder["cursor"] = cursor
                logger.info(f"GraphQL page {pages_fetched}: +{new_found} new videos (total={len(video_urls)}), cursor advanced.")
                consecutive_empty = 0 if new_found > 0 else consecutive_empty + 1
            else:
                logger.info(f"GraphQL cursor: no more pages after {pages_fetched} pages (has_next={has_next}).")
                break
                
            await asyncio.sleep(0.8)  # Polite rate limiting
            
        except Exception as e:
            logger.warning(f"GraphQL cursor page {pages_fetched} failed: {e}")
            consecutive_empty += 1
            await asyncio.sleep(2.0)
    
    logger.info(f"GraphQL cursor harvest finished. Fetched {pages_fetched} pages, total IDs so far: {len(video_urls)}")


async def scrape_facebook_page(url: str, max_scrolls: int = 1500, cookie_file: str = None) -> dict:
    logger.info(f"Starting deep brute-force scrape for Facebook Page/Profile URL: {url} (max_scrolls={max_scrolls})")
    video_urls = set()
    page_name = "Facebook_Page"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 900},
                locale="th-TH"
            )
            
            # 1. Load session cookies from local browser and cookies.txt
            cookie_list = get_auto_browser_cookies("facebook.com")
            if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                file_cookies = load_netscape_cookies(cookie_file)
                cookie_list.extend(file_cookies)
                
            has_login = any(c.get('name') == 'c_user' for c in cookie_list)
            if not has_login:
                logger.warning("Facebook session 'c_user' cookie not detected. Facebook limits guest scrolling on Reels/Feed to ~110 items. Log in via cookies.txt to harvest unlimited thousands of clips.")
                
            if cookie_list:
                cookie_dict = {}
                for c in cookie_list:
                    key = (c['name'], c.get('domain', ''))
                    cookie_dict[key] = c
                try:
                    await context.add_cookies(list(cookie_dict.values()))
                    logger.info(f"Injected {len(cookie_dict)} session cookies into Facebook context.")
                except Exception as e:
                    logger.warning(f"Error injecting cookies: {e}")
                    
            page = await context.new_page()

            # Shared dict for GraphQL cursor pagination tokens extracted from live network traffic
            graphql_token_holder = {}

            # 2. Intercept GraphQL & AJAX network responses to capture 100% of reels even when DOM nodes unmount
            async def on_response(response):
                try:
                    ct = response.headers.get("content-type", "")
                    url_lower = response.url.lower()
                    if "application/json" in ct or "text/javascript" in ct or "graphql" in url_lower or "api/graphql" in url_lower:
                        body = await response.text()

                        # Capture all known Facebook video ID patterns from GraphQL payloads
                        all_matches = set()
                        all_matches.update(re.findall(r'"video_id":"(\d+)"', body))
                        all_matches.update(re.findall(r'/reel/(\d+)', body))
                        all_matches.update(re.findall(r'"post_id":"(\d+)"', body))
                        all_matches.update(re.findall(r'"story_id":"(\d+)"', body))
                        all_matches.update(re.findall(r'"node_id":"(\d+)"', body))
                        all_matches.update(re.findall(r'"id":"(\d{10,})"', body))
                        all_matches.update(re.findall(r'video/(\d+)', body))
                        all_matches.update(re.findall(r'reels/(\d+)', body))
                        all_matches.update(re.findall(r'fb\.watch/([A-Za-z0-9_\-]+)', body))
                        for m in all_matches:
                            if len(m) >= 8:
                                video_urls.add(f"https://www.facebook.com/reel/{m}")

                        # --- Extract GraphQL cursor pagination tokens for direct API calls ---
                        # Only capture if it looks like a Reels/Videos feed response
                        if ("end_cursor" in body or "has_next_page" in body) and "video_id" in body:
                            # fb_dtsg token (anti-CSRF)
                            if not graphql_token_holder.get("fb_dtsg"):
                                dtsg_m = re.search(r'"DTSGInitialData".*?"token"\s*:\s*"([^"]+)"', body)
                                if not dtsg_m:
                                    dtsg_m = re.search(r'"fb_dtsg"\s*:\s*\{"value"\s*:\s*"([^"]+)"', body)
                                if dtsg_m:
                                    graphql_token_holder["fb_dtsg"] = dtsg_m.group(1)

                            # __req token
                            if not graphql_token_holder.get("token"):
                                req_m = re.search(r'"__req"\s*:\s*"([^"]+)"', body)
                                if req_m:
                                    graphql_token_holder["token"] = req_m.group(1)
                                else:
                                    graphql_token_holder["token"] = "r"  # common default

                            # doc_id (identifies the GraphQL query)
                            if not graphql_token_holder.get("doc_id"):
                                doc_m = re.search(r'"doc_id"\s*:\s*"(\d+)"', body)
                                if doc_m:
                                    graphql_token_holder["doc_id"] = doc_m.group(1)

                            # Pagination cursor (end_cursor of the current page → next page)
                            cursor_m = re.search(r'"end_cursor"\s*:\s*"([^"]+)"', body)
                            if cursor_m:
                                graphql_token_holder["cursor"] = cursor_m.group(1)

                            # Variables template (for re-submitting with next cursor)
                            if not graphql_token_holder.get("variables"):
                                vars_m = re.search(r'"variables"\s*:\s*(\{[^}]{20,}\})', body)
                                if vars_m:
                                    graphql_token_holder["variables"] = vars_m.group(1)

                except Exception:
                    pass

            page.on("response", on_response)

            
            targets = get_facebook_harvest_targets(url)
            # Add mbasic (lightweight mobile) fallback variant for each target — bypasses React virtual DOM virtualization
            mbasic_targets = []
            for t in targets:
                mb = t.replace("https://www.facebook.com", "https://mbasic.facebook.com").replace("https://facebook.com", "https://mbasic.facebook.com")
                if mb not in targets:
                    mbasic_targets.append(mb)
            targets = targets + mbasic_targets
            logger.info(f"Identified {len(targets)} Facebook target tabs to scrape (incl. mbasic fallback): {targets}")
            
            for tab_idx, target_tab_url in enumerate(targets, start=1):
                logger.info(f"Scraping Facebook tab [{tab_idx}/{len(targets)}]: {target_tab_url}")
                try:
                    await page.goto(target_tab_url, wait_until='domcontentloaded', timeout=45000)
                except Exception as e:
                    logger.warning(f"Goto warning for {target_tab_url}: {e}")
                await asyncio.sleep(4)
                
                # Extract creator title on first valid tab
                if page_name == "Facebook_Page":
                    try:
                        raw_title = await page.evaluate("() => document.querySelector('div[role=\"main\"] h1')?.innerText || document.querySelector('div[role=\"main\"] h2')?.innerText || document.querySelector('meta[property=\"og:title\"]')?.content || document.title")
                        clean = sanitize_folder_name(str(raw_title))
                        if clean and clean != "Facebook_Page" and "แชท" not in clean and "การแจ้งเตือน" not in clean:
                            page_name = clean
                        else:
                            parsed = urlparse(target_tab_url)
                            path_parts = [p for p in parsed.path.split('/') if p]
                            if path_parts:
                                page_name = sanitize_folder_name(path_parts[0])
                    except Exception:
                        pass
                    
                # Parse initial embedded script tags (SSR payload)
                try:
                    script_contents = await page.evaluate('''() => {
                        const scripts = Array.from(document.querySelectorAll('script[type="application/json"]'));
                        return scripts.map(s => s.textContent || '');
                    }''')
                    for sc in script_contents:
                        matches = re.findall(r'"video_id":"(\d+)"', sc)
                        matches += re.findall(r'/reel/(\d+)', sc)
                        for m in matches:
                            if len(m) >= 8:
                                video_urls.add(f"https://www.facebook.com/reel/{m}")
                except Exception:
                    pass
                    
                # Continuous multi-strategy scroll & popup removal
                no_new_count = 0
                consecutive_big_scrolls = 0
                for scroll_idx in range(max_scrolls):
                    prev_count = len(video_urls)
                    
                    # Dismiss modal/dialog overlays and restore body scrollability
                    await page.evaluate('''() => {
                        const closeSelectors = [
                            'div[aria-label="Close"]', 'div[aria-label="ปิด"]',
                            'div[role="button"][aria-label="Close"]', 'div[role="button"][aria-label="ปิด"]',
                            'div[aria-label="Decline optional cookies"]', 'div[aria-label="Allow all cookies"]',
                            'div[aria-label="Not now"]', 'div[aria-label="ไม่ใช่ตอนนี้"]'
                        ];
                        for (const sel of closeSelectors) {
                            const el = document.querySelector(sel);
                            if (el) { try { el.click(); } catch (e) {} }
                        }
                        const dialogs = document.querySelectorAll('div[role="dialog"], div[data-pagelet="root"] + div');
                        dialogs.forEach(d => {
                            const text = d.innerText || '';
                            if (text.includes("เข้าสู่ระบบ") || text.includes("Log In") || text.includes("ดูเพิ่มเติมบน Facebook")) {
                                d.remove();
                            }
                        });
                        document.body.style.overflow = 'auto';
                        document.body.style.position = 'relative';
                        document.documentElement.style.overflow = 'auto';
                        window.scrollBy(0, 5000);
                        const elements = document.querySelectorAll('*');
                        for (let i = 0; i < elements.length; i++) {
                            const el = elements[i];
                            if (el.scrollHeight > el.clientHeight) {
                                const style = window.getComputedStyle(el);
                                if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                                    el.scrollTop += 5000;
                                    el.dispatchEvent(new Event('scroll', { bubbles: true }));
                                }
                            }
                        }
                    }''')
                    
                    # Extract DOM anchor links strictly from main feed container and check for Facebook recommendations boundary
                    eval_result = await page.evaluate('''() => {
                        const main = document.querySelector('div[role="main"]') || document.querySelector('div[role="feed"]') || document.body;
                        
                        // Indicators that Facebook has transitioned past creator's content into global suggestions
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
                        const results = [];
                        for (const a of anchors) {
                            // Ignore any anchors located after the suggested reels heading
                            if (suggestionBoundary && (suggestionBoundary.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) {
                                continue;
                            }
                            // Exclude sidebars, dialogs, banners, navigation
                            if (a.closest('div[role="dialog"], div[role="complementary"], div[role="navigation"], div[role="banner"]')) {
                                continue;
                            }
                            const href = a.href || a.getAttribute('data-href') || '';
                            if (href) results.push(href);
                        }
                        return {
                            links: results,
                            reachedSuggestions: !!suggestionBoundary
                        };
                    }''')
                    
                    found_anchors = eval_result.get("links", [])
                    for a_href in found_anchors:
                        clean = clean_fb_url(a_href)
                        if any(x in clean.lower() for x in ['/reel/', '/reels/', '/video/', '/videos/', 'watch?v=', 'fb.watch']):
                            if not any(clean.rstrip('/').endswith(x) for x in ['/reels', '/videos', '/watch', '/reel']):
                                m = re.search(r'/(?:reel|reels|video|videos)/(\d+)', clean)
                                if m and len(m.group(1)) >= 8:
                                    video_urls.add(f"https://www.facebook.com/reel/{m.group(1)}")
                                elif clean.startswith("http"):
                                    video_urls.add(clean)
                                    
                    curr_count = len(video_urls)
                    if curr_count > prev_count:
                        logger.info(f"Tab {tab_idx} Scroll {scroll_idx + 1}: Discovered {curr_count} total videos (+{curr_count - prev_count} new)")
                        no_new_count = 0
                        consecutive_big_scrolls = 0
                    else:
                        no_new_count += 1
                        consecutive_big_scrolls += 1
                        # Progressive unstick: small back-scroll first, then big jump, then reload
                        try:
                            if consecutive_big_scrolls % 5 == 0:
                                # Every 5 stalled scrolls: scroll way back up to reload virtualized content
                                await page.evaluate("window.scrollTo(0, 0);")
                                await asyncio.sleep(1.5)
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                                await asyncio.sleep(1.0)
                            else:
                                await page.evaluate("window.scrollBy(0, -2500);")
                                await page.keyboard.press("PageUp")
                                await asyncio.sleep(1.0)
                        except Exception:
                            pass
                        
                    # Stop immediately if recommendations appeared
                    if eval_result.get("reachedSuggestions"):
                        logger.info(f"Tab {tab_idx}: Detected end of creator's reels (Facebook recommendations boundary reached). Stopping tab scrape to prevent mixing foreign clips.")
                        break

                    if no_new_count >= 25:
                        logger.info(f"Tab {tab_idx}: No new videos for 25 consecutive scrolls. Tab complete with {curr_count} total videos.")
                        break
                        
                    await page.keyboard.press("PageDown")
                    await page.keyboard.press("End")
                    await page.mouse.wheel(0, 6000)
                    # Stagger sleep: fast when finding content, slower when stalled
                    await asyncio.sleep(1.8 if no_new_count == 0 else 2.8)

                    # After first 10 scrolls, try to launch GraphQL cursor pagination in parallel
                    if scroll_idx == 10 and graphql_token_holder.get("cursor"):
                        logger.info("🚀 Launching GraphQL cursor API harvest in parallel with browser scroll...")
                        asyncio.create_task(scrape_graphql_cursor(page, video_urls, graphql_token_holder))

            # Final GraphQL cursor sweep after all browser tabs are done
            if graphql_token_holder.get("cursor"):
                logger.info("🔄 Running final GraphQL cursor pagination sweep...")
                await scrape_graphql_cursor(page, video_urls, graphql_token_holder)

            await browser.close()
            logger.info(f"Scraping completed for '{page_name}'. Total videos found across all tabs: {len(video_urls)}")

            return {
                "success": True,
                "page_name": page_name,
                "video_urls": list(video_urls),
                "error": ""
            }
    except Exception as e:
        logger.error(f"Error scraping Facebook page: {e}")
        return {
            "success": False,
            "page_name": page_name,
            "video_urls": list(video_urls),
            "error": str(e)
        }

async def scrape_facebook_images(url: str, max_scrolls: int = 50, cookie_file: str = None) -> dict:
    """
    Automates a headless Chrome browser to scroll through a Facebook profile's photos tab,
    extracting high-resolution image URLs. Includes Deep Album Traversal to bypass 10-image limits.
    """
    logger.info(f"Starting deep headless image scrape for Facebook URL: {url} (max_scrolls={max_scrolls})")
    page_name = "Facebook_Page"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
                locale="th-TH"
            )
            
            cookie_list = get_auto_browser_cookies("facebook.com")
            if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                file_cookies = load_netscape_cookies(cookie_file)
                cookie_list.extend(file_cookies)
                
            if cookie_list:
                try:
                    await context.add_cookies(cookie_list)
                    logger.info(f"Injected {len(cookie_list)} session cookies into Playwright context.")
                except Exception as e:
                    logger.warning(f"Error injecting cookies: {e}")

            page = await context.new_page()
            
            # Step 1: Determine urls to scrape based on user input
            urls_to_scrape = [url]
            is_specific_photo_or_album = "set=a." in url.lower() or "/photo/" in url.lower() or "photo.php" in url.lower() or "fbid=" in url.lower()
            
            excluded_fbids = set()
            if not is_specific_photo_or_album:
                # We will build a blacklist of Profile and Cover photo fbids to exclude them from the main scrape
                from urllib.parse import urlparse, parse_qs
                import re
                parsed = urlparse(url)
                if "profile.php" in parsed.path:
                    qs = parse_qs(parsed.query)
                    if 'id' in qs:
                        albums_url = f"{parsed.scheme}://{parsed.netloc}/profile.php?id={qs['id'][0]}&sk=photos_albums"
                    else:
                        albums_url = url.split("?")[0].rstrip("/") + "/?sk=photos_albums" if "sk=" not in url else url
                else:
                    albums_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/?sk=photos_albums"
                    
                # Always ensure albums_url has sk=photos_albums
                if "sk=photos_albums" not in albums_url:
                    albums_url = re.sub(r'sk=[^&]+', 'sk=photos_albums', albums_url)

                logger.info(f"Finding Profile/Cover albums to exclude at {albums_url}")
                await page.goto(albums_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
                
                # Check for login wall
                login_wall = await page.evaluate('''() => {
                    const text = document.body.innerText;
                    return text.includes("อีเมลหรือหมายเลขโทรศัพท์มือถือ") && text.includes("รหัสผ่าน") && text.includes("เข้าสู่ระบบ");
                }''')
                
                if login_wall:
                    raise Exception("Facebook Login Wall detected! Your cookies are missing, invalid, or expired. Facebook requires an active login to scroll and load all images. Please update your cookies using the extension or log in to Facebook on Chrome.")
                    
                try:
                    close_buttons = page.locator("div[role='button']:has-text('Allow'), div[role='button']:has-text('Accept'), div[role='button']:has-text('Decline'), div[aria-label='Close']")
                    if await close_buttons.count() > 0:
                        await close_buttons.first.click(timeout=2000)
                except Exception:
                    pass

                exclude_album_links = set()
                album_links = set()
                
                for _ in range(4):
                    links = await page.evaluate('''() => {
                        const results = { excl: [], all: [] };
                        const anchors = Array.from(document.querySelectorAll('a'));
                        for (const a of anchors) {
                            const href = a.href || '';
                            if (!href.includes('set=a.')) continue;
                            
                            results.all.push(href);
                            
                            let text = (a.innerText || '').toLowerCase() + ' ' + (a.getAttribute('aria-label') || '').toLowerCase();
                            let parent = a.parentElement;
                            if (parent && parent.innerText) {
                                text += ' ' + parent.innerText.toLowerCase();
                            }
                            
                            if (text.includes('profile') || text.includes('cover') || text.includes('โปรไฟล์') || text.includes('ปก') || text.includes('หน้าปก')) {
                                results.excl.push(href);
                            }
                        }
                        return results;
                    }''')
                    
                    # Normalize links to grid views
                    for l in links['excl']:
                        if '/photo' in l and 'set=a.' in l:
                            m = re.search(r'set=(a\.\d+)', l)
                            if m:
                                exclude_album_links.add(f"https://www.facebook.com/media/set/?set={m.group(1)}&type=3")
                        else:
                            exclude_album_links.add(l)
                            
                    for l in links['all']:
                        if '/photo' in l and 'set=a.' in l:
                            m = re.search(r'set=(a\.\d+)', l)
                            if m:
                                album_links.add(f"https://www.facebook.com/media/set/?set={m.group(1)}&type=3")
                        else:
                            album_links.add(l)
                            
                    await page.keyboard.press('End')
                    await asyncio.sleep(1.5)
                    
                clean_exclude_links = exclude_album_links
                        
                for excl_url in clean_exclude_links:
                    logger.info(f"Extracting fbids from excluded album: {excl_url}")
                    await page.goto(excl_url, wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3)
                    for _ in range(3):
                        try:
                            fbids = await page.evaluate(r'''() => {
                                const imgs = Array.from(document.querySelectorAll('img'));
                                return imgs.map(img => {
                                    const a = img.closest('a');
                                    if (!a) return null;
                                    const href = a.href || '';
                                    const match = href.match(/fbid=(\d+)/);
                                    return match ? match[1] : null;
                                }).filter(id => id);
                            }''')
                            for fbid in fbids:
                                excluded_fbids.add(fbid)
                        except Exception as e:
                            logger.warning(f"Error evaluating fbids: {e}")
                        await page.keyboard.press('End')
                        await asyncio.sleep(1.5)
                        
                logger.info(f"Total excluded fbids (Profile/Cover photos): {len(excluded_fbids)}")
                
                # We always scrape albums if it's a general profile link, regardless of what sk= tab they pasted
                valid_albums = [a for a in album_links if a not in exclude_album_links]
                
                # We also want to scrape the exact URL they pasted (e.g. sk=photos_by) to get any loose photos
                if url not in valid_albums:
                    valid_albums.append(url)
                    
                if valid_albums:
                    logger.info(f"Deep album discovery: found {len(valid_albums)} valid sources to scrape.")
                    urls_to_scrape = valid_albums
                else:
                    logger.info("No valid albums found for deep discovery. Scraping original URL.")
                
            # Extract true page/profile creator name
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                raw_title = await page.evaluate("() => document.querySelector('div[role=\"main\"] h1')?.innerText || document.querySelector('div[role=\"main\"] h2')?.innerText || document.querySelector('meta[property=\"og:title\"]')?.content || document.title")
                clean = sanitize_folder_name(str(raw_title))
                if clean and clean != "Facebook_Page" and "แชท" not in clean and "การแจ้งเตือน" not in clean:
                    page_name = clean
                else:
                    fallback_clean = sanitize_folder_name(str(await page.title()))
                    if fallback_clean and fallback_clean != "Facebook_Page" and "แชท" not in fallback_clean and "การแจ้งเตือน" not in fallback_clean:
                        page_name = fallback_clean
                logger.info(f"Target saving creator folder determined as: '{page_name}'")
            except Exception as e:
                logger.warning(f"Could not read page title: {e}")
            
            image_urls = set()
            
            for t_url in urls_to_scrape:
                logger.info(f"Deep Scraping images from: {t_url}")
                await page.goto(t_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
                
                no_new_links_count = 0
                for scroll_idx in range(max_scrolls):
                    try:
                        found_links = await page.evaluate('''() => {
                            const anchors = Array.from(document.querySelectorAll('a'));
                            return anchors.map(a => {
                                // 1. Reject anything in the main site banner (header)
                                if (a.closest('div[role="banner"]')) return null;
                                
                                // 2. Must be a photo viewer link
                                const href = a.href || '';
                                if (!href.includes('/photo/') && !href.includes('fbid=')) return null;
                                if (href.includes('/media/set/')) return null; // Exclude album links
                                
                                return href;
                            }).filter(src => src && src.includes('facebook.com'));
                        }''')
                    except Exception as e:
                        logger.warning(f"Error extracting links during scrape: {e}")
                        found_links = []
                    
                    previous_count = len(image_urls)
                    import re
                    for link in found_links:
                        match = re.search(r'fbid=(\d+)', link)
                        fbid = match.group(1) if match else None
                        if fbid and fbid in excluded_fbids:
                            continue
                        image_urls.add(link)
                    
                    new_count = len(image_urls)
                    if new_count > previous_count:
                        logger.info(f"-> Discovered {new_count - previous_count} new images (Total: {new_count})")
                    
                    if new_count == previous_count and new_count > 0:
                        no_new_links_count += 1
                        try:
                            await page.evaluate("window.scrollBy(0, -1200);")
                            await page.keyboard.press("PageUp")
                            await asyncio.sleep(1.2)
                        except Exception:
                            pass
                    else:
                        no_new_links_count = 0
                        
                    # Stop early if this specific album/page has no more images
                    if no_new_links_count >= 6:
                        logger.info("Reached maximum no-new-links count. Breaking scroll loop.")
                        break
                    
                    locators = page.locator("a[href*='/photo'], a[href*='fbid=']")
                    count = await locators.count()
                    if count > 0:
                        try:
                            await locators.nth(count - 1).hover(timeout=1000)
                        except Exception:
                            pass
                            
                    await page.keyboard.press("End")
                    
                    try:
                        viewport = page.viewport_size
                        if viewport:
                            await page.mouse.move(viewport['width'] / 2, viewport['height'] / 2)
                    except Exception:
                        pass
                        
                    await page.mouse.wheel(0, 5000)
                    
                    await page.evaluate('''() => {
                        // Remove login overlays and restore scrolling
                        const dialogs = document.querySelectorAll('div[role="dialog"]');
                        dialogs.forEach(el => el.remove());
                        document.body.style.overflow = 'auto';
                        document.body.style.position = 'relative';
                        document.documentElement.style.overflow = 'auto';
                        
                        window.scrollBy(0, 5000);
                        window.scrollTo(0, document.body.scrollHeight);
                        const elements = document.querySelectorAll('*');
                        for (let i = 0; i < elements.length; i++) {
                            const el = elements[i];
                            if (el.scrollHeight > el.clientHeight) {
                                const style = window.getComputedStyle(el);
                                if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                                    el.scrollTop += 5000;
                                    el.dispatchEvent(new Event('scroll', { bubbles: true }));
                                }
                            }
                        }
                    }''')
                    await asyncio.sleep(2.5)
                    
            await browser.close()
            logger.info(f"Deep Scraping complete. Found {len(image_urls)} total images for '{page_name}'.")
            
            return {
                "success": True,
                "page_name": page_name,
                "image_urls": list(image_urls),
                "error": ""
            }
    except Exception as e:
        logger.error(f"Error during image scraping: {str(e)}")
        return {
            "success": False,
            "page_name": page_name,
            "image_urls": [],
            "error": str(e)
        }

async def scrape_instagram_profile(url: str, max_scrolls: int = 50, cookie_file: str = None) -> dict:
    logger.info(f"Starting headless scrape for Instagram Profile URL: {url} (max_scrolls={max_scrolls})")
    video_urls = set()
    page_name = "Instagram_Profile"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900}
            )
            
            # Instagram requires cookies to see reels
            cookie_list = get_auto_browser_cookies("instagram.com")
            if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                cookie_list.extend(load_netscape_cookies(cookie_file))
            
            if cookie_list:
                cookie_dict = {}
                for c in cookie_list:
                    key = (c['name'], c.get('domain', ''))
                    cookie_dict[key] = c
                try:
                    await context.add_cookies(list(cookie_dict.values()))
                    logger.info(f"Loaded {len(cookie_dict)} cookies into Instagram scraper.")
                except Exception as e:
                    logger.warning(f"Error loading cookies for Instagram: {e}")
            else:
                logger.warning("No cookies provided for Instagram scraper. Scraping might be heavily restricted or blocked by login wall.")
                    
            page = await context.new_page()
            
            try:
                parsed = urlparse(url)
                path_parts = [p for p in parsed.path.split('/') if p]
                if path_parts:
                    raw_title = path_parts[0]
                    clean = sanitize_folder_name(raw_title)
                    if clean:
                        page_name = clean
            except Exception as e:
                logger.warning(f"Could not parse Instagram username: {e}")
                pass
                
            logger.info(f"Target Instagram folder determined as: '{page_name}'")
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(5)
            
            video_urls = set()
            
            # Initial DOM links
            found_links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(href => href && (href.includes('/reel/') || href.includes('/p/')));
            }''')
            for link in found_links:
                video_urls.add(link.split('?')[0].rstrip('/'))
                
            logger.info(f"Initial: Discovered {len(video_urls)} videos.")
            
            no_new_links_count = 0
            for scroll_idx in range(max_scrolls):
                previous_count = len(video_urls)
                
                # Close popup if it exists
                try:
                    close_btn = page.locator("svg[aria-label='Close']")
                    if await close_btn.count() > 0:
                        await close_btn.first.click(force=True, timeout=1000)
                        await asyncio.sleep(1)
                except Exception:
                    pass
                
                # Scroll
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.keyboard.press("End")
                except Exception:
                    pass
                await asyncio.sleep(3)
                
                # Extract DOM again
                found_links = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(href => href && (href.includes('/reel/') || href.includes('/p/')));
                }''')
                for link in found_links:
                    video_urls.add(link.split('?')[0].rstrip('/'))
                
                new_count = len(video_urls)
                logger.info(f"Scroll {scroll_idx+1}: Discovered {new_count} total videos so far.")
                
                if new_count == previous_count and new_count > 0:
                    no_new_links_count += 1
                else:
                    no_new_links_count = 0
                    
                if no_new_links_count >= 5:
                    logger.info("No new links found for several scrolls. End of profile likely reached.")
                    break
                    
            await browser.close()
            
            return {
                "success": True,
                "page_name": page_name,
                "video_urls": list(video_urls),
                "error": ""
            }
    except Exception as e:
        logger.error(f"Error scraping Instagram page: {e}")
        return {
            "success": False,
            "page_name": page_name,
            "video_urls": list(video_urls),
            "error": str(e)
        }

def is_tiktok_profile(url: str) -> bool:
    """Checks if a URL is a TikTok user/creator profile page."""
    clean = url.strip().split("?")[0].rstrip("/")
    if "/video/" in clean or "/photo/" in clean:
        return False
    return bool(re.search(r'tiktok\.com/@[\w\.\-]+/?$', clean, re.IGNORECASE))

def extract_tiktok_username(url: str) -> str:
    """Extracts username or creator slug from a TikTok profile link."""
    m = re.search(r'tiktok\.com/@([a-zA-Z0-9_\.\-]+)', url)
    if m:
        return sanitize_folder_name(m.group(1))
    return "TikTok_Creator"

def _harvest_tiktok_ytdlp_sync(url: str, cookie_file: str = None) -> list[str]:
    """Extracts 100% of video links from a TikTok profile using yt-dlp flat-playlist + TLS impersonation."""
    video_urls = []
    configs = [
        {"desc": "Cookies file + TLS Impersonation (Chrome)", "opts": {"impersonate": ImpersonateTarget("chrome")}, "use_cookie": True},
        {"desc": "Direct TLS Impersonation (Chrome, No Cookies)", "opts": {"impersonate": ImpersonateTarget("chrome")}, "use_cookie": False},
        {"desc": "Direct TLS Impersonation (Safari, No Cookies)", "opts": {"impersonate": ImpersonateTarget("safari")}, "use_cookie": False},
        {"desc": "Standard flat extraction", "opts": {}, "use_cookie": False}
    ]
    
    clean_url = url.strip().split("?")[0].rstrip("/")
    uploader_from_url = extract_tiktok_username(url)

    for cfg in configs:
        opts = {
            'extract_flat': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        }
        if cfg.get("use_cookie") and cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
            opts['cookiefile'] = cookie_file
        opts.update(cfg["opts"])
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if not info:
                    continue
                uploader = info.get('uploader_id') or uploader_from_url
                entries = info.get('entries') or []
                for entry in entries:
                    if not entry:
                        continue
                    v_url = entry.get('url')
                    if not v_url and entry.get('id'):
                        v_url = f"https://www.tiktok.com/@{uploader}/video/{entry['id']}"
                    if v_url and "/video/" in v_url and v_url not in video_urls:
                        video_urls.append(v_url)
                if video_urls:
                    logger.info(f"[{cfg['desc']}] Successfully harvested {len(video_urls)} TikTok clips.")
                    return video_urls
        except Exception as e:
            logger.debug(f"[{cfg['desc']}] TikTok flat harvest attempt error: {e}")
            
    return video_urls

async def scrape_tiktok_profile(url: str, max_scrolls: int = 150, cookie_file: str = None) -> dict:
    """
    Two-stage TikTok profile harvester:
    Stage 1: Fast & comprehensive extraction via yt-dlp flat-playlist with TLS impersonation & session cookies.
    Stage 2 (Fallback): Playwright headless browser auto-scroll with network interception to capture 100% of video URLs.
    """
    logger.info(f"Starting TikTok Profile harvest for: {url}")
    page_name = extract_tiktok_username(url)
    
    # Check for any already downloaded files on disk for this creator
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    downloads_dir = os.path.join(project_root, "VDO")
    local_urls = []
    if os.path.exists(downloads_dir):
        for candidate_folder in [page_name, page_name.lstrip('@')]:
            target_p = os.path.join(downloads_dir, candidate_folder)
            if os.path.exists(target_p) and os.path.isdir(target_p):
                for f in os.listdir(target_p):
                    m = re.search(r'(\d{15,22})', f)
                    if m and (f.endswith('.mp4') or f.endswith('.webm')) and not f.endswith('.part'):
                        local_urls.append(f"https://www.tiktok.com/@{page_name}/video/{m.group(1)}")
    
    # 1. Try fast yt-dlp flat extraction with TLS Impersonation & Cookies
    discovered_urls = await asyncio.to_thread(_harvest_tiktok_ytdlp_sync, url, cookie_file)
    combined_urls = list(dict.fromkeys(discovered_urls + local_urls))
    if combined_urls:
        logger.info(f"TikTok profile harvest retrieved {len(combined_urls)} clips ({len(discovered_urls)} from network, {len(local_urls)} verified on disk) for profile '{page_name}'.")
        return {
            "success": True,
            "page_name": page_name,
            "video_urls": combined_urls
        }
        
    # 2. Playwright fallback if yt-dlp was restricted/blocked
    logger.info(f"Falling back to Playwright deep auto-scroll for TikTok profile '{page_name}'...")
    video_urls = set()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            )
            
            cookie_list = get_auto_browser_cookies("tiktok.com")
            if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                cookie_list.extend(load_netscape_cookies(cookie_file))
            
            if cookie_list:
                cookie_dict = {}
                for c in cookie_list:
                    cookie_dict[(c['name'], c.get('domain', ''))] = c
                try:
                    await context.add_cookies(list(cookie_dict.values()))
                    logger.info(f"Injected {len(cookie_dict)} cookies into TikTok Playwright context.")
                except Exception as e:
                    logger.warning(f"Error injecting cookies for TikTok: {e}")
                    
            page = await context.new_page()
            
            async def on_response(response):
                try:
                    ct = response.headers.get("content-type", "")
                    if "application/json" in ct or "text/plain" in ct:
                        if "/api/post/item_list" in response.url:
                            data = await response.json()
                            items = data.get("itemList") or []
                            for itm in items:
                                vid = itm.get("id")
                                if vid:
                                    video_urls.add(f"https://www.tiktok.com/@{page_name}/video/{vid}")
                except Exception:
                    pass
            page.on("response", on_response)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=35000)
            await asyncio.sleep(4)
            
            # Scrape initial DOM links
            dom_links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(href => href && href.includes('/video/'));
            }''')
            for l in dom_links:
                video_urls.add(l.split('?')[0].rstrip('/'))
                
            no_new_rounds = 0
            for scroll_idx in range(max_scrolls):
                prev_len = len(video_urls)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.keyboard.press("End")
                await asyncio.sleep(2)
                
                # Check for new links
                dom_links = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(href => href && href.includes('/video/'));
                }''')
                for l in dom_links:
                    video_urls.add(l.split('?')[0].rstrip('/'))
                    
                if len(video_urls) == prev_len:
                    no_new_rounds += 1
                    if no_new_rounds >= 6:
                        break
                else:
                    no_new_rounds = 0
                    
            await browser.close()
    except Exception as e:
        logger.error(f"Playwright TikTok scrape error: {e}")
        
    final_urls = list(dict.fromkeys(list(video_urls) + local_urls))
    return {
        "success": bool(final_urls),
        "page_name": page_name,
        "video_urls": final_urls,
        "error": "" if final_urls else "No TikTok clips could be extracted."
    }

def extract_subreddit_name(url: str) -> str:
    """Extracts clean subreddit name e.g. 'videos' from url."""
    m = re.search(r'/r/([A-Za-z0-9_]+)', url)
    if m:
        return m.group(1).lower()
    m_raw = re.search(r'^r/([A-Za-z0-9_]+)', url.strip(), re.IGNORECASE)
    if m_raw:
        return m_raw.group(1).lower()
    return "reddit"

async def scrape_subreddit(url: str, max_scrolls: int = 50, cookie_file: str = None) -> dict:
    """
    Headless browser scraper to harvest all video post URLs from a Subreddit (e.g. r/videos, r/funny).
    Scrolls through the subreddit stream and extracts every unique /comments/ post link.
    """
    sub_name = extract_subreddit_name(url)
    page_name = f"r_{sub_name}"
    canonical_sub_url = f"https://www.reddit.com/r/{sub_name}/"
    logger.info(f"Starting Subreddit harvest for: '{sub_name}' ({canonical_sub_url}) with max_scrolls={max_scrolls}")
    
    video_urls = []
    seen = set()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            await page.goto(canonical_sub_url, wait_until='domcontentloaded', timeout=35000)
            await asyncio.sleep(3)
            
            async def extract_page_links():
                raw_links = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(h => h && h.includes('/comments/'));
                }''')
                new_found = 0
                for l in raw_links:
                    clean = l.split('?')[0].rstrip('/')
                    if f"/r/{sub_name}/comments/" in clean.lower() or "/comments/" in clean.lower():
                        if clean not in seen:
                            seen.add(clean)
                            video_urls.append(clean)
                            new_found += 1
                return new_found

            await extract_page_links()
            logger.info(f"[Initial] Discovered {len(video_urls)} posts from r/{sub_name}")
            
            no_new_rounds = 0
            for scroll_idx in range(max_scrolls):
                prev_count = len(video_urls)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.keyboard.press("End")
                await asyncio.sleep(2)
                
                await extract_page_links()
                new_added = len(video_urls) - prev_count
                if new_added > 0:
                    logger.info(f"[Scroll {scroll_idx + 1}/{max_scrolls}] Found +{new_added} new posts (Total: {len(video_urls)})")
                    no_new_rounds = 0
                else:
                    no_new_rounds += 1
                    if no_new_rounds >= 5:
                        logger.info(f"Subreddit scroll reached bottom after {scroll_idx + 1} scrolls.")
                        break
                        
            await browser.close()
    except Exception as e:
        logger.error(f"Playwright Subreddit scrape error for r/{sub_name}: {e}")
        
    return {
        "success": bool(video_urls),
        "page_name": page_name,
        "video_urls": video_urls,
        "error": "" if video_urls else f"No posts found for Subreddit r/{sub_name}."
    }

