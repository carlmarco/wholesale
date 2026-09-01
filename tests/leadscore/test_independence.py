"""
The scoring engine must stay independent of the wholesaler application.

This is the property that makes the engine reusable for another asset class, and
it is the one that erodes first: one convenient import of a property model and
the package is a real estate scorer again. These tests fail on that import
rather than at the point someone tries to reuse it.
"""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "leadscore"
MODULES = sorted(PACKAGE.rglob("*.py"))

# Vocabulary that would mean the engine has learned what it is scoring.
# "property" is deliberately absent: it collides with the Python builtin.
ASSET_TERMS = (
    "parcel", "violation", "foreclosure", "tax_sale", "arv",
    "equity", "repair", "situs", "wholesale", "lead_score",
)


def imported_modules(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_package_has_modules():
    """Guard against the globs silently matching nothing."""
    assert MODULES, f"no modules found under {PACKAGE}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_does_not_import_the_application(path):
    offenders = [
        module
        for module in imported_modules(path)
        if module.startswith("src.wholesaler") or module.startswith("config")
    ]
    assert not offenders, (
        f"{path.name} imports {offenders}. The engine must not depend on the "
        "wholesaler application, or it cannot be reused for another asset class."
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_only_imports_the_standard_library_and_itself(path):
    """No third-party dependencies, so the engine stays cheap to lift out."""
    allowed_roots = {"src", "__future__", "dataclasses", "typing", "abc", "math", "enum"}
    offenders = [
        module
        for module in imported_modules(path)
        if module.split(".")[0] not in allowed_roots
    ]
    assert not offenders, f"{path.name} pulls in {offenders}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_carries_no_asset_specific_vocabulary(path):
    """
    Names in the engine describe scoring, not property.

    A bucket called 'equity' or a field named 'parcel_id' would mean asset
    knowledge leaked in. Docstrings may cite examples, so only code is checked.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring or bare string literal
        name = getattr(node, "name", None) or getattr(node, "id", None) or getattr(node, "attr", None)
        if not isinstance(name, str):
            continue
        lowered = name.lower()
        for term in ASSET_TERMS:
            assert term not in lowered, (
                f"{path.name} defines {name!r}, which names a property concept. "
                "Asset vocabulary belongs in a profile, not the engine."
            )
