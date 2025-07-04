from playwright.sync_api import Page
import logging
from typing import Optional

logger = logging.getLogger(__name__)

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
    locator = page.locator(selector)
    if locator.count() == 0:
        logger.info(f"No element found for selector: {selector}")
        return False
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
