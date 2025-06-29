# A Wordle AI that plays the game using DOM reading and LLM reasoning.

import re
import logging
from playwright.sync_api import sync_playwright, Page
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import List, Tuple, Optional
from prompts import WORDLE_INSTRUCTIONS, build_game_context

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

fallback_word = "slope"

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
        logger.info(f"No element found for selector: {selector}")
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
            logger.debug(f"{description} found.")
        return True
    except Exception:
        if description:
            logger.debug(f"No {description} found, continuing...")
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
        logger.debug(f"{description or selector} clicked.")
        return True
    return False

def remove_ad_container(page: Page) -> None:
    """
    Remove the ad container if present on the page.
    
    Args:
        page: Playwright page object
    """
    logger.debug("Checking for ad container...")
    if wait_for_selector_safe(page, 'div[class*="adContainer"]', timeout=1000, description="Ad container"):
        page.evaluate("""
        const ad = document.querySelector('div[class*="adContainer"]'); if (ad)
        ad.remove();
        """)
        logger.debug("Ad container removed.")
    else:
        logger.debug("No ad container found, continuing...")


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
            logger.error(f"Failed to click letter: {letter}")
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
    logger.debug("Clearing word...")
    for i in range(5):
        wait_and_click(page, 'button[data-key="←"]', description=f"Backspace {i+1}", timeout=100)
        page.wait_for_timeout(pause)
    logger.debug("Word cleared.")

def read_guess_result(page: Page, row_index: int = 0) -> str:
    """
    Read the result of a guess from the DOM.
    
    Args:
        page: Playwright page object
        row_index: Which row to read (0 for first guess, 1 for second, etc.)
        
    Returns:
        str: 5-character string representing the result:
             'c' = correct (green)
             'p' = present (yellow) 
             'a' = absent (gray)
             'u' = unknown/not yet evaluated (tbd, empty, etc.)
    """
    # Wait for tiles to finish animating
    page.wait_for_timeout(1000)
    
    # Get all tiles in the specified row using locators
    tiles = page.locator(f'div[class*="Tile-module_tile"]').all()
    
    # Wordle has 6 rows of 5 tiles each, so we need to get the correct row
    start_index = row_index * 5
    end_index = start_index + 5
    
    if len(tiles) < end_index:
        logger.error(f"Not enough tiles found. Expected at least {end_index}, got {len(tiles)}")
        return "uuuuu"
    
    row_tiles = tiles[start_index:end_index]
    result = ""
    
    for i, tile in enumerate(row_tiles):
        # Get the tile's data-state to determine the result
        data_state = tile.get_attribute('data-state') or ''
        
        if data_state == 'correct':
            result += 'c'
        elif data_state == 'present':
            result += 'p'
        elif data_state == 'absent':
            result += 'a'
        else:  # tbd, empty, or any other state
            result += 'u'
        
        logger.debug(f"Tile {i+1}: {data_state} -> {result[-1]}")
    
    return result


def is_game_won(result: str) -> bool:
    """
    Check if the game is won (all tiles are correct).
    
    Args:
        result: 5-character string representing the result
        
    Returns:
        bool: True if all tiles are 'c', False otherwise
    """
    return result == 'ccccc'

def call_llm_for_guess(context: str) -> Optional[str]:
    """
    Call OpenAI API to get the next word guess with reasoning.
    
    Args:
        context: The game context and history to send to the LLM
        
    Returns:
        str: A word from the LLM, or None if the call failed
    """
    try:
        # Get API key from environment variable
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("Warning: OPENAI_API_KEY not found in environment variables.")
            return None
        
        client = OpenAI(api_key=api_key)
        
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=WORDLE_INSTRUCTIONS,
            input=context,
        )
        
        content = response.output_text
        if not content:
            logger.warning("LLM returned empty content.")
            return None
        
        # Print the full response for debugging
        logger.info("\n=== LLM RESPONSE ===")
        logger.info(content)
        logger.info("===================\n")
        
        # Extract the word from the structured format
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ANSWER:'):
                word = line[7:].strip().lower()  # Remove "ANSWER: " prefix
                if len(word) == 5 and word.isalpha():
                    return word
        
        # Fallback: try to find any 5-letter word in the response
        words = re.findall(r'\b[a-zA-Z]{5}\b', content)
        if words:
            return words[0].lower()
            
        return None
        
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        return None

