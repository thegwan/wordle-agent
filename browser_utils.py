import logging
from typing import Optional

from playwright.sync_api import Page

logger = logging.getLogger(__name__)

def wait_and_click(
    page: Page,
    selector: str,
    description: Optional[str] = None,
    highlight: bool = True,
    highlight_duration: int = 150,
) -> bool:
    """
    Wait for a selector to become visible and click it, optionally highlighting the element.

    Args:
        page: Playwright page object
        selector: CSS selector for the element to click
        description: Optional description for logging
        highlight: Whether to highlight the element before clicking
        highlight_duration: How long to highlight in ms (only if highlight=True)

    Returns:
        bool: True if element was found and clicked, False otherwise
    """
    locator = page.locator(selector)
    try:
        locator.wait_for(state="visible")
        if highlight:
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
            ''', highlight_duration)
            page.wait_for_timeout(highlight_duration)
        locator.click()
        logger.debug(f"{description or selector} clicked.")
        return True
    except Exception:
        if description:
            logger.debug(f"No {description} found, continuing...")
        return False

def wait_for_selector_safe(
    page: Page,
    selector: str,
    description: Optional[str] = None
) -> bool:
    """
    Wait for a selector with error handling and optional logging, using Locator.wait_for as recommended by Playwright docs.

    Args:
        page: Playwright page object
        selector: CSS selector to wait for
        description: Optional description for logging

    Returns:
        bool: True if selector was found, False if timeout occurred
    """
    locator = page.locator(selector)
    try:
        locator.wait_for(state="visible", timeout=5000)
        if description:
            logger.debug(f"{description} found.")
        return True
    except Exception:
        if description:
            logger.debug(f"No {description} found, continuing...")
        return False

def remove_ad_container(page: Page) -> None:
    """
    Remove the ad container if present on the page.

    Args:
        page: Playwright page object
    """
    logger.debug("Checking for ad container...")
    locator = page.locator('div[class*="adContainer"]')
    try:
        locator.wait_for(state="visible", timeout=1000)
        page.evaluate("""
        const ad = document.querySelector('div[class*="adContainer"]'); if (ad)
        ad.remove();
        """)
        logger.debug("Ad container removed.")
    except Exception:
        logger.debug("No ad container found, continuing...")
