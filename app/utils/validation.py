import re


def validate_ticker(symbol: str) -> str:
    """
    Validates and normalizes a stock ticker symbol.

    Args:
        symbol (str): The ticker symbol to validate

    Returns:
        str: The validated and normalized ticker symbol

    Raises:
        ValueError: If the ticker symbol is invalid
    """
    if not isinstance(symbol, str):
        raise ValueError("Ticker symbol must be a string")

    # Clean and normalize the symbol
    cleaned = symbol.upper().strip()

    # Validate format: 1-5 uppercase letters
    if not re.match(r"^[A-Z]{1,5}$", cleaned):
        raise ValueError("Invalid ticker format: must be 1-5 uppercase letters")

    return cleaned


def is_valid_ticker_format(symbol: str) -> bool:
    """
    Check if a string is a valid ticker format.

    Args:
        symbol (str): The ticker symbol to check

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(symbol, str):
        return False

    # Check if it's 1-5 uppercase letters
    return bool(re.match(r"^[A-Z]{1,5}$", symbol.upper().strip()))
