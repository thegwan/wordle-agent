# main.py
import random
from playwright.sync_api import sync_playwright, Page
import time
from openai import OpenAI
import os
from typing import List, Tuple, Optional

def highlight_and_click(page: Page, selector: str, wait_before_click: int = 1000) -> bool:
    """
    Highlight an element and click it with visual feedback.
    
    Args:
        page: Playwright page object
        selector: CSS selector for the element to click
        wait_before_click: How long to wait before clicking in milliseconds (also used for highlight duration)
    
    Returns:
        bool: True if element was found and clicked, False otherwise
    """
    # Use locator to check if element exists
    locator = page.locator(selector)
    if locator.count() == 0:
        print(f"No element found for selector: {selector}")
        return False

    # Highlight element with red border using evaluate on the locator
    locator.evaluate('''
    (el, duration) => {
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
    ''', wait_before_click)

    page.wait_for_timeout(wait_before_click)
    locator.click()
    return True

def wait_for_selector_safe(page: Page, selector: str, timeout: int = 5000, description: Optional[str] = None) -> bool:
    """
    Wait for a selector with error handling and optional logging.
    
    Args:
        page: Playwright page object
        selector: CSS selector to wait for
        timeout: Maximum time to wait in milliseconds
        description: Optional description for logging
    
    Returns:
        bool: True if selector was found, False if timeout occurred
    """
    try:
        page.wait_for_selector(selector, timeout=timeout)
        if description:
            print(f"{description} found.")
        return True
    except Exception:
        if description:
            print(f"No {description} found, continuing...")
        return False

def wait_and_click(page: Page, selector: str, description: Optional[str] = None, highlight: bool = True, timeout: int = 5000) -> bool:
    """
    Wait for a selector and click it, optionally highlighting the element.
    
    Args:
        page: Playwright page object
        selector: CSS selector for the element to click
        description: Optional description for logging
        highlight: Whether to highlight the element before clicking
        timeout: Maximum time to wait for selector in milliseconds
    
    Returns:
        bool: True if element was found and clicked, False otherwise
    """
    if wait_for_selector_safe(page, selector, timeout=timeout, description=description):
        if highlight:
            highlight_and_click(page, selector, wait_before_click=100)
        else:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.click()
        print(f"{description or selector} clicked.")
        return True
    return False

def remove_ad_container(page: Page) -> None:
    """
    Remove the ad container if present on the page.
    
    Args:
        page: Playwright page object
    """
    print("Checking for ad container...")
    if wait_for_selector_safe(page, 'div[class*="adContainer"]', timeout=1000, description="Ad container"):
        page.evaluate("""
        const ad = document.querySelector('div[class*="adContainer"]'); if (ad)
        ad.remove();
        """)
        print("Ad container removed.")
    else:
        print("No ad container found, continuing...")

def take_screenshot(page: Page, path: str, description: Optional[str] = None) -> None:
    """
    Take a screenshot and print a descriptive message.
    
    Args:
        page: Playwright page object
        path: File path to save the screenshot
        description: Optional description for logging
    """
    page.screenshot(path=path, full_page=True)
    if description:
        print(f"Screenshot taken: {description} -> {path}")
    else:
        print(f"Screenshot taken: {path}")

def click_word(page: Page, word: str, pause: int = 200) -> None:
    """
    Click all letters in the word using the on-screen keyboard, then press Enter.
    
    Args:
        page: Playwright page object
        word: The word to type (will be converted to lowercase)
        pause: Pause between letter clicks in milliseconds
    """
    for letter in word.lower():
        selector = f'button[data-key="{letter}"]'
        if not wait_and_click(page, selector, description=f"Key '{letter}'"):
            print(f"Failed to click letter: {letter}")
        page.wait_for_timeout(pause)

    # Press Enter (↵)
    wait_and_click(page, 'button[data-key="↵"]', description="Enter key", timeout=100)

def clear_word(page: Page, pause: int = 100) -> None:
    """
    Clear the current word by clicking backspace 5 times.
    
    Args:
        page: Playwright page object
        pause: Pause between backspace clicks in milliseconds
    """
    print("Clearing word...")
    for i in range(5):
        wait_and_click(page, 'button[data-key="←"]', description=f"Backspace {i+1}", timeout=100)
        page.wait_for_timeout(pause)
    print("Word cleared.")

