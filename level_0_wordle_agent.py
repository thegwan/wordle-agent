import logging
import os
import re
from typing import List, Tuple, Optional
from openai import OpenAI
from dataclasses import dataclass
from browser_utils import wait_for_selector_safe, remove_ad_container, wait_and_click
from playwright.sync_api import Page

@dataclass
class GameState:
    guess_history: List[Tuple[str, str]]
    current_round: int
    max_guesses: int

# Tool definitions

def click_word(page: Page, word: str) -> None:
    for letter in word.lower():
        selector = f'button[data-key="{letter}"]'
        if not wait_and_click(page, selector, description=f"Key '{letter}'"):
            logging.error(f"Failed to click letter: {letter}")
    wait_and_click(page, 'button[data-key="↵"]', description="Enter key")
    page.wait_for_timeout(1000)

def clear_word(page: Page) -> None:
    for i in range(5):
        wait_and_click(page, 'button[data-key="←"]', description=f"Backspace {i+1}")

def update_game_state(page: Page, game_state: GameState, guess: str) -> str:
    result = read_game_state(page, game_state.current_round)
    if 'u' not in result:
        game_state.guess_history.append((guess, result))
        game_state.current_round += 1
    return result

def read_game_state(page: Page, row_index: int = 0) -> str:
    page.wait_for_timeout(1000)
    tiles = page.locator('div[class*="Tile-module_tile"]').all()
    start_index = row_index * 5
    end_index = start_index + 5
    if len(tiles) < end_index:
        logging.error(f"Not enough tiles found. Expected at least {end_index}, got {len(tiles)}")
        return "uuuuu"
    row_tiles = tiles[start_index:end_index]
    result = ""
    for i, tile in enumerate(row_tiles):
        data_state = tile.get_attribute('data-state') or ''
        if data_state == 'correct':
            result += 'c'
        elif data_state == 'present':
            result += 'p'
        elif data_state == 'absent':
            result += 'a'
        else:
            result += 'u'
    return result

class Level0WordleAgent:
    def __init__(self, page: Page):
        self.page = page
        self.llm_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.game_state = GameState(
            guess_history=[],
            current_round=0,
            max_guesses=6,
        )

    def get_llm_instructions(self) -> str:
        return (
            """You are an expert Wordle player. You will be given a history of previous guesses and their results, as well as the current round and how many guesses you have left.\n\nAlways reason strategically about what word you should guess next. At the end, output your final guess in **this exact format**:  \n`ANSWER: [your 5-letter word]` — no quotes, no extra text, no explanation after. Make sure the final answer is actually a 5 letter word.\n\nIf your answer does not have the final 5-letter answer in that format, it will be ignored.\n\nRESULT FORMAT:\nEach line: Round X: WORD -> RESULT\n- RESULT uses:\n  - c = correct (green)\n  - p = present (yellow)\n  - a = absent (gray)\n  - u = unknown\n\nExample:  \nRound 1: CRANE -> cpaaa  \n=> C is green, R is yellow, A/N/E are gray.\n\nThink step by step:\n1. Analyze what letters are confirmed, eliminated, or likely.\n2. Consider frequency and coverage of remaining options.\n3. Choose the most promising guess.\n4. Try to win in as few guesses as possible.\n\nThen end with:  \nANSWER: [your word]\n"""
        )

    def get_llm_input(self) -> str:
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
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logging.warning("Warning: OPENAI_API_KEY not found in environment variables.")
                return None
            response = self.llm_client.responses.create(
                model="gpt-4.1-mini",
                instructions=self.get_llm_instructions(),
                input=context,
            )
            content = response.output_text
            if not content:
                logging.warning("LLM returned empty content.")
                return None
            logging.info("\n=== LLM RESPONSE ===")
            logging.info(content)
            logging.info("===================\n")
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
            logging.error(f"Error calling OpenAI API: {e}")
            return None

    def guess_word(self) -> str:
        fallback_word = "slope"
        if self.game_state.guess_history is None:
            self.game_state.guess_history = []
        context = self.get_llm_input()
        logging.debug(f"Context: {context}")
        llm_word = self.call_llm(context)
        if llm_word and len(llm_word) == 5 and llm_word.isalpha():
            logging.info(f"LLM chose: {llm_word}")
            return llm_word
        else:
            if llm_word:
                logging.info(f"LLM word '{llm_word}' is invalid, using fallback: {fallback_word}")
            else:
                logging.info(f"LLM returned None, using fallback: {fallback_word}")
            return fallback_word

    def play_round(self) -> bool:
        logging.info(f"\n--- Round {self.game_state.current_round+1} ---")
        word = self.guess_word()
        logging.info(f"Guessing word: {word}")
        click_word(self.page, word)
        self.page.wait_for_timeout(2500)
        logging.debug("Reading guess result...")
        result = update_game_state(self.page, self.game_state, word)
        logging.info(f"Guess result: {result}")
        while any(tile_result == 'u' for tile_result in result):
            logging.info("Word not in dictionary or not submitted properly. Clearing the word...")
            clear_word(self.page)
            logging.info(f"Retrying round {self.game_state.current_round+1}...")
            self.play_round()
            result = update_game_state(self.page, self.game_state, word)
        if self.game_state.guess_history[-1][1] == 'ccccc':
            logging.info("Congratulations! You've won the game!")
            logging.info(f"The word was: {word.upper()}")
        else:
            logging.debug("The game is still ongoing.")
        return self.game_state.guess_history[-1][1] == 'ccccc'

    def run(self):
        while self.game_state.current_round < self.game_state.max_guesses:
            self.play_round()
        if self.game_state.guess_history and self.game_state.guess_history[-1][1] == 'ccccc':
            logging.info(f"Game won in {self.game_state.current_round} guesses!")
        else:
            logging.info(f"Game lost after {self.game_state.current_round} guesses.") 