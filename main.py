# main.py
from playwright.sync_api import sync_playwright
import time


def highlight_and_click(page, selector, highlight_duration=1000, wait_before_click=1000):
    element_handle = page.query_selector(selector)
    if element_handle is None:
        print(f"No element found for selector: {selector}")
        return False

    # Highlight element
    page.evaluate('''
    ([el, duration]) => {
        // Get element's position and size
        const rect = el.getBoundingClientRect();
        // Create overlay
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.left = rect.left + 'px';
        overlay.style.top = rect.top + 'px';
        overlay.style.width = rect.width + 'px';
        overlay.style.height = rect.height + 'px';
        overlay.style.border = '3px solid red';
        overlay.style.zIndex = 9999;
        overlay.style.pointerEvents = 'none';
        overlay.style.borderRadius = '0'; // force square corners
        document.body.appendChild(overlay);
        setTimeout(() => {
            overlay.remove();
        }, duration);
    }
    ''', [element_handle, highlight_duration])

    # Wait so highlight is visible
    page.wait_for_timeout(wait_before_click)

    # Click element
    element_handle.click()
    return True

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")
        
        # TODO: make this more robust in case landing page changes
        print("Waiting for Play button...")
        page.wait_for_selector('text=Play')
         
        highlight_and_click(page, 'text=Play', highlight_duration=3000, wait_before_click=3000)
        print("Play button clicked")
        time.sleep(2)        
        page.screenshot(path="wordle_board2.png", full_page=True)

        try:
            print("Waiting for ad container...")
            page.wait_for_selector('div[class*="adContainer"]', timeout=1000)
            page.evaluate("""
            const ad = document.querySelector('div[class*="adContainer"]');
            if (ad) ad.remove();
            """)
            time.sleep(2)
            print("Ad container removed")
        except:
            print("No ad container found, continuing...")

        # Wait for popup and close it
        try:
            print("Waiting for Close button...")
            page.wait_for_selector('button[aria-label="Close"]', timeout=5000)
            highlight_and_click(page, 'button[aria-label="Close"]', highlight_duration=3000, wait_before_click=3000)
        except:
            print("No close button found, continuing...")

        # Wait for the board to load
        print("Waiting for board...")
        page.wait_for_selector('div[class*="Tile-module_tile"]', timeout=10000)
        time.sleep(2) 
        print("Board loaded")
        # Take screenshot of game board
        page.screenshot(path="wordle_board3.png", full_page=True)
        print("Screenshot taken.")

        input("Press Enter to exit...")
        browser.close()

if __name__ == "__main__":
    run()