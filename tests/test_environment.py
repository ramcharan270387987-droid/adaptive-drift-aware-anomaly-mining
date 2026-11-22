"""Environment smoke tests for package installation and dependency imports."""

from importlib import import_module

import pytest


def test_project_package_imports():
    import_module("drift_anomaly")


@pytest.mark.parametrize(
    "module_name",
    [
        "joblib",
        "numpy",
        "pandas",
        "plotly",
        "psutil",
        "river",
        "sklearn",
        "scipy",
    ],
)
def test_runtime_dependency_imports(module_name):
    import_module(module_name)


def test_matplotlib_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path))
    import_module("matplotlib")


def test_yaml_loads():
    yaml = import_module("yaml")
    assert yaml.safe_load("seed: 42") == {"seed": 42}
