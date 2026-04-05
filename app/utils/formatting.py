def format_number(value: float) -> str:
    """
    Format a number with appropriate suffixes (K, M, B).

    Args:
        value (float): The number to format

    Returns:
        str: Formatted number string
    """
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.2f}K"
    else:
        return str(value)


def format_currency(value: float) -> str:
    """
    Format a currency value with appropriate suffixes and dollar sign.

    Args:
        value (float): The currency value to format

    Returns:
        str: Formatted currency string
    """
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.2f}K"
    else:
        return f"${value:.2f}"


def format_percentage(value: float) -> str:
    """
    Format a percentage value.

    Args:
        value (float): The percentage value to format

    Returns:
        str: Formatted percentage string
    """
    return f"{value:.2f}%"
