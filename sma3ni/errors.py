class PermanentError(Exception):
    """Retrying will not help (corrupt audio, too long, unknown request...). Fail fast."""
