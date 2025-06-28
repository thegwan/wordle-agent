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

def clear_word(page, pause=100):
    """Clear the current word by clicking backspace 5 times."""
    print("Clearing word...")
    for i in range(5):
        wait_and_click(page, 'button[data-key="←"]', description=f"Backspace {i+1}", timeout=100)
        page.wait_for_timeout(pause)
    print("Word cleared.")

def read_guess_result(page, row_index=0):
    """Read the result of a guess from the DOM.
    
    Args:
        page: Playwright page object
        row_index: Which row to read (0 for first guess, 1 for second, etc.)
    
    Returns:
        List of tuples: (letter, result) where result is 'correct', 'present', or 'absent'
    """
    # Wait for tiles to finish animating
    page.wait_for_timeout(1000)
    
    # Get all tiles in the specified row
    tiles = page.query_selector_all(f'div[class*="Tile-module_tile"]')
    
    # Wordle has 6 rows of 5 tiles each, so we need to get the correct row
    start_index = row_index * 5
    end_index = start_index + 5
    
    if len(tiles) < end_index:
        print(f"Not enough tiles found. Expected at least {end_index}, got {len(tiles)}")
        return []
    
    row_tiles = tiles[start_index:end_index]
    results = []
    
    for i, tile in enumerate(row_tiles):
        # Get the letter from the tile
        letter = tile.text_content().strip().lower()
        
        # Get the tile's class and data-state to determine the result
        class_name = tile.get_attribute('class') or ''
        data_state = tile.get_attribute('data-state') or ''
        print(f"Tile {i+1} class: {class_name}, data-state: {data_state}")  # DEBUG
        
        # Check for tbd state (word not in dictionary or not submitted properly)
        if data_state == 'tbd':
            result = 'tbd'
        elif data_state in ['correct', 'present', 'absent']:
            result = data_state
        else:
            result = 'unknown'
        
        results.append((letter, result))
        print(f"Tile {i+1}: {letter} -> {result}")
    
    return results

def is_game_won(result):
    """Check if the game is won (all tiles are correct)."""
    return all(tile_result == 'correct' for _, tile_result in result)

def is_game_over(page):
    """Check if the game is over (won or lost)."""
    # Check for win message or game over message
    win_selector = 'text=Congratulations'
    game_over_selector = 'text=Game Over'
    
    try:
        page.wait_for_selector(win_selector, timeout=1000)
        return 'won'
    except:
        try:
            page.wait_for_selector(game_over_selector, timeout=1000)
            return 'lost'
        except:
            return None

def guess_word(page, context) -> str:
    """Guess a word and return the result."""
    # hook up to LLM here
    return "stump"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")

        print("Waiting for Play button...")
        wait_and_click(page, 'text=Play', description="Play button")
        take_screenshot(page, "wordle_board2.png", description="After Play button")

        remove_ad_container(page)

        # Wait for popup and close it
        wait_and_click(page, 'button[aria-label="Close"]', description="Close button")

        # Wait for the board to load
        print("Waiting for board...")
        wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', timeout=10000, description="Game board")
        print("Board loaded.")
        take_screenshot(page, "wordle_board3.png", description="Game board loaded")
        context = "You are a helpful assistant that plays the wordle game. Here is the past history of the game: Guess the next word, return only the word itself, and nothing else. You should return a single 5-letter word."
        word = guess_word(page, context)
        print(f"Guessing word: {word}")
        click_word(page, word)
        page.wait_for_timeout(2500)  # Let tiles animate
        take_screenshot(page, "wordle_after_guess.png", description="After first guess")
        
        # Read the result of the guess
        print("\nReading guess result...")
        result = read_guess_result(page, row_index=0)
        print(f"Guess result: {result}")

        # Check if we need to clear and retry (tbd state)
        if any(tile_result == 'tbd' for _, tile_result in result):
            print("Word not in dictionary or not submitted properly. Clearing and retrying...")
            clear_word(page)
            # Try a different word
            word = "slate"  # Fallback word
            print(f"Retrying with word: {word}")
            click_word(page, word)
            page.wait_for_timeout(2500)  # Let tiles animate
            take_screenshot(page, "wordle_after_retry.png", description="After retry guess")
            
            # Read the result again
            print("\nReading retry guess result...")
            result = read_guess_result(page, row_index=0)
            print(f"Retry guess result: {result}")

        # Check game state
        if is_game_won(result):
            print("🎉 Congratulations! You've won the game!")
            winning_word = ''.join([letter for letter, _ in result])
            print(f"The word was: {winning_word.upper()}")
            take_screenshot(page, "wordle_win.png", description="Game won!")
        else:
            game_status = is_game_over(page)
            if game_status == 'lost':
                print("😔 Game over! You've lost the game.")
                take_screenshot(page, "wordle_loss.png", description="Game lost")
            else:
                print("The game is still ongoing.")

        input("Press Enter to exit...")
        browser.close()

if __name__ == "__main__":
    run()