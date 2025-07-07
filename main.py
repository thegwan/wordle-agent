import logging
import os
import re
from typing import List, Tuple, Optional

from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright, Page

from browser_utils import wait_for_selector_safe, remove_ad_container, wait_and_click
from level_0_wordle_agent import Level0WordleAgent
from level_1_wordle_agent import Level1WordleAgent

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

def run_agent():
    """
    Run the Wordle agent.
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
    run_agent()