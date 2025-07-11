import logging
import os
from typing import List, Tuple, Optional
from openai import OpenAI
from browser_utils import  wait_and_click
from playwright.sync_api import Page


class WordleWorkflow:
    """
    Agent that plays Wordle using an LLM to select guesses. 
    The system controls the play, while the LLM only makes next word guesses.
    """
    def __init__(self, page: Page):
        """
        Initialize the WordleWorkflow.

        Args:
            page: Playwright Page object representing the Wordle game.
        """
        self.page = page
        self.llm_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.game_status = None  # None when in progress, "win" or "loss" when finished
        self.game_state = []     # List of (word, result) tuples representing the game board

    def get_llm_instructions(self) -> str:
        """
        Return the system prompt/instructions for the LLM, describing how to play Wordle and how to format its answer.

        Returns:
            str: Instructions for the LLM.
        """
        return """You are an expert Wordle player. You will be given a history of 
previous guesses and their results, as well as the current round and how many 
guesses you have left.

Always reason strategically about what word you should guess next. At the end, 
output your final guess in **this exact format**:  
`ANSWER: [your 5-letter word]` — no quotes, no extra text, no explanation 
after. Make sure the final answer is actually a 5 letter word.

If your answer does not have the final 5-letter answer in that format, it will 
be ignored.

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

    def get_llm_input(self) -> str:
        """
        Generate the input context for the LLM.
        
        Returns:
            str: Input context for the LLM.
        """
        game_history = ""
        for i, (word, result) in enumerate(self.game_state):
            game_history += f"Round {i+1}: {word.upper()} -> {result}\n"

        return f"""
Previous guesses:
{game_history}

Current round: {len(self.game_state)}. There are {6-len(self.game_state)} guesses left.

Think step by step and guess the next word.

End with:  
`ANSWER: [your word]`
"""

    def call_llm(self, context: str) -> Optional[str]:
        """
        Call the LLM with the provided context and return the response.
        
        Args:
            context: The input context for the LLM.
        Returns:
            Optional[str]: LLM response as a string, or None on error.
        """
        try:
            response = self.llm_client.responses.create(
                model="gpt-4.1-mini",
                instructions=self.get_llm_instructions(),
                input=context,
            )
            content = response.output_text
            if not content:
                logging.warning("LLM returned empty content.")
                return None
            return content
        except Exception as e:
            logging.error(f"Error calling LLM: {e}")
            return None

    # tool
    def click_word(self, word: str) -> None:
        """
        Click the on-screen keyboard to enter a 5-letter word and submit it.
        
        Args:
            word: The 5-letter word to guess.
        """
        for letter in word.lower():
            selector = f'button[data-key="{letter}"]'
            if not wait_and_click(
                self.page, selector, description=f"Key '{letter}'"
            ):
                logging.error(f"Failed to click letter: {letter}")
        wait_and_click(self.page, 'button[data-key="↵"]', description="Enter key")
        self.page.wait_for_timeout(1000)

    # tool
    def clear_word(self) -> None:
        """
        Clear the currently entered word by clicking backspace 5 times.
        """
        for i in range(5):
            wait_and_click(
                self.page, 'button[data-key="←"]', description=f"Backspace {i+1}"
            )
    # tool
    def read_game_board(self) -> List[Tuple[str, str]]:
        """
        Read the current game board and return all guessed words and their result strings.
        
        Returns:
            List[Tuple[str, str]]: List of (word, result) tuples for each guess.
        """
        self.page.wait_for_timeout(1000)
        tiles = self.page.locator('div[class*="Tile-module_tile"]').all()
        board = []
        for i in range(0, len(tiles), 5):
            row_tiles = tiles[i:i+5]
            word = ''
            result = ''
            for tile in row_tiles:
                letter = (tile.text_content() or '').strip().lower()
                data_state = tile.get_attribute('data-state') or ''
                word += letter if letter else ''
                if data_state == 'correct':
                    result += 'c'
                elif data_state == 'present':
                    result += 'p'
                elif data_state == 'absent':
                    result += 'a'
                else:
                    result += 'u'
            if len(word) == 5:
                board.append((word, result))
        return board

    # tool
    def end_game(self, status: str) -> None:
        """
        Set the game status to 'win' or 'loss'.
        
        Args:
            status: The status of the game ('win' or 'loss').
        """
        if status == "win":
            self.game_status = "win"
        elif status == "loss":
            self.game_status = "loss"
        else:
            logging.error(f"Invalid game status: {status}")


    def parse_llm_response(self, llm_response: str | None) -> str:
        """
        Parse the LLM response to extract the 5-letter answer in the required format.
        If the response is invalid or missing, return a fallback word.

        Args:
            llm_response: The raw response from the LLM.
        Returns:
            str: The parsed 5-letter word, or fallback if invalid.
        """
        fallback_word = "slope"
        if not llm_response:
            return fallback_word
        lines = llm_response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ANSWER:'):
                word = line[7:].strip().lower()
                if len(word) == 5 and word.isalpha():
                    return word
        return fallback_word
            
    def play_round(self):
        """
        Play a single round of Wordle: build LLM input, get a guess, submit it, handle invalid guesses,
        update game state, and check for win/loss conditions.
        """

        while True:
            # Build LLM input
            llm_input = self.get_llm_input()
            logging.info("\n--- BEGIN LLM INPUT ------\n")
            print(llm_input)
            logging.info("\n--- END LLM INPUT --------\n")

            # Call LLM and get the response
            llm_response = self.call_llm(llm_input)
            if not llm_response:
                logging.error("Failed to get LLM response.")
                
            logging.info("\n--- BEGIN LLM RESPONSE ---\n")
            print(llm_response)
            logging.info("\n--- END LLM RESPONSE  ----\n")
            
            word = self.parse_llm_response(llm_response)

            logging.info(f"Guessing word: {word}")
            self.click_word(word)
            self.game_state = self.read_game_board()
            
            last_result = self.game_state[-1][1]
            if any(tile_result == 'u' for tile_result in last_result):
                logging.info("Word not in dictionary or not submitted properly. Clearing the word...")
                self.clear_word()
                self.game_state.pop()
                logging.info(f"Retrying round {len(self.game_state)}...")
                continue
            break
            
        if last_result == "ccccc":
            self.end_game("win")
        elif len(self.game_state) == 6:
            self.end_game("loss")

    def run(self):
        """
        Main loop to play the Wordle game using the LLM only for word guessing.
        Continues until the game is won, lost, or an error occurs.
        """
        while len(self.game_state) < 6:
            logging.info(f"\n\nRound {len(self.game_state)+1}")
            self.play_round()
            
            if self.game_status is not None:
                break
        
        logging.info(f"Game ended with status: {self.game_status}")