def guess_word(guess_history: Optional[List[Tuple[str, str]]] = None, current_round: int = 1, max_guesses: int = 6) -> str:
    """
    Get a word to guess, either from LLM or fallback.
    
    Args:
        guess_history: List of (word, result) tuples from previous guesses
        current_round: Current round number (1-based)
        max_guesses: Maximum number of guesses allowed
        
    Returns:
        str: A valid 5-letter word to guess
    """
    # Build comprehensive context for LLM
    if guess_history is None:
        guess_history = []
    logger.debug(f"Guess history: {guess_history}")
    
    # Try to get word from LLM
    llm_word = call_llm_for_guess(build_game_context(guess_history, current_round, max_guesses))
    
    if llm_word and len(llm_word) == 5 and llm_word.isalpha():
        logger.info(f"LLM chose: {llm_word}")
        return llm_word
    else:
        # Fallback if LLM word is invalid or None
        if llm_word:
            logger.info(f"LLM word '{llm_word}' is invalid, using fallback: {fallback_word}")
        else:
            logger.info(f"LLM returned None, using fallback: {fallback_word}")
        return fallback_word

def play_round(page: Page, guess_count: int, max_guesses: int, guess_history: List[Tuple[str, str]]) -> bool:
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
    logger.info(f"\n--- Round {guess_count} ---")
    
    # Get a word from the LLM
    word = guess_word(guess_history, guess_count, max_guesses)
    if 'u' in word:
        word = 'budgy'
    logger.info(f"Guessing word: {word}")
    click_word(page, word)
    page.wait_for_timeout(2500)  # Let tiles animate

    # Read the result of the guess
    logger.debug("Reading guess result...")
    result = read_guess_result(page, row_index=guess_count-1)
    logger.info(f"Guess result: {result}")

    # Check if we need to clear and retry (unknown states)
    while any(tile_result == 'u' for tile_result in result):
        logger.info("Word not in dictionary or not submitted properly. Clearing the word...")
        clear_word(page)
        # Guess a new word
        logger.info(f"Retrying round {guess_count}...")
        play_round(page, guess_count, max_guesses, guess_history)
        # Update result with the new word's result
        result = read_guess_result(page, row_index=guess_count-1)

    if not any(tile_result == 'u' for tile_result in result):
        guess_history.append((word, result))

    # Check if game is won
    game_won = is_game_won(result)
    if game_won:
        logger.info("Congratulations! You've won the game!")
        logger.info(f"The word was: {word.upper()}")
    else:
        logger.debug("The game is still ongoing.")
    
    return game_won

def run() -> None:
    """
    Main function to run the Wordle agent (actually more of a workflow than a true agent).
    
    1. Sets up the browser and navigates to Wordle
    2. Initializes the game
    3. Plays rounds until the game is won or lost
    4. Provides a final summary
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")

        logger.debug("Waiting for Play button...")
        wait_and_click(page, 'text=Play', description="Play button")

        remove_ad_container(page)

        # Wait for popup and close it
        wait_and_click(page, 'button[aria-label="Close"]', description="Close button")

        # Wait for the board to load
        logger.debug("Waiting for board...")
        wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', timeout=10000, description="Game board")
        logger.debug("Board loaded.")
        
        # Game loop - continue guessing until game ends
        game_won = False
        guess_count = 0
        max_guesses = 6
        guess_history: List[Tuple[str, str]] = []  # Track all guesses and their results
        
        while not game_won and guess_count < max_guesses:
            guess_count += 1
            game_won = play_round(page, guess_count, max_guesses, guess_history)

        # Final game summary
        if game_won:
            logger.info(f"Game won in {guess_count} guesses!")
        else:
            logger.info(f"Game lost after {guess_count} guesses.")

        input("Press Enter to exit...")
        browser.close()

if __name__ == "__main__":
    run()