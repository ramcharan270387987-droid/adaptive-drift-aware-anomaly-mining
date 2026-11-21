from importlib import import_module


def test_environment_imports() -> None:
    for module in ("drift_anomaly", "numpy", "pandas", "sklearn", "river"):
        import_module(module)
