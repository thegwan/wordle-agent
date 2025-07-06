import logging
import os
import re
import json
from typing import List, Tuple, Optional
from openai import OpenAI
from dataclasses import dataclass
from browser_utils import (
    wait_and_click,
)
from playwright.sync_api import Page

@dataclass
class GameState:
    guess_history: List[Tuple[str, str]]
    current_round: int
    max_guesses: int

def click_word(page: Page, word: str) -> None:
    for letter in word.lower():
        selector = f'button[data-key="{letter}"]'
        if not wait_and_click(
            page, selector, description=f"Key '{letter}'"
        ):
            logging.error(f"Failed to click letter: {letter}")
    wait_and_click(page, 'button[data-key="↵"]', description="Enter key")
    page.wait_for_timeout(1000)

def clear_word(page: Page) -> None:
    for i in range(5):
        wait_and_click(
            page, 'button[data-key="←"]', description=f"Backspace {i+1}"
        )

def update_game_state(
    page: Page, game_state: GameState, guess: str
) -> str:
    # row index is 0-indexed, but current_round is 1-indexed
    result = read_game_state(page, game_state.current_round - 1)
    game_state.guess_history.append((guess, result))
    if 'u' not in result:
        game_state.current_round += 1
    return result

def read_game_state(page: Page, row_index: int = 0) -> str:
    page.wait_for_timeout(1000)
    tiles = page.locator('div[class*="Tile-module_tile"]').all()
    start_index = row_index * 5
    end_index = start_index + 5
    if len(tiles) < end_index:
        logging.error(
            f"Not enough tiles found. Expected at least {end_index}, "
            f"got {len(tiles)}"
        )
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

def check_game_won(result: str) -> bool:
    return result == 'ccccc'

class Level1WordleAgent:
    def __init__(self, page: Page):
        self.page = page
        self.llm_client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.game_state = GameState(
            guess_history=[],
            current_round=1,
            max_guesses=6,
        )
        self.tool_registry = [
            {
                "name": "click_word",
                "description": (
                    "Make a guess by clicking the letters on the on-screen "
                    "keyboard."
                ),
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
                "description": (
                    "Clear the current word."
                ),
                "args": {},
                "returns": "None",
            },
            {
                "name": "update_game_state",
                "description": (
                    "Read the result of the last guessed word and update the game state."
                ),
                "args": {
                    "guess": {
                        "type": "str",
                        "description": (
                            "The guess to update the game state with"
                        ),
                    }
                },
                "returns": """A 5-character string representing the result: 
     - 'c' = correct (green)
     - 'p' = present (yellow)
     - 'a' = absent (gray)
     - 'u' = unknown/not yet evaluated (tbd, empty, etc.)
                """,
            },
        ]

    def format_tool_registry(self, registry: List[dict]) -> str:
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

    def format_guess_history(self, guess_history: List[Tuple[str, str]]) -> str:
        lines = []
        for guess, result in guess_history:
            lines.append(f"{guess} -> {result}")
        return "\n".join(lines).rstrip()

    def parse_action(self, action_json: str) -> Tuple[str, dict]:
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
        logging.info(f"Executing tool: {tool_name} with args: {args}")
        try:
            if tool_name == 'click_word':
                click_word(self.page, args['word'])
                return "Word clicked!"
            elif tool_name == 'clear_word':
                clear_word(self.page)
                return "Word cleared!"
            elif tool_name == 'update_game_state':
                result = update_game_state(
                    self.page, self.game_state, args['guess']
                )
                return f"Game state updated! Result: {result}"
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except Exception as e:
            return f"Error executing tool {tool_name}: {e}"

    def get_llm_instructions(self) -> str:
        tool_registry_str = self.format_tool_registry(self.tool_registry)
        return f"""
You are an autonomous agent playing Wordle. Your goal is to win today's Wordle in as few guesses as possible.
Stop playing if you have won the game (result == 'ccccc') and let the user exit the game.

You have access to the following tools:
{tool_registry_str}

You must decide which tool to use based on the current situation.

After each guess, you MUST:
1. update the game state (using update_game_state)
2. If the result is 'ccccc', you have won and must stop.

If the result is 'uuuuu', this means the guess was not a valid word. You must clear the word and try again.

You MUST output your response in this exact JSON format:
{{
  "reasoning": "text",
  "action": {{
    "tool": "tool_name",
    "args": {{ ... }}
  }}
}}

Examples of valid responses:
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

Think carefully about the guess history before picking the next word to guess.
"""

    def get_llm_input(self, prev_action=None, prev_result=None) -> str:
        prev_action_str = (
            f"Previous action: {prev_action}\nResult: {prev_result}\n"
            if prev_action and prev_result else ""
        )
        guess_history_str = self.format_guess_history(self.game_state.guess_history)
        return f"""
You are an autonomous agent playing Wordle.
{prev_action_str}
Current round: {self.game_state.current_round}/{self.game_state.max_guesses}

Guess history:
{guess_history_str}

Pick the correct next action based on guess history and previous action. Think step by step about what you need to do next.
""".strip()

    def call_llm(self, context: str) -> Optional[dict]:
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

    def run(self):
        max_iterations = 50
        iteration = 0
        prev_action = None
        prev_result = None
        while self.game_state.current_round <= self.game_state.max_guesses:
            iteration += 1
            if iteration > max_iterations:
                logging.warning("Max iterations reached. Exiting.")
                break

            # Determine stopping conditions
            guess_history = self.game_state.guess_history
            last_result = guess_history[-1][1] if guess_history else None
            game_won = last_result == 'ccccc'
            game_lost = (
                self.game_state.current_round > self.game_state.max_guesses
                and not game_won
            )

            if game_won:
                logging.info(
                    f"Game won in {self.game_state.current_round} guesses!"
                )
                break

            if game_lost:
                logging.info(
                    f"Game lost after {self.game_state.current_round - 1} guesses."
                )
                break

            # Build LLM input
            llm_input = self.get_llm_input(
                prev_action=prev_action, prev_result=prev_result
            )
            logging.info("\n--- LLM INPUT ------\n")
            logging.info(llm_input)
            logging.info("\n--------------------\n")

            # Call LLM and get the response
            llm_response = self.call_llm(llm_input)
            if not llm_response:
                logging.error("Failed to get LLM response.")
                break
            logging.info("\n--- LLM RESPONSE ---\n")
            logging.info(llm_response)
            logging.info("\n--------------------\n")

            # Parse LLM response and execute tool
            tool_name, args = self.parse_action(json.dumps(llm_response))
            result = self.execute_tool(tool_name, args)
            prev_action = (tool_name, args)
            prev_result = result

            if "Error" in result:
                logging.error(f"Error executing tool: {result}")
                break
