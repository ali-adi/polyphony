def __getattr__(name: str) -> str:
    if name != "__version__":
        raise AttributeError(f"module 'polyphony' has no attribute {name!r}")
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("polyphony")
    except PackageNotFoundError:
        return "0.0.0+unknown"
