"""Publisher backends.

`base.Publisher` is the shared protocol. The CLI surface in `cli.py` picks
a concrete implementation based on the `--backend` flag.
"""

from swagger_studio_ruleset_publisher.publishers.base import (
    Backend,
    PublishResult,
    Publisher,
)
from swagger_studio_ruleset_publisher.publishers.cli_publisher import CliPublisher
from swagger_studio_ruleset_publisher.publishers.rest_publisher import RestPublisher

__all__ = ["Backend", "CliPublisher", "PublishResult", "Publisher", "RestPublisher"]
