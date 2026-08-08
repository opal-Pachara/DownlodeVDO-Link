import os
import asyncio
import re
import logging
from urllib.parse import urlparse, urlunparse
from playwright.async_api import async_playwright

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
        r'(https?://(?:www\.|m\.|mbasic\.|l\.)?(?:facebook\.com|instagram\.com|tiktok\.com|youtube\.com|youtu\.be)/(?:[^/"\'\s]+/videos/[^/"\'\s]+|reel/[^/"\'\s]+|reels/[^/"\'\s]+|watch/?\?[^\s"\'<>]+|@[^/"\'\s]+/video/[^/"\'\s]+|p/[^/"\'\s]+|shorts/[^/"\'\s]+|v/[^/"\'\s]+|[^\s"\'<>]+))|'
        r'(https?://fb\.watch/[^\s"\'<>]+)',
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
            if any(k in clean.lower() for k in ['/reel/', '/videos/', '/watch', 'fb.watch', '/video/', '/p/', '/shorts/', 'youtube.com/watch']):
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

async def scrape_facebook_page(url: str, max_scrolls: int = 80, cookie_file: str = None) -> dict:
    """
    Launches a headless Chromium instance using Playwright, auto-injects browser cookies,
    extracts creator title, and scrolls up to 80 times to harvest 100% of all Reels/Videos.
    """
    logger.info(f"Starting headless scrape for Facebook Page URL: {url} (max_scrolls={max_scrolls})")
    video_urls = set()
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
            
            # Automatically load browser cookies from Chrome/Safari or file to bypass Facebook login wall and capture 100% of clips!
            cookie_list = get_auto_browser_cookies("facebook.com")
            if cookie_file and os.path.exists(cookie_file):
                file_cookies = load_netscape_cookies(cookie_file)
                cookie_list.extend(file_cookies)
                
            if cookie_list:
                try:
                    await context.add_cookies(cookie_list)
                    logger.info(f"Injected {len(cookie_list)} session cookies into Playwright browser context successfully.")
                except Exception as e:
                    logger.warning(f"Error injecting cookies into context: {e}")

            page = await context.new_page()
            
            logger.info("Navigating to target URL...")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            
            try:
                close_buttons = page.locator("div[role='button']:has-text('Allow'), div[role='button']:has-text('Accept'), div[role='button']:has-text('Decline'), div[aria-label='Close']")
                if await close_buttons.count() > 0:
                    await close_buttons.first.click(timeout=2000)
            except Exception:
                pass

            # Extract true page/profile creator name strictly from main content area to avoid notification/header titles
            try:
                raw_title = await page.evaluate("() => document.querySelector('div[role=\"main\"] h1')?.innerText || document.querySelector('div[role=\"main\"] h2')?.innerText || document.querySelector('meta[property=\"og:title\"]')?.content || document.title")
                logger.info(f"Raw creator name retrieved from profile header: '{raw_title}'")
                clean = sanitize_folder_name(str(raw_title))
                if clean and clean != "Facebook_Page" and "แชท" not in clean and "การแจ้งเตือน" not in clean:
                    page_name = clean
                else:
                    fallback_title = await page.title()
                    fallback_clean = sanitize_folder_name(str(fallback_title))
                    if fallback_clean and fallback_clean != "Facebook_Page" and "แชท" not in fallback_clean and "การแจ้งเตือน" not in fallback_clean:
                        page_name = fallback_clean
            except Exception as e:
                logger.warning(f"Could not read page title: {e}")

            logger.info(f"Target saving creator folder determined as: '{page_name}'")
            
            # Scroll loop with keyboard simulation and window scrolling to force GraphQL pagination
            no_new_links_count = 0
            for scroll_idx in range(max_scrolls):
                # Extract anchor tags exclusively from main content area to avoid notification/sidebar clips
                found_links = await page.evaluate('''() => {
                    const main_el = document.querySelector('div[role="main"]') || document.body;
                    const anchors = Array.from(main_el.querySelectorAll('a'));
                    return anchors
                        .map(a => a.href)
                        .filter(href => {
                            if (!href) return false;
                            const h = href.toLowerCase();
                            if (h.includes('notif') || h.includes('comment_id=') || h.includes('/reel/?s=')) return false;
                            return h.includes('/reel/') || h.includes('/videos/') || h.includes('fb.watch/');
                        });
                }''')
                
                previous_count = len(video_urls)
                for link in found_links:
                    clean_url = clean_fb_url(link)
                    if "notif" in clean_url.lower() or "comment_id" in clean_url.lower():
                        continue
                    if not clean_url.endswith('/reels') and not clean_url.endswith('/videos') and not clean_url.endswith('/watch'):
                        video_urls.add(clean_url)
                
                new_count = len(video_urls)
                logger.info(f"[Scroll {scroll_idx + 1}/{max_scrolls}] Discovered {new_count - previous_count} new clip URLs (Total: {new_count})")
                
                if new_count == previous_count and new_count > 0:
                    no_new_links_count += 1
                    logger.debug(f"No new videos discovered on scroll {scroll_idx + 1}; performing Smart Jiggle scroll...")
                    try:
                        await page.evaluate("window.scrollBy(0, -1200);")
                        await page.keyboard.press("PageUp")
                        await asyncio.sleep(1.2)
                    except Exception:
                        pass
                else:
                    no_new_links_count = 0
                    
                # If scrolling 10 consecutive times yielded no new videos, finish harvesting
                if no_new_links_count >= 10:
                    logger.info("No new videos discovered after 10 consecutive retry attempts; finishing harvesting.")
                    break
                
                # Perform simulated keyboard and mouse scrolling to trigger React event listeners
                await page.keyboard.press("End")
                await page.mouse.wheel(0, 5000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(3.5)
                
            await browser.close()
            logger.info(f"Scraping complete. Found {len(video_urls)} clips for '{page_name}'.")
            
            return {
                "success": True,
                "page_name": page_name,
                "video_urls": list(video_urls),
                "error": ""
            }
    except Exception as e:
        logger.error(f"Error during Playwright page scraping: {str(e)}")
        return {
            "success": False,
            "page_name": page_name,
            "video_urls": [],
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
            if cookie_file and os.path.exists(cookie_file):
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
                            fbids = await page.evaluate('''() => {
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
