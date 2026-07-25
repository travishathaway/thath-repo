"""Trivial greeting package for conda channel testing."""


def hello(name: str) -> str:
    """Return a greeting string for the given name."""
    return f"Hello, {name}!"
