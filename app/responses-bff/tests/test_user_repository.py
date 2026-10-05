"""Production BFF identity must not import ORM or repository modules."""
import ast
from pathlib import Path


def test_production_has_no_database_imports() -> None:
    for path in (Path(__file__).parents[1] / "src" / "bff").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            for module in modules:
                assert module not in ("banking_shared.models", "banking_shared.database", "bff.user_repository")
                assert not module.startswith(("sqlalchemy", "sqlmodel", "pwdlib"))
