"""
Main entry point for avgangstider.
Re-exports CLI and core abstractions for backwards compatibility.
"""
from cli import main
from models import DepartureData, NormalizedStopData, StopPlaceState, WeatherData
from presenters import DeparturePresenter, StopPlacePresenter, WeatherPresenter

__all__ = [
    "DepartureData",
    "DeparturePresenter",
    "NormalizedStopData",
    "StopPlacePresenter",
    "StopPlaceState",
    "WeatherData",
    "WeatherPresenter",
    "main",
]

if __name__ == "__main__":
    main()
