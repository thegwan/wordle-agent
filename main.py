import logging
import os
import re
from typing import List, Tuple, Optional

from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright, Page

from browser_utils import wait_for_selector_safe, remove_ad_container, wait_and_click

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def click_word(page: Page, word: str) -> None:
    """
    Click all letters in the word using the on-screen keyboard, then press Enter.

    Args:
        page: Playwright page object
        word: The 5-letter word to type (will be converted to lowercase)
    
    Returns:
        None
    """
    for letter in word.lower():
        selector = f'button[data-key="{letter}"]'
        if not wait_and_click(page, selector, description=f"Key '{letter}'"):
            logger.error(f"Failed to click letter: {letter}")

    # Press Enter (↵)
    wait_and_click(page, 'button[data-key="↵"]', description="Enter key")


def clear_word(page: Page) -> None:
    """
    Clear the current word by clicking backspace 5 times.

    Args:
        page: Playwright page object

    Returns:
        None
    """
    logger.debug("Clearing word...")
    for i in range(5):
        wait_and_click(page, 'button[data-key="←"]', description=f"Backspace {i+1}")
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

    tiles = page.locator('div[class*="Tile-module_tile"]').all()

    # Wordle has 6 rows of 5 tiles each, get the tile indexes
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
        else:  # tbd, empty, or any other state considered unknown
            result += 'u'

        logger.debug(f"Tile {i+1}: {data_state} -> {result[-1]}")

    return result


def check_game_won(result: str) -> bool:
    """
    Check if the game is won (all tiles are correct).

    Args:
        result: 5-character string representing the game state

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

class Level1WordleAgent:
    def __init__(self, page: Page):
        self.page = page
        self.game_state = GameState(
            guess_history=[],
            current_round=0,
            max_guesses=6,
            game_won=False
        )

        # Define available tools
        self.tool_registry = [{
            "name": "click_word",
            "description": click_word.__doc__
        },
        {
            "name": "clear_word",
            "description": clear_word.__doc__
        },
        {
            "name": "read_game_state",
            "description":  read_game_state.__doc__
        },
        {
            "name": "check_game_won",
            "description":  check_game_won.__doc__
        }
        ]


    
    

class Level0WordleAgent:
    def __init__(self, page: Page):
        self.page = page
        self.llm_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.game_state = GameState(
            guess_history=[],
            current_round=0,
            max_guesses=6,
            game_won=False
        )

    def get_llm_instructions(self) -> str:
        """
        Get the system prompt for the LLM.
        """
        return (
            """You are an expert Wordle player. You will be given a history of previous guesses and their results, as well as the current round and how many guesses you have left.

Always think step by step, but don't take too long and be concise. At the end, output your final guess in **this exact format**:  
`ANSWER: [your 5-letter word]` — no quotes, no extra text, no explanation after. Make sure the final answer is actually a 5 letter word.

If your answer does not have the final 5-letter answer in that format, it will be ignored.

RESULT FORMAT:
Each line: Round X: WORD -> RESULT
- RESULT uses:
  - c = correct (green)
  - p = present (yellow)
  - a = absent (gray)
  - u = unknown

Example:  
Round 1: CRANE -> cpaaa  
=> C is green, R is yellow, A/N/E are gray.

Think step by step:
1. Analyze what letters are confirmed, eliminated, or likely.
2. Consider frequency and coverage of remaining options.
3. Choose the most promising guess.
4. Try to win in as few guesses as possible.

Then end with:  
ANSWER: [your word]
"""
        )

    def build_game_context(self) -> str:
        """
        Build the game context prompt with guess history and current state.

        Returns:
            str: Formatted context string for the LLM
        """
        context = """
    Previous guesses:
    """
        for i, (word, result) in enumerate(self.game_state.guess_history, 1):
            context += f"Round {i}: {word.upper()} -> {result}\n"
        context += f"""

    Current round: {self.game_state.current_round}. There are {self.game_state.max_guesses - self.game_state.current_round + 1} guesses left.

    Think step by step and guess the next word.

    End with:  
    `ANSWER: [your word]`
    """
        return context

    def call_llm(self, context: str) -> Optional[str]:
        """
        Call OpenAI API to get the next word guess with reasoning.

        Args:
            context: The game context and history to send to the LLM

        Returns:
            str: A word from the LLM, or None if the call failed
        """
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.warning("Warning: OPENAI_API_KEY not found in environment variables.")
                return None
            
            response = self.llm_client.responses.create(
                model="gpt-4.1-mini",
                instructions=self.get_llm_instructions(),
                input=context,
            )
            content = response.output_text
            if not content:
                logger.warning("LLM returned empty content.")
                return None
            logger.info("\n=== LLM RESPONSE ===")
            logger.info(content)
            logger.info("===================\n")
            lines = content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('ANSWER:'):
                    word = line[7:].strip().lower()
                    if len(word) == 5 and word.isalpha():
                        return word
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

        Returns:
            str: A valid 5-letter word to guess
        """
        fallback_word = "slope"
        if self.game_state.guess_history is None:
            self.game_state.guess_history = []
        context = self.build_game_context()
        logger.debug(f"Context: {context}")
        llm_word = self.call_llm(context)
        if llm_word and len(llm_word) == 5 and llm_word.isalpha():
            logger.info(f"LLM chose: {llm_word}")
            return llm_word
        else:
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
        logger.info(f"Guessing word: {word}")
        click_word(self.page, word)
        self.page.wait_for_timeout(2500)
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
    wait_and_click(page, 'button[aria-label="Close"]', description="Close button")
    logger.debug("Closed help module.")
    wait_for_selector_safe(page, 'div[class*="Tile-module_tile"]', description="Game board")
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