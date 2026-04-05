class TickerNotFoundError(Exception):
    """Exception raised when a ticker symbol is not found."""

    pass


class RateLimitError(Exception):
    """Exception raised when rate limit is exceeded."""

    pass


class ValidationError(Exception):
    """Exception raised for validation errors."""

    pass


class ExternalAPIError(Exception):
    """Exception raised when there's an error with external API."""

    pass
