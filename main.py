# main.py
from playwright.sync_api import sync_playwright
import time


def highlight_and_click(page, selector, highlight_duration=1000, wait_before_click=1000):
    """Highlight an element and click it."""
    element_handle = page.query_selector(selector)
    if element_handle is None:
        print(f"No element found for selector: {selector}")
        return False

    # Highlight element
    page.evaluate('''
    ([el, duration]) => {
        const rect = el.getBoundingClientRect();
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.left = rect.left + 'px';
        overlay.style.top = rect.top + 'px';
        overlay.style.width = rect.width + 'px';
        overlay.style.height = rect.height + 'px';
        overlay.style.border = '3px solid red';
        overlay.style.zIndex = 9999;
        overlay.style.pointerEvents = 'none';
        overlay.style.borderRadius = '0';
        document.body.appendChild(overlay);
        setTimeout(() => {
            overlay.remove();
        }, duration);
    }
    ''', [element_handle, highlight_duration])

    page.wait_for_timeout(wait_before_click)
    element_handle.click()
    return True

def wait_for_selector_safe(page, selector, timeout=5000, description=None):
    """Wait for a selector with error handling."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        if description:
            print(f"{description} found.")
        return True
    except Exception:
        if description:
            print(f"No {description} found, continuing...")
        return False

def wait_and_click(page, selector, description=None, highlight=True, timeout=5000):
    """Wait for a selector and click it, optionally highlighting."""
    if wait_for_selector_safe(page, selector, timeout=timeout, description=description):
        if highlight:
            highlight_and_click(page, selector)
        else:
            element = page.query_selector(selector)
            if element:
                element.click()
        print(f"{description or selector} clicked.")
        return True
    return False

def remove_ad_container(page):
    """Remove the ad container if present."""
    print("Checking for ad container...")
    if wait_for_selector_safe(page, 'div[class*="adContainer"]', timeout=1000, description="Ad container"):
        page.evaluate("""
        const ad = document.querySelector('div[class*="adContainer"]');
        if (ad) ad.remove();
        """)
        print("Ad container removed.")
    else:
        print("No ad container found, continuing...")

def take_screenshot(page, path, description=None):
    """Take a screenshot and print a message."""
    page.screenshot(path=path, full_page=True)
    if description:
        print(f"Screenshot taken: {description} -> {path}")
    else:
        print(f"Screenshot taken: {path}")

def click_word(page, word, pause=200):
    """Click each letter in the word using the on-screen keyboard, then press Enter."""
    for letter in word.lower():
        selector = f'button[data-key="{letter}"]'
        if not wait_and_click(page, selector, description=f"Key '{letter}'"):
            print(f"Failed to click letter: {letter}")
        page.wait_for_timeout(pause)

    # Press Enter (↵)
    wait_and_click(page, 'button[data-key="↵"]', description="Enter key", timeout=100)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")

        print("Waiting for Play button...")
        wait_and_click(page, 'text=Play', description="Play button")
        time.sleep(2)
        take_screenshot(page, "wordle_board2.png", description="After Play button")

        remove_ad_container(page)

        # Wait for popup and close it
        wait_and_click(page, 'button[aria-label="Close"]', description="Close button")

        # Wait for the board to load
        print("Waiting for board...")
        wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', timeout=10000, description="Game board")
        time.sleep(2)
        print("Board loaded.")
        take_screenshot(page, "wordle_board3.png", description="Game board loaded")

        click_word(page, "crane")
        page.wait_for_timeout(2500)  # Let tiles animate
        take_screenshot(page, "wordle_after_guess.png", description="After first guess")

        input("Press Enter to exit...")
        browser.close()

if __name__ == "__main__":
    run()