def read_guess_result(page: Page, row_index: int = 0) -> List[Tuple[str, str]]:
    """
    Read the result of a guess from the DOM.
    
    Args:
        page: Playwright page object
        row_index: Which row to read (0 for first guess, 1 for second, etc.)
    
    Returns:
        List of tuples: (letter, result) where result is 'correct', 'present', 'absent', or 'tbd'
    """
    # Wait for tiles to finish animating
    page.wait_for_timeout(1000)
    
    # Get all tiles in the specified row using locators
    tiles = page.locator(f'div[class*="Tile-module_tile"]').all()
    
    # Wordle has 6 rows of 5 tiles each, so we need to get the correct row
    start_index = row_index * 5
    end_index = start_index + 5
    
    if len(tiles) < end_index:
        print(f"Not enough tiles found. Expected at least {end_index}, got {len(tiles)}")
        return []
    
    row_tiles = tiles[start_index:end_index]
    result = []
    
    for i, tile in enumerate(row_tiles):
        # Get the letter from the tile using locator
        text_content = tile.text_content()
        if text_content is None:
            letter = ''
        else:
            letter = text_content.strip().lower()
        
        # Get the tile's data-state to determine the result
        data_state = tile.get_attribute('data-state') or ''
        if data_state in ['correct', 'present', 'absent', 'tbd']:
            letter_state = data_state
        else:
            letter_state = 'unknown'
        
        result.append((letter, letter_state))
        print(f"Tile {i+1}: {letter} -> {letter_state}")
    
    return result

def format_guess_result(result: List[Tuple[str, str]]) -> str:
    """
    Format the result in a readable way for the LLM.
    
    Args:
        result: List of (letter, status) tuples from read_guess_result
    
    Returns:
        str: Formatted string like "C(green) R(yellow) A(gray) N(gray) E(gray)"
    """
    formatted = []
    for letter, status in result:
        if status == 'correct':
            formatted.append(f"{letter.upper()}(green)")
        elif status == 'present':
            formatted.append(f"{letter.upper()}(yellow)")
        elif status == 'absent':
            formatted.append(f"{letter.upper()}(gray)")
        else:
            formatted.append(f"{letter.upper()}(unknown)")
    return ' '.join(formatted)

def is_game_won(result: List[Tuple[str, str]]) -> bool:
    """
    Check if the game is won (all tiles are correct).
    
    Args:
        result: List of (letter, status) tuples from read_guess_result
    
    Returns:
        bool: True if all tiles are 'correct', False otherwise
    """
    return all(tile_result == 'correct' for _, tile_result in result)

def build_game_context(guess_history: List[Tuple[str, List[Tuple[str, str]]]], current_round: int, max_guesses: int) -> str:
    """
    Build a comprehensive context for the LLM based on game state.
    
    Args:
        guess_history: List of (word, result) tuples from previous guesses
        current_round: Current round number (1-based)
        max_guesses: Maximum number of guesses allowed
    
    Returns:
        str: Formatted context string for the LLM
    """
    context = f"""You are a Wordle expert. Think carefully about the previous guesses and results, and reason about what the next best guess is. Once you are confident about your guess, respond with the answer. You must respond with exactly one 5-letter word, nothing else. No explanations, no quotes, just the word.

You are playing Wordle. You have {max_guesses - current_round + 1} guesses remaining.

Previous guesses and results:
"""
    
    for i, (word, result) in enumerate(guess_history, 1):
        context += f"Round {i}: {word.upper()} -> {format_guess_result(result)}\n"
    
    context += f"""
Current round: {current_round}

Based on the previous results, choose the best 5-letter word to guess next.
Return only the word itself, nothing else."""
    
    return context


def call_llm_for_guess(context: str) -> str:
    """
    Call OpenAI API to get the next word guess.
    
    Args:
        context: The game context and history to send to the LLM
    
    Returns:
        str: A 5-letter word to guess, or "crane" as fallback
    """
    try:
        # Get API key from environment variable
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("Warning: OPENAI_API_KEY not found in environment variables. Using fallback word.")
            return "crane"
        
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Call the API with responses format
        response = client.responses.create(
            model="gpt-4",
            input=context
        )
        
        # Extract and clean the response
        content = response.output_text
        if not content:
            print("LLM returned empty content. Using fallback.")
            return "crane"
            
        word = content.strip().lower()
        
        # Validate it's a 5-letter word
        if len(word) == 5 and word.isalpha():
            return word
        else:
            print(f"LLM returned invalid word: '{word}'. Using fallback.")
            return "crane"
            
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        print("Using fallback word: crane")
        return "crane"

