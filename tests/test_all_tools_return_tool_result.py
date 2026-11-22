"""Verify all BaseTool subclasses return ToolResult from async_call."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent / "custom_components" / "llm_intents"


class _AsyncCallVisitor(ast.NodeVisitor):
    """AST visitor that checks every return in async_call returns ToolResult."""

    def __init__(self, source_lines: list[str], filename: str) -> None:
        self.errors: list[str] = []
        self.source_lines = source_lines
        self.filename = filename

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "async_call":
            self._check_returns(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name == "async_call":
            self._check_returns(node)
        self.generic_visit(node)

    def _check_returns(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Walk all return statements inside async_call and verify they return ToolResult."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value is not None:
                lineno = node.lineno
                line_text = (
                    self.source_lines[lineno - 1].strip()
                    if lineno <= len(self.source_lines)
                    else "<unknown>"
                )
                if not self._is_tool_result_call(node.value):
                    self.errors.append(
                        f"{self.filename}:{lineno}: async_call returns non-ToolResult: {line_text}"
                    )

    @staticmethod
    def _is_tool_result_call(node: ast.expr) -> bool:
        """Check if an expression resolves to ToolResult, recursing through IfExp."""
        if isinstance(node, ast.IfExp):
            return _AsyncCallVisitor._is_tool_result_call(
                node.body
            ) and _AsyncCallVisitor._is_tool_result_call(node.orelse)
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name) and func.id == "ToolResult":
            return True
        if isinstance(func, ast.Attribute):
            return func.attr == "ToolResult"
        return False


def _get_base_tool_subclasses() -> list[Path]:
    """Find all .py files that define a class inheriting from BaseTool."""
    tool_files: list[Path] = []
    for file_path in sorted(ROOT.glob("*.py")):
        if file_path.name.startswith("_") or file_path.name == "utils":
            continue

        try:
            source = file_path.read_text()
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    # Direct: class Foo(BaseTool)
                    if isinstance(base, ast.Name) and base.id == "BaseTool":
                        tool_files.append(file_path)
                        break
                    # Indirect: class Foo(SearchWebTool), class Foo(FindPlacesBaseTool)
                    if isinstance(base, ast.Name) and base.id in (
                        "SearchWebTool",
                        "FindPlacesBaseTool",
                    ):
                        tool_files.append(file_path)
                        break
    return tool_files


@pytest.mark.parametrize("tool_file", _get_base_tool_subclasses())
def test_async_call_returns_tool_result(tool_file: Path) -> None:
    """Every async_call in a BaseTool subclass must return ToolResult."""
    source = tool_file.read_text()
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(tool_file))

    # Check if this file overrides async_call (not just inherits)
    has_async_call_override = False
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "async_call"
        ):
            has_async_call_override = True
            break

    if not has_async_call_override:
        pytest.skip(
            f"{tool_file.name} inherits async_call from parent, not checked here"
        )

    visitor = _AsyncCallVisitor(source_lines, tool_file.name)
    visitor.visit(tree)

    assert not visitor.errors, "\n".join(visitor.errors)
