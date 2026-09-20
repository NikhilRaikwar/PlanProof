from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedSymbol:
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    is_exported: bool = False


def extract_python_symbols(path: Path, text: str) -> list[ExtractedSymbol]:
    tree = ast.parse(text, filename=str(path))
    symbols = [ExtractedSymbol(path.stem, "module", 1, max(1, text.count("\n") + 1))]
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = ",".join(alias.name for alias in node.names)
            symbols.append(
                ExtractedSymbol(imported, "import", node.lineno, node.end_lineno or node.lineno)
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            symbols.append(
                ExtractedSymbol(node.name, kind, node.lineno, node.end_lineno or node.lineno)
            )
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(
                            ExtractedSymbol(
                                f"{node.name}.{member.name}",
                                "method",
                                member.lineno,
                                member.end_lineno or member.lineno,
                            )
                        )
    return symbols


_TS_SYMBOL = re.compile(
    r"(?m)^\s*(export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)"
)
_TS_METHOD = re.compile(r"(?m)^\s{2,}(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(")
_TS_IMPORT = re.compile(r"(?m)^\s*import\s+(.+?)\s+from\s+['\"]")
_TS_EXPORT = re.compile(r"(?m)^\s*export\s*\{\s*([^}]+)\s*\}")


def extract_jsts_symbols(text: str) -> list[ExtractedSymbol]:
    symbols: list[ExtractedSymbol] = []
    for match in _TS_SYMBOL.finditer(text):
        token = match.group(0)
        kind = "class" if "class" in token else "function"
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(ExtractedSymbol(match.group(2), kind, line, line, bool(match.group(1))))
    for match in _TS_METHOD.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(ExtractedSymbol(match.group(1), "method", line, line))
    for match in _TS_IMPORT.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(ExtractedSymbol(match.group(1).strip(), "import", line, line))
    for match in _TS_EXPORT.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(ExtractedSymbol(match.group(1).strip(), "export", line, line, True))
    return symbols
