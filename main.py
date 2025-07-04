# A Wordle AI that plays the game using DOM reading and LLM reasoning.

from dataclasses import dataclass
import re
import logging
from playwright.sync_api import sync_playwright, Page
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import List, Tuple, Optional
from prompts import WORDLE_INSTRUCTIONS, build_game_context
from dataclasses import dataclass
from browser_utils import wait_for_selector_safe, remove_ad_container, wait_and_click

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Tool implementations
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

def read_game_state(page: Page, row_index: int = 0) -> str:
    """
    Read the current state of the game board.
    
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

def check_game_won(result: str) -> bool:
    """
    Check if the game is won (all tiles are correct).
    
    Args:
        result: 5-character string representing the result
        
    Returns:
        bool: True if all tiles are 'c', False otherwise
    """
    return result == 'ccccc'



@dataclass
class GameState:
    """
    Represents the current state of the game.
    """
    guess_history: List[Tuple[str, str]]
    current_round: int
    max_guesses: int
    game_won: bool

class Level0WordleAgent:
    def __init__(self, page: Page):
        self.page = page
        self.game_state = GameState(
            guess_history=[],
            current_round=0,
            max_guesses=6,
            game_won=False
        )

    def call_llm(self, context: str) -> Optional[str]:
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

    def guess_word(self) -> str:
        """
        Get a word to guess, either from LLM or fallback.
        
        Args:
            guess_history: List of (word, result) tuples from previous guesses
            current_round: Current round number (1-based)
            max_guesses: Maximum number of guesses allowed
            
        Returns:
            str: A valid 5-letter word to guess
        """
        fallback_word = "slope"

        # Build comprehensive context for LLM
        if self.game_state.guess_history is None:
            self.game_state.guess_history = []
        logger.debug(f"Guess history: {self.game_state.guess_history}")
        
        # Try to get word from LLM
        llm_word = self.call_llm(build_game_context(self.game_state.guess_history, self.game_state.current_round, self.game_state.max_guesses))
        
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

    def play_round(self) -> bool:
        """
        Play a single round of Wordle and return whether the game was won.
        Returns:
            bool: True if the game was won this round, False otherwise
        """
        logger.info(f"\n--- Round {self.game_state.current_round} ---")
        word = self.guess_word()
        # Placeholder to force invalid words
        if 'u' in word:
            word = 'qqqqq'
        logger.info(f"Guessing word: {word}")
        click_word(self.page, word)
        self.page.wait_for_timeout(2500)  # Let tiles animate
        logger.debug("Reading guess result...")
        result = read_game_state(self.page, row_index=self.game_state.current_round-1)
        logger.info(f"Guess result: {result}")
        while any(tile_result == 'u' for tile_result in result):
            logger.info("Word not in dictionary or not submitted properly. Clearing the word...")
            clear_word(self.page)
            logger.info(f"Retrying round {self.game_state.current_round}...")
            self.play_round()
            result = read_game_state(self.page, row_index=self.game_state.current_round-1)
        if not any(tile_result == 'u' for tile_result in result):
            self.game_state.guess_history.append((word, result))
        self.game_state.game_won = check_game_won(result)
        if self.game_state.game_won:
            logger.info("Congratulations! You've won the game!")
            logger.info(f"The word was: {word.upper()}")
        else:
            logger.debug("The game is still ongoing.")
        return self.game_state.game_won
        

    def run(self):
        while not self.game_state.game_won and self.game_state.current_round < self.game_state.max_guesses:
            self.game_state.current_round += 1
            self.game_state.game_won = self.play_round()
        if self.game_state.game_won:
            logger.info(f"Game won in {self.game_state.current_round} guesses!")
        else:
            logger.info(f"Game lost after {self.game_state.current_round} guesses.")


def setup_game(page: Page):
    """
    Setup the game by clicking the Play button, removing the ad container, and closing the help module.
    """
    wait_and_click(page, 'button[data-testid="Play"]', description="Play button")
    logger.debug("Clicked Play button.")
    remove_ad_container(page)
    logger.debug("Ad container removed.")
    wait_and_click(page, 'button[aria-label=\"Close\"]', description="Close button")
    logger.debug("Closed help module.")
    wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', timeout=10000, description="Game board")
    logger.debug("Board loaded.")


def run_level0_agent():
    """
    Run the Level 0 Wordle agent.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.nytimes.com/games/wordle/index.html", wait_until="domcontentloaded")

        setup_game(page)

        agent = Level0WordleAgent(page)
        agent.run()

        input("Press Enter to exit...")
        browser.close()


if __name__ == "__main__":
    run_level0_agent()