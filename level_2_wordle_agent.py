import logging
import os
import json
import pprint
from typing import List, Tuple, Optional
from openai import OpenAI
from dataclasses import dataclass
from browser_utils import (
    wait_and_click,
)
from playwright.sync_api import Page

pp = pprint.PrettyPrinter(indent=4)

class Level2WordleAgent:
    """
    Agent that plays Wordle using an LLM for play making and word selection.
    The system executes tool calls and interacts with the browser, the LLM controls the decision making.
    """
    def __init__(self, page: Page):
        """
        Initialize the Level2WordleAgent.
        
        Args:
            page: Page object representing the Wordle game.
        """
        self.page = page
        self.llm_client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.game_status = None
        self.action_history = []
        self.tool_registry = [
            {
                "name": "click_word",
                "description": "Guess a word by clicking letters on the on-screen keyboard.",
                "args": {
                    "word": {
                        "type": "str",
                        "description": (
                            "The 5-letter word to type"
                        ),
                    }
                },
                "returns": "None",
            },
            {
                "name": "clear_word",
                "description": "Clear the currently entered word if it was invalid or a mistake.",
                "args": {},
                "returns": "None",
            },
            {
                "name": "read_game_board",
                "description": "Read the current game board. This returns all guessed words and their result strings (e.g., 'cpaaa').",
                "args": {},
                "returns": "A list of tuples, each containing a 5-letter word and a 5-character string representing the result",
            },
            {
                "name": "end_game",
                "description": "End the game with a status of 'win' or 'loss'.",
                "args": {
                    "status": {
                        "type": "str",
                        "description": "The status of the game ('win' or 'loss').",
                    },
                },
                "returns": "None",
            }
        ]

    def format_tool_registry(self, registry: List[dict]) -> str:
        """
        Format the tool registry for LLM input.
        
        Args:
            registry: List of tool definitions.
        Returns:
            str: Formatted string describing available tools.
        """
        lines = []
        for tool in registry:
            # Tool header
            lines.append(f"- {tool['name']}: {tool['description']}")
            # Args
            lines.append(f"  Args:  ")
            if tool["args"]:
                for k, v in tool["args"].items():
                    lines.append(
                        f"    - {k} ({v['type']}): {v['description']}  "
                    )
            else:
                lines.append("    - None  ")
            # Returns
            lines.append(f"  Returns:  {tool['returns']}")

        return "\n".join(lines).rstrip()

    def format_action_history(self, action_history: List[Tuple[str, str]]) -> str:
        """
        Format the action history for LLM input.
        
        Args:
            action_history: List of (action, result) tuples.
        Returns:
            str: Formatted string of action history.
        """
        lines = []
        for i, (action, result) in enumerate(action_history):
            lines.append(f"Step {i+1}: {action} -> {result}")
        return "\n".join(lines).rstrip()

    def format_guess_history(self, guess_history: List[Tuple[str, str]]) -> str:
        """
        Format the guess history for LLM input.
        
        Args:
            guess_history: List of (guess, result) tuples.
        Returns:
            str: Formatted string of guess history.
        """
        lines = []
        for i, (guess, result) in enumerate(guess_history):
            lines.append(f"Round {i+1}: {guess} -> {result}")
        return "\n".join(lines).rstrip()

    def parse_action(self, action_json: str) -> Tuple[str, dict]:
        """
        Parse the action JSON string from the LLM into a tool name and arguments.
        
        Args:
            action_json: JSON string specifying the action.
        Returns:
            Tuple[str, dict]: Tool name and arguments dictionary.
        Raises:
            ValueError: If the JSON is invalid or missing required fields.
        """
        try:
            action_obj = json.loads(action_json)
            tool_name = action_obj["action"]["tool"]
            args = action_obj["action"].get("args", {})
            return tool_name, args
        except Exception as e:
            raise ValueError(
                f"Invalid action JSON: {action_json}, error: {e}"
            )

    def execute_tool(self, tool_name: str, args: dict) -> str:
        """
        Have the system execute the specified tool with given arguments.
        
        Args:
            tool_name: Name of the tool to execute.
            args: Arguments for the tool.
        Returns:
            str: Result message from the tool execution.
        """
        logging.info(f"Executing tool: {tool_name} with args: {args}")
        try:
            if tool_name == 'click_word':
                self.click_word(args['word'])
                return f"Word clicked! Your most recent guess is {args['word']}"
            elif tool_name == 'clear_word':
                self.clear_word()
                return f"You have just cleared your most recent guess."
            elif tool_name == 'read_game_board':
                result = self.read_game_board()
                return f"Game board read! Result: {result}"
            elif tool_name == 'end_game':
                self.end_game(args['status'])
                return f"Game ended with status: {args['status']}"
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except Exception as e:
            return f"Error executing tool {tool_name}: {e}"

    def get_llm_instructions(self) -> str:
        """
        Generate the system instruction prompt for the LLM, including game rules and tool usage.
        
        Returns:
            str: Instructions for the LLM.
        """
        tool_registry_str = self.format_tool_registry(self.tool_registry)
        return f"""
You are an expert Wordle player.

Your goal is to guess the hidden 5-letter word in as few attempts as possible.

### Game Rules
- You have 6 total guesses.
- After each guess, the game displays feedback:
  - 'c' means correct letter in correct position (green),
  - 'p' means correct letter, wrong position (yellow),
  - 'a' means letter not in the word (gray),
  - 'u' means the result is unknown or the guess was invalid.

### Tool Usage Strategy
- Guess a word using `self.`.
- Call `read_game_board` to observe the outcome of the guess.
- If the result of your last guess is `'uuuuu'`, it was invalid. You MUST ALWAYScall `clear_word` and try again.
- If any row on the board has result `'ccccc'`, the game is won. You should stop by calling `end_game` with status `'win'`.
- At every step, determine how many guesses you have left. If you have used all 6 guesses and none of them were correct, the game is lost. You should stop by calling `end_game` with status `'loss'`.
- Before making a guess, summarize the game board and the results of the previous guesses. Then, think carefully about what the next guess should be.

### Available Tools
{tool_registry_str}
---

### Output Format

Respond with JSON in the following format:
{{
  "reasoning": "Explain what you're doing and why.",
  "action": {{
    "tool": "tool_name",
    "args": {{ ... }}
  }}
}}

Examples of valid JSON responses:
{{
  "reasoning": "I need to make my first guess. CRANE is a good starting word.",
  "action": {{
    "tool": "click_word",
    "args": {{"word": "CRANE"}}
  }}
}}

{{
  "reasoning": "The previous guess ABCDE was not a valid word. I need to clear the word and try again.",
  "action": {{
    "tool": "clear_word",
    "args": {{}}
  }}
}}

Think step by step to successfully complete the Wordle game.
"""

    def get_llm_input(self) -> str:
        """
        Generate the input context for the LLM.
        
        Returns:
            str: Input context for the LLM.
        """
        return f"""
You are an expert Wordle player currently playing a game of Wordle.

Here is a history of past actions you have taken and their results:
{self.format_action_history(self.action_history)}

ALWAYS use your past actions and their results to decide what to do next.
ALWAYS summarize the game board and reason about the results of the previous guesses before making the next guess.
ALWAYS state out loud the number of remaining guesses before choosing a word to guess. End the game if you have won or used up all 6 guesses.
"""

    def call_llm(self, context: str) -> Optional[dict]:
        """
        Call the LLM with the provided context and parse the response.
        
        Args:
            context: The input context for the LLM.
        Returns:
            Optional[dict]: Parsed LLM response as a dictionary, or None on error.
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
            
            try:
                llm_obj = json.loads(content)
                return llm_obj
            except Exception as e:
                logging.error(f"Failed to parse LLM JSON: {e}")
                return None
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None

    # tools
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

    def clear_word(self) -> None:
        """
        Clear the currently entered word by clicking backspace 5 times.
        """
        for i in range(5):
            wait_and_click(
                self.page, 'button[data-key="←"]', description=f"Backspace {i+1}"
            )

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

    def run(self):
        """
        Main loop to play the Wordle game using the LLM for decision making.
        Continues until the game is won, lost, or an error occurs.
        """
        max_iterations = 50
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            if iteration > max_iterations:
                logging.warning("Max iterations reached. Exiting.")
                break

            # Build LLM input
            llm_input = self.get_llm_input()
            logging.info("\n--- BEGIN LLM INPUT ------\n")
            print(llm_input)
            logging.info("\n--- END LLM INPUT --------\n")

            # Call LLM and get the response
            llm_response = self.call_llm(llm_input)
            if not llm_response:
                logging.error("Failed to get LLM response.")
                break
            logging.info("\n--- BEGIN LLM RESPONSE ---\n")
            pp.pprint(llm_response)
            logging.info("\n--- END LLM RESPONSE  ----\n")

            # Parse LLM response and execute tool
            tool_name, args = self.parse_action(json.dumps(llm_response))
            result = self.execute_tool(tool_name, args)
            self.action_history.append(((tool_name, args), result))

            if "Error" in result:
                logging.error(f"Error executing tool: {result}")
                break

            if self.game_status is not None:
                break
        logging.info(f"Game ended with status: {self.game_status}")

            
