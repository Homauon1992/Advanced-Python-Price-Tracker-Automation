from __future__ import annotations

import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import pandas as pd
import undetected_chromedriver as uc
from loguru import logger
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


CSV_PATH = Path("price_history.csv")


@dataclass(frozen=True)
class ProductConfig:
    url: str
    target_price: float


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )


def get_site_name(url: str) -> str:
    hostname = urlparse(url).hostname or "unknown"
    if "amazon." in hostname:
        return "Amazon"
    if "ebay." in hostname:
        return "eBay"
    return hostname.replace("www.", "")


def parse_price(raw_text: str) -> float | None:
    """
    Convert a price-like text into a float.
    Handles patterns such as:
    - $1,299.99
    - 1.299,99 EUR
    """
    if not raw_text:
        return None

    cleaned = re.sub(r"[^\d,.\s]", "", raw_text).strip()
    if not cleaned:
        return None

    # Keep the first likely numeric token to avoid matching unrelated values.
    match = re.search(r"(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)", cleaned)
    if not match:
        return None

    number = match.group(1).replace(" ", "")
    if "," in number and "." in number:
        # Resolve mixed separators based on the last separator occurrence.
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif number.count(",") > 0 and number.count(".") == 0:
        # Single comma can be decimal or thousands separator.
        parts = number.split(",")
        if len(parts[-1]) == 2:
            number = number.replace(",", ".")
        else:
            number = number.replace(",", "")
    else:
        number = number.replace(",", "")

    try:
        return float(number)
    except ValueError:
        return None


def first_text(driver: uc.Chrome, selectors: Iterable[tuple[str, str]]) -> str | None:
    for by, value in selectors:
        try:
            elem = driver.find_element(by, value)
            text = elem.text.strip()
            if text:
                return text
        except Exception:
            continue
    return None


def scrape_product(driver: uc.Chrome, url: str) -> tuple[str, float]:
    site = get_site_name(url)
    driver.get(url)

    WebDriverWait(driver, 20).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    # Common selectors for Amazon/eBay + generic ecommerce pages.
    name_selectors = [
        (By.ID, "productTitle"),  # Amazon
        (By.CSS_SELECTOR, "h1.x-item-title__mainTitle span"),  # eBay
        (By.CSS_SELECTOR, "h1[itemprop='name']"),
        (By.CSS_SELECTOR, "h1"),
        (By.CSS_SELECTOR, "[data-testid='product-title']"),
    ]
    price_selectors = [
        (By.CSS_SELECTOR, "span.a-price span.a-offscreen"),  # Amazon
        (By.CSS_SELECTOR, "div.x-price-primary span.ux-textspans"),  # eBay
        (By.CSS_SELECTOR, "[itemprop='price']"),
        (By.CSS_SELECTOR, ".price"),
        (By.CSS_SELECTOR, "[data-testid='price']"),
    ]

    product_name = first_text(driver, name_selectors) or "Unknown Product"
    raw_price = first_text(driver, price_selectors)
    parsed_price = parse_price(raw_price or "")

    # Fallback: scrape visible body text for a likely currency pattern.
    if parsed_price is None:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        currency_match = re.search(r"[$€£]\s?\d[\d,.\s]*", body_text)
        parsed_price = parse_price(currency_match.group(0)) if currency_match else None

    if parsed_price is None:
        raise ValueError(f"Could not extract price from {site} page.")

    return product_name, parsed_price


def append_price_history(timestamp: str, product: str, site: str, price: float) -> None:
    row = pd.DataFrame(
        [{"Timestamp": timestamp, "Product": product, "Site": site, "Price": price}]
    )

    if CSV_PATH.exists():
        history = pd.read_csv(CSV_PATH)
        updated = pd.concat([history, row], ignore_index=True)
    else:
        updated = row

    updated.to_csv(CSV_PATH, index=False)


def alert_if_target_hit(product: str, site: str, current_price: float, target_price: float) -> None:
    if current_price <= target_price:
        logger.success(
            "ALERT: Price drop detected | Product='{}' | Site={} | Current={} | Target={}",
            product,
            site,
            current_price,
            target_price,
        )
    else:
        logger.info(
            "No alert | Product='{}' | Site={} | Current={} | Target={}",
            product,
            site,
            current_price,
            target_price,
        )


def detect_chrome_major_version() -> int | None:
    """
    Detect local Chrome major version on Windows via registry keys.
    Returns None when detection fails.
    """
    commands = [
        [
            "reg",
            "query",
            r"HKCU\Software\Google\Chrome\BLBeacon",
            "/v",
            "version",
        ],
        [
            "reg",
            "query",
            r"HKLM\Software\Google\Chrome\BLBeacon",
            "/v",
            "version",
        ],
        [
            "reg",
            "query",
            r"HKLM\Software\WOW6432Node\Google\Chrome\BLBeacon",
            "/v",
            "version",
        ],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            combined = f"{result.stdout}\n{result.stderr}"
            version_match = re.search(r"(\d+)\.\d+\.\d+\.\d+", combined)
            if version_match:
                return int(version_match.group(1))
        except Exception:
            continue
    return None


def create_driver(headless: bool = True) -> uc.Chrome:
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    detected_major = detect_chrome_major_version()
    driver_kwargs: dict[str, object] = {"options": options}
    if detected_major is not None:
        logger.info("Detected local Chrome major version: {}", detected_major)
        driver_kwargs["version_main"] = detected_major
    else:
        logger.warning(
            "Could not detect local Chrome version. Starting driver without explicit version."
        )

    try:
        return uc.Chrome(**driver_kwargs)
    except SessionNotCreatedException as exc:
        message = str(exc)
        fallback_match = re.search(r"Current browser version is (\d+)\.", message)
        fallback_major = int(fallback_match.group(1)) if fallback_match else None
        if fallback_major is not None and fallback_major != detected_major:
            logger.warning(
                "Driver/browser mismatch detected. Retrying with version_main={}.",
                fallback_major,
            )
            return uc.Chrome(options=options, version_main=fallback_major)
        raise


def track_prices(products: list[ProductConfig], min_delay: float = 3.0, max_delay: float = 8.0) -> None:
    if min_delay > max_delay:
        raise ValueError("min_delay cannot be greater than max_delay.")

    setup_logger()
    logger.info("Starting price tracker for {} products.", len(products))

    driver = create_driver(headless=True)
    try:
        for item in products:
            site = get_site_name(item.url)
            logger.info("Checking {}...", item.url)
            try:
                product_name, current_price = scrape_product(driver, item.url)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                append_price_history(now, product_name, site, current_price)
                alert_if_target_hit(product_name, site, current_price, item.target_price)
            except Exception as exc:
                logger.error("Failed to process URL={} | Reason={}", item.url, exc)

            delay = random.uniform(min_delay, max_delay)
            logger.info("Sleeping {:.2f}s before next request.", delay)
            time.sleep(delay)
    finally:
        driver.quit()
        logger.info("Price tracker finished.")


if __name__ == "__main__":
    # Sample product URLs for quick testing (generally scraping-friendly).
    # You can replace them with Amazon/eBay links later.
    PRODUCTS_TO_TRACK = [
        ProductConfig(
            url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            target_price=55.00,
        ),
        ProductConfig(
            url="https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
            target_price=40.00,
        ),
        ProductConfig(
            url="https://webscraper.io/test-sites/e-commerce/static/product/518",
            target_price=800.00,
        ),
    ]

    track_prices(PRODUCTS_TO_TRACK, min_delay=2.0, max_delay=5.0)
