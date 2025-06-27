# main.py
from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")
        
        # TODO: make this more robust in case landing page changes
        print("Waiting for Play button...")
        page.wait_for_selector('text=Play')
        time.sleep(2)  
        page.screenshot(path="wordle_board1.png", full_page=True)
         
        page.click('text=Play')
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
            time.sleep(2)
            page.click('button[aria-label="Close"]')
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