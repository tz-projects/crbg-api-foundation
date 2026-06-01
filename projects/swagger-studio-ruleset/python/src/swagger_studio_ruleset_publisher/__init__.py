"""Publishes the API Foundation Spectral ruleset to SwaggerHub Studio."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("swagger-studio-ruleset-publisher")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
