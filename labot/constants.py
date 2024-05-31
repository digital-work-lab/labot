#!/usr/bin/env python
"""Constants for Labot"""
# pylint: disable=too-few-public-methods
# pylint: disable=colrev-missed-constant-usage


class ExitCodes:
    """Exit codes"""

    SUCCESS = 0
    FAIL = 1


class Colors:
    """Colors for CLI printing"""

    RED = "\033[91m"
    GREEN = "\033[92m"
    ORANGE = "\033[93m"
    BLUE = "\033[94m"
    END = "\033[0m"