def guess_word(guess_history: Optional[List[Tuple[str, List[Tuple[str, str]]]]] = None, current_round: int = 1, max_guesses: int = 6) -> str:
    """
    Guess a word using LLM and return the result.
    
    Args:
        guess_history: List of (word, result) tuples from previous guesses
        current_round: Current round number (1-based)
        max_guesses: Maximum number of guesses allowed
    
    Returns:
        str: A 5-letter word to guess
    """
    # Build comprehensive context for LLM
    if guess_history is None:
        guess_history = []
    
    llm_context = build_game_context(guess_history, current_round, max_guesses)
    
    # Call LLM for word selection
    llm_word = call_llm_for_guess(llm_context)
    
    # Validate LLM response is a 5-letter word
    if len(llm_word) == 5 and llm_word.isalpha():
        word = llm_word.lower()
        print(f"LLM chose: {word}")
    else:
        # Fallback to "crane" if LLM word is invalid
        print(f"LLM word '{llm_word}' is invalid, using fallback: crane")
        word = "crane"
    
    return word

def play_round(page: Page, guess_count: int, max_guesses: int, guess_history: List[Tuple[str, List[Tuple[str, str]]]]) -> bool:
    """
    Play a single round of Wordle and return whether the game was won.
    
    Args:
        page: Playwright page object
        guess_count: Current guess number (1-based)
        max_guesses: Maximum number of guesses allowed
        guess_history: List of (word, result) tuples from previous guesses
    
    Returns:
        bool: True if the game was won this round, False otherwise
    """
    print(f"\n--- Round {guess_count} ---")
    
    # Get word from LLM
    word = guess_word(guess_history, guess_count, max_guesses)
    print(f"Guessing word: {word}")
    click_word(page, word)
    page.wait_for_timeout(2500)  # Let tiles animate
    take_screenshot(page, f"wordle_round_{guess_count}_after_guess_{word}.png", description=f"After round {guess_count} guess: {word}")

    # Read the result of the guess
    print("\nReading guess result...")
    result = read_guess_result(page, row_index=guess_count-1)
    print(f"Guess result: {result}")

    # Check if we need to clear and retry (tbd state)
    while any(tile_result == 'tbd' for _, tile_result in result):
        print("Word not in dictionary or not submitted properly. Clearing and retrying...")
        clear_word(page)
        # Try a different word
        word = guess_word(guess_history, guess_count, max_guesses)
        print(f"Retrying with word: {word}")
        click_word(page, word)
        page.wait_for_timeout(2500)  # Let tiles animate
        take_screenshot(page, f"wordle_round_{guess_count}_retry_after_guess_{word}.png", description=f"After round {guess_count} retry: {word}")
        
        # Read the result again
        print("\nReading retry guess result...")
        result = read_guess_result(page, row_index=guess_count-1)
        print(f"Retry guess result: {result}")

    # Add to guess history (only if not tbd)
    if not any(tile_result == 'tbd' for _, tile_result in result):
        guess_history.append((word, result))

    # Check if game is won
    game_won = is_game_won(result)
    if game_won:
        print("Congratulations! You've won the game!")
        winning_word = ''.join([letter for letter, _ in result])
        print(f"The word was: {winning_word.upper()}")
        take_screenshot(page, "wordle_game_won.png", description="Game won!")
    else:
        print("The game is still ongoing.")
    
    return game_won

def run() -> None:
    """
    Main function to run the Wordle agent.
    
    This function:
    1. Sets up the browser and navigates to Wordle
    2. Initializes the game
    3. Plays rounds until the game is won or lost
    4. Takes screenshots throughout the process
    5. Provides a final summary
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")

        print("Waiting for Play button...")
        wait_and_click(page, 'text=Play', description="Play button")
        take_screenshot(page, "wordle_after_play_button.png", description="After Play button")

        remove_ad_container(page)

        # Wait for popup and close it
        wait_and_click(page, 'button[aria-label="Close"]', description="Close button")

        # Wait for the board to load
        print("Waiting for board...")
        wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', timeout=10000, description="Game board")
        print("Board loaded.")
        take_screenshot(page, "wordle_game_board_loaded.png", description="Game board loaded")
        
        # Game loop - continue guessing until game ends
        game_won = False
        guess_count = 0
        max_guesses = 6
        guess_history: List[Tuple[str, List[Tuple[str, str]]]] = []  # Track all guesses and their results
        
        while not game_won and guess_count < max_guesses:
            guess_count += 1
            game_won = play_round(page, guess_count, max_guesses, guess_history)

        # Final game summary
        if game_won:
            print(f"Game won in {guess_count} guesses!")
        else:
            print(f"Game lost after {guess_count} guesses.")
            take_screenshot(page, "wordle_game_lost.png", description="Game lost")

        input("Press Enter to exit...")
        browser.close()

if __name__ == "__main__":
    run()