"""Org-wide non-conformance scanner for SmartBear Swagger Studio."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("swagger-studio-scanner")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
