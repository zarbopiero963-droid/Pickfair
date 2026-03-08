import pytest


def test_numpy_import():
    import numpy


def test_pandas_import():
    import pandas


def test_sklearn_import():
    import sklearn


def test_matplotlib_import():
    import matplotlib


def test_pyside6_import():
    pytest.importorskip("PySide6")
