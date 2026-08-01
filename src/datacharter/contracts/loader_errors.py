"""Shared contract-loading error type (split out to avoid import cycles)."""


class CharterError(Exception):
    """charter.yaml problem, phrased so the user knows exactly what to fix."""
