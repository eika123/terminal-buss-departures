import logging
from typing import TypeVar

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger("avgangstider.resilience")

T = TypeVar("T")


class MaxConsecutiveFailuresExceeded(RuntimeError):
    """Raised when an operation or service exceeds its consecutive failure threshold."""


class ConsecutiveFailureTracker:
    """
    Tracks consecutive failures for an operation or service.
    Resets counter to 0 upon success.
    Raises MaxConsecutiveFailuresExceeded if failures exceed max_failures.
    """

    def __init__(self, name: str, max_failures: int = 10):
        self.name = name
        self.max_failures = max_failures
        self.failure_count = 0

    def record_success(self) -> None:
        if self.failure_count > 0:
            logger.info(
                "Service/operation '%s' recovered after %d failure(s).",
                self.name,
                self.failure_count,
            )
        self.failure_count = 0

    def record_failure(self, error: Exception) -> None:
        self.failure_count += 1
        logger.warning(
            "Failure in '%s' (%d/%d): %s",
            self.name,
            self.failure_count,
            self.max_failures,
            error,
        )
        if self.failure_count > self.max_failures:
            msg = (
                f"Critical error: '{self.name}' exceeded maximum consecutive failures limit "
                f"({self.max_failures}). Program is terminating. Last error: {error}"
            )
            logger.critical(msg)
            raise MaxConsecutiveFailuresExceeded(msg) from error


def create_resilient_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Session:
    """
    Creates a requests.Session with urllib3 Retry configured for exponential backoff.
    Backoff sleep formula: {backoff_factor} * (2 ** ({retry_number} - 1))
    e.g. 0.5s -> 1.0s -> 2.0s
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
