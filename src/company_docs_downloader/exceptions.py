class ApplicationError(Exception):
    """Base error for the application."""


class ValidationError(ApplicationError):
    """Raised when user input is invalid."""


class ScraperError(ApplicationError):
    """Raised when a scraping flow fails."""


class AuthenticationError(ScraperError):
    """Raised when authentication fails."""


class DocumentNotFoundError(ScraperError):
    """Raised when the requested document is not available."""
