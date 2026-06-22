"""Repository automation discovery for Super Looper.

The audit layer is intentionally conservative. It inventories repo-native
evidence, ranks possible automation candidates, and allocates autonomy ceilings;
it does not claim that static evidence is enough to build or schedule a loop.
"""

from __future__ import annotations

import configparser
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .design import build_spec
from .validate import max_autonomy


class RepoAuditError(RuntimeError):
    """Raised when a repository audit cannot proceed."""


_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".super-looper",
}
_KEEP_DOT_DIRS = {".github"}
_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    "",
}
_LANG_SUFFIXES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".md": "markdown",
}
_SCRIPT_NAMES = {
    "test": "test",
    "tests": "test",
    "pytest": "test",
    "unit": "test",
    "integration": "test",
    "lint": "lint",
    "ruff": "lint",
    "format": "format",
    "fmt": "format",
    "typecheck": "typecheck",
    "type-check": "typecheck",
    "types": "typecheck",
    "mypy": "typecheck",
    "pyright": "typecheck",
    "build": "build",
    "check": "check",
}


_SCRIPT_NAME_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in sorted(_SCRIPT_NAMES, key=len, reverse=True)) + r")\b"
)


def _name_matches_script(lowered_name: str) -> bool:
    """Word-boundary match (#9): `latest` must NOT match `test`, but `test` / `test:cov` do."""
    return bool(_SCRIPT_NAME_RE.search(lowered_name))


_COMMAND_CATEGORY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("test", re.compile(r"\b(pytest|tox|nox|unittest|npm\s+test|pnpm\s+test|yarn\s+test|cargo\s+test|go\s+test|make\s+test)\b")),
    ("typecheck", re.compile(r"\b(mypy|pyright|tsc|typecheck|type-check|type\s+check)\b")),
    ("lint", re.compile(r"\b(ruff|flake8|eslint|pylint|clippy|golangci-lint|make\s+lint|npm\s+run\s+lint|pnpm\s+lint|yarn\s+lint)\b")),
    ("format", re.compile(r"\b(black|prettier|ruff\s+format|cargo\s+fmt|gofmt|make\s+format|make\s+fmt)\b")),
    ("build", re.compile(r"\b(build|python\s+-m\s+build|cargo\s+build|go\s+build|npm\s+run\s+build|pnpm\s+build|yarn\s+build)\b")),
    ("security", re.compile(r"\b(bandit|pip-audit|npm\s+audit|cargo\s+audit|trivy|semgrep)\b")),
    ("syntax", re.compile(r"\bcompileall\b")),
]


@dataclass(frozen=True)
class Gate:
    """A statically discovered verification command."""

    command: str
    source: str
    category: str
    strength: str
    confidence: str
    requires_network: bool
    destructive: bool
    rationale: str


def _norm(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _read_text(path: Path, max_bytes: int = 200_000) -> str:
    if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in {"Makefile", "Dockerfile"}:
        return ""
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _walk_files(repo_path: Path, max_files: int) -> List[str]:
    files: List[str] = []
    for root, dirs, names in os.walk(repo_path):
        dirs[:] = [
            d
            for d in dirs
            if d in _KEEP_DOT_DIRS
            or (d not in _IGNORE_DIRS and not d.startswith(".") and not d.startswith(".egg-info"))
        ]
        root_path = Path(root)
        for name in names:
            rel = _norm(str((root_path / name).relative_to(repo_path)))
            files.append(rel)
            if len(files) >= max_files:
                return sorted(files)
    return sorted(files)


def _language_summary(files: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for rel in files:
        lang = _LANG_SUFFIXES.get(Path(rel).suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items()))


def _top_level_python_roots(files: Sequence[str]) -> List[str]:
    roots: List[str] = []
    for preferred in ("src", "tests", "test", "lib", "packages", "scripts"):
        if any(rel == preferred or rel.startswith(preferred + "/") for rel in files if rel.endswith(".py")):
            roots.append(preferred)
    top_dirs: Dict[str, int] = {}
    for rel in files:
        if not rel.endswith(".py") or "/" not in rel:
            continue
        top = rel.split("/", 1)[0]
        if top in set(roots) or top.startswith(".") or top in {"docs", "examples", "case-studies", "case_studies"}:
            continue
        top_dirs[top] = top_dirs.get(top, 0) + 1
    for top, count in sorted(top_dirs.items(), key=lambda item: (-item[1], item[0])):
        if count >= 2:
            roots.append(top)
        if len(roots) >= 6:
            break
    return roots


def _classify_command(command: str) -> str:
    lower = command.lower()
    for category, pattern in _COMMAND_CATEGORY_PATTERNS:
        if pattern.search(lower):
            return category
    return "check"


def _gate_strength(category: str, command: str, source: str) -> str:
    lower = command.lower()
    if category == "test":
        return "strong"
    if category in {"typecheck", "lint", "security"}:
        return "medium"
    if category == "build":
        return "medium"
    if category == "syntax":
        return "weak"
    if "ci" in source.lower() or ".github/workflows" in source:
        return "medium"
    return "weak"


def _requires_network(command: str) -> bool:
    lower = command.lower()
    return any(term in lower for term in (" install", "pip install", "npm install", "pnpm install", "yarn install", "cargo fetch", "go get", "docker pull"))


def _is_destructive(command: str) -> bool:
    lower = command.lower()
    return any(term in lower for term in (" rm -rf ", "git push", "publish", "deploy", "release", "terraform apply"))


def _split_ci_command(command: str) -> List[str]:
    """Split simple chained CI commands into auditable verifier candidates."""
    return [part.strip() for part in re.split(r"\s+(?:&&|\|\|)\s+|;\s*", command) if part.strip()]


def _is_setup_or_log_command(command: str) -> bool:
    lower = command.strip().lower()
    setup_prefixes = (
        "apt-get ",
        "apt ",
        "brew ",
        "cargo fetch",
        "cd ",
        "cp ",
        "echo ",
        "git config ",
        "mkdir ",
        "npm ci",
        "npm install",
        "pip install",
        "pnpm install",
        "python -m pip install",
        "python3 -m pip install",
        "printf ",
        "uv pip install",
        "yarn install",
    )
    if lower.startswith(setup_prefixes):
        return True
    return bool(re.match(r"^[a-z_][a-z0-9_-]*=.*", lower))


def _make_gate(command: str, source: str, rationale: str) -> Gate:
    category = _classify_command(command)
    return Gate(
        command=command.strip(),
        source=source,
        category=category,
        strength=_gate_strength(category, command, source),
        confidence="confirmed_by_static_config",
        requires_network=_requires_network(command),
        destructive=_is_destructive(command),
        rationale=rationale,
    )


def _add_gate(gates: List[Gate], command: str, source: str, rationale: str) -> None:
    command = " ".join(command.strip().split())
    if not command:
        return
    if any(g.command == command and g.source == source for g in gates):
        return
    gates.append(_make_gate(command, source, rationale))


def _node_manager(files: Sequence[str]) -> str:
    file_set = set(files)
    if "pnpm-lock.yaml" in file_set:
        return "pnpm"
    if "yarn.lock" in file_set:
        return "yarn"
    return "npm"


def _discover_python_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    py_roots = _top_level_python_roots(files)
    if py_roots:
        _add_gate(
            gates,
            "python -m compileall -q " + " ".join(py_roots),
            "python-files",
            "Python files exist; compileall is a cheap syntax canary, not a behavioral gate.",
        )

    file_set = set(files)
    pyproject = repo / "pyproject.toml"
    pyproject_text = _read_text(pyproject) if "pyproject.toml" in file_set else ""
    setup_cfg = repo / "setup.cfg"
    setup_text = _read_text(setup_cfg) if "setup.cfg" in file_set else ""
    has_tests = any(
        rel.endswith(".py")
        and (
            rel.startswith(("tests/", "test/"))
            or Path(rel).name.startswith("test_")
            or Path(rel).name.endswith("_test.py")
        )
        for rel in files
    )

    if has_tests or "[tool.pytest" in pyproject_text or "[tool.pytest" in setup_text:
        _add_gate(gates, "python -m pytest", "python-test-discovery", "Tests or pytest configuration were found.")
    if "[tool.ruff" in pyproject_text or "ruff" in pyproject_text:
        _add_gate(gates, "ruff check .", "pyproject.toml", "Ruff configuration or dependency reference was found.")
    if "[tool.mypy" in pyproject_text or "mypy" in pyproject_text:
        _add_gate(gates, "mypy .", "pyproject.toml", "Mypy configuration or dependency reference was found.")
    if "[tool.pyright" in pyproject_text or "pyright" in pyproject_text:
        _add_gate(gates, "pyright", "pyproject.toml", "Pyright configuration or dependency reference was found.")


def _discover_package_json_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    if "package.json" not in set(files):
        return
    text = _read_text(repo / "package.json")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return
    for name, command in sorted(scripts.items()):
        if not isinstance(command, str):
            continue
        lowered = name.lower()
        if _name_matches_script(lowered):
            manager = _node_manager(files)
            run_cmd = f"{manager} run {name}" if name not in {"test"} or manager != "npm" else "npm test"
            _add_gate(gates, run_cmd, "package.json", f"package.json script `{name}` maps to `{command}`.")


def _discover_make_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    if "Makefile" not in set(files):
        return
    text = _read_text(repo / "Makefile")
    for line in text.splitlines():
        if line.startswith(("\t", " ", "#", ".")):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?![=])", line)
        if not match:
            continue
        target = match.group(1)
        lowered = target.lower()
        if _name_matches_script(lowered):
            _add_gate(gates, f"make {target}", "Makefile", f"Makefile target `{target}` was found.")


def _discover_tox_nox_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    file_set = set(files)
    if "tox.ini" in file_set:
        parser = configparser.ConfigParser()
        try:
            parser.read(repo / "tox.ini", encoding="utf-8")
        except configparser.Error:
            parser = configparser.ConfigParser()
        envlist = ""
        if parser.has_section("tox"):
            envlist = parser.get("tox", "envlist", fallback="")
        envs = [e.strip() for e in re.split(r"[, \n]+", envlist) if e.strip()]
        interesting = [env for env in envs if any(key in env.lower() for key in ("py", "test", "lint", "type", "mypy", "ruff"))]
        if interesting:
            _add_gate(gates, "tox -e " + ",".join(interesting[:4]), "tox.ini", "tox envlist includes test/lint/typecheck-like environments.")
        else:
            _add_gate(gates, "tox", "tox.ini", "tox.ini exists.")
    if "noxfile.py" in file_set:
        text = _read_text(repo / "noxfile.py")
        names = re.findall(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*session", text)
        interesting = [name for name in names if any(key in name.lower() for key in ("test", "lint", "type", "mypy", "ruff"))]
        for name in interesting[:5]:
            _add_gate(gates, f"nox -s {name}", "noxfile.py", f"nox session `{name}` was found.")


def _workflow_run_blocks(text: str) -> Iterable[str]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- run:"):
            value = stripped[6:].strip()
        elif stripped.startswith("run:"):
            value = stripped[4:].strip()
        else:
            continue
        if value and value not in {"|", ">"}:
            yield value.strip("\"'")
            continue
        block: List[str] = []
        base_indent = len(line) - len(line.lstrip())
        for next_line in lines[idx + 1:]:
            indent = len(next_line) - len(next_line.lstrip())
            if next_line.strip() and indent <= base_indent:
                break
            candidate = next_line.strip()
            if candidate and not candidate.startswith("#"):
                block.append(candidate)
        for candidate in _join_continuations(block):
            yield candidate


def _join_continuations(lines: Sequence[str]) -> List[str]:
    commands: List[str] = []
    current = ""
    for line in lines:
        item = line.strip()
        if not item:
            continue
        current = f"{current} {item}".strip() if current else item
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        commands.append(current)
        current = ""
    if current:
        commands.append(current)
    return commands


def _discover_ci_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    workflow_files = [rel for rel in files if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))]
    for rel in workflow_files:
        text = _read_text(repo / rel)
        for command in _workflow_run_blocks(text):
            for segment in _split_ci_command(command):
                if _is_setup_or_log_command(segment):
                    continue
                category = _classify_command(segment)
                if category in {"test", "lint", "typecheck", "build", "security", "syntax"}:
                    _add_gate(gates, segment, rel, "GitHub Actions workflow run step looks like a verifier.")


def _discover_language_gates(repo: Path, files: Sequence[str], gates: List[Gate]) -> None:
    file_set = set(files)
    if "Cargo.toml" in file_set:
        _add_gate(gates, "cargo test", "Cargo.toml", "Rust project manifest exists.")
        _add_gate(gates, "cargo clippy --all-targets -- -D warnings", "Cargo.toml", "Rust project manifest exists.")
    if "go.mod" in file_set:
        _add_gate(gates, "go test ./...", "go.mod", "Go module exists.")
    if any(rel.endswith((".ts", ".tsx")) for rel in files) and "package.json" in file_set:
        manager = _node_manager(files)
        _add_gate(gates, f"{manager} run typecheck", "typescript-files", "TypeScript files and package.json exist; confirm script before running.")


def discover_gates(repo_path: str, files: Optional[Sequence[str]] = None, max_files: int = 50_000) -> List[Dict[str, Any]]:
    """Return a conservative gate inventory for a local repository."""
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise RepoAuditError(f"repo path does not exist: {repo}")
    files = list(files) if files is not None else _walk_files(repo, max_files)
    gates: List[Gate] = []
    _discover_python_gates(repo, files, gates)
    _discover_package_json_gates(repo, files, gates)
    _discover_make_gates(repo, files, gates)
    _discover_tox_nox_gates(repo, files, gates)
    _discover_ci_gates(repo, files, gates)
    _discover_language_gates(repo, files, gates)
    sorted_gates = sorted(
        gates,
        key=lambda g: (
            {"strong": 0, "medium": 1, "weak": 2}.get(g.strength, 9),
            g.requires_network,
            g.destructive,
            g.category,
            g.command,
        ),
    )
    return [
        {
            "id": f"gate-{idx:03d}",
            "command": gate.command,
            "source": gate.source,
            "category": gate.category,
            "strength": gate.strength,
            "confidence": gate.confidence,
            "requires_network": gate.requires_network,
            "destructive": gate.destructive,
            "rationale": gate.rationale,
        }
        for idx, gate in enumerate(sorted_gates, start=1)
    ]


def _gate_ids(gates: Sequence[Dict[str, Any]], *, categories: Sequence[str] = (), strengths: Sequence[str] = (), limit: int = 4) -> List[str]:
    out: List[str] = []
    for gate in gates:
        if categories and gate["category"] not in categories:
            continue
        if strengths and gate["strength"] not in strengths:
            continue
        out.append(gate["id"])
        if len(out) >= limit:
            break
    return out


def _score(leverage: int, gate: int, effort: int, risk: int) -> Dict[str, int]:
    total = max(0, min(100, leverage + gate + effort - risk))
    return {"total": total, "leverage": leverage, "gate": gate, "effort": effort, "risk_penalty": risk}


def _candidate(
    *,
    cid: str,
    title: str,
    recommended_path: str,
    max_agent_autonomy: str,
    gate_strength: str,
    score: Dict[str, int],
    why: Sequence[str],
    primary_gates: Sequence[str],
    missing_evidence: Sequence[str],
    next_step: str,
    scope_hint: Optional[Dict[str, List[str]]] = None,
    surface_id: Optional[str] = None,
    surface_title: Optional[str] = None,
    evidence_level: str = "static_evidence",
    hypothesis: bool = False,
    proposed_verifiers: Sequence[str] = (),
    discovery_questions: Sequence[str] = (),
) -> Dict[str, Any]:
    result = {
        "id": cid,
        "title": title,
        "recommended_path": recommended_path,
        "max_agent_autonomy": max_agent_autonomy,
        "gate_strength": gate_strength,
        "evidence_level": evidence_level,
        "hypothesis": hypothesis,
        "score": score,
        "why": list(why),
        "primary_gates": list(primary_gates),
        "proposed_verifiers": list(proposed_verifiers),
        "scope_hint": scope_hint or {"may_touch": [], "must_not_touch": []},
        "missing_evidence": list(missing_evidence),
        "discovery_questions": list(discovery_questions),
        "next_step": next_step,
    }
    if surface_id:
        result["surface_id"] = surface_id
    if surface_title:
        result["surface_title"] = surface_title
    return result


def _repo_traits(repo: Path, files: Sequence[str], gates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    languages = _language_summary(files)
    file_set = set(files)
    return {
        "languages": languages,
        "has_ci": any(rel.startswith(".github/workflows/") for rel in files),
        "has_tests": any(
            "/test" in rel.lower()
            or rel.lower().startswith(("tests/", "test/"))
            or Path(rel).name.startswith("test_")
            or Path(rel).name.endswith("_test.py")
            for rel in files
        ),
        "has_docs": any(rel.lower().startswith(("docs/", "doc/")) or rel.lower() in {"readme.md", "docs.md"} for rel in files),
        "has_dependency_automation": any(rel.startswith(".github/dependabot") or "renovate" in rel.lower() for rel in files),
        "lockfiles": sorted(rel for rel in file_set if rel.endswith(("lock", ".lock")) or rel in {"uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "go.sum"}),
        "gate_counts": {
            "strong": sum(1 for gate in gates if gate["strength"] == "strong"),
            "medium": sum(1 for gate in gates if gate["strength"] == "medium"),
            "weak": sum(1 for gate in gates if gate["strength"] == "weak"),
        },
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48].strip("-") or "surface"


def _repo_roots(files: Sequence[str]) -> List[str]:
    roots: Dict[str, int] = {}
    for rel in files:
        if "/" not in rel:
            continue
        top = rel.split("/", 1)[0]
        if top.startswith(".") or top in _IGNORE_DIRS:
            continue
        roots[top] = roots.get(top, 0) + 1
    preferred = [root for root in ("src", "lib", "packages", "tests", "test", "examples", "docs", "scripts") if root in roots]
    rest = [root for root, _ in sorted(roots.items(), key=lambda item: (-item[1], item[0])) if root not in preferred]
    return preferred + rest[:8]


def _path_exists_or_root(path: str, files: Sequence[str], roots: Sequence[str]) -> bool:
    clean = _norm(path).rstrip("/")
    if clean in roots:
        return True
    prefix = clean + "/"
    return any(rel == clean or rel.startswith(prefix) for rel in files)


def _mentioned_paths(command: str, files: Sequence[str]) -> List[str]:
    roots = _repo_roots(files)
    found: List[str] = []
    tokens = re.split(r"[\s,]+", command)
    for token in tokens:
        item = token.strip().strip("\"'`()[]{}")
        item = item.split(":", 1)[0]
        item = item.rstrip("/.,")
        if not item or item.startswith("-") or item.startswith("$") or item in {"#", "|", ">"}:
            continue
        if item.startswith("./"):
            item = item[2:]
        item = _norm(item)
        if _path_exists_or_root(item, files, roots):
            if item in roots:
                item += "/"
            found.append(item)
    return sorted(dict.fromkeys(found))


def _surface_languages(paths: Sequence[str], files: Sequence[str]) -> List[str]:
    langs = set()
    for path in paths:
        clean = path.rstrip("/")
        for rel in files:
            if rel == clean or rel.startswith(clean + "/"):
                lang = _LANG_SUFFIXES.get(Path(rel).suffix.lower())
                if lang:
                    langs.add(lang)
    return sorted(langs)


def _surface_strength(gate_ids: Sequence[str], gates_by_id: Dict[str, Dict[str, Any]]) -> str:
    strengths = {gates_by_id[gate_id]["strength"] for gate_id in gate_ids if gate_id in gates_by_id}
    if "strong" in strengths:
        return "strong"
    if "medium" in strengths:
        return "medium"
    if "weak" in strengths:
        return "weak"
    return "none"


def _surface_gate_counts(gate_ids: Sequence[str], gates_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    return {
        "strong": sum(1 for gate_id in gate_ids if gates_by_id.get(gate_id, {}).get("strength") == "strong"),
        "medium": sum(1 for gate_id in gate_ids if gates_by_id.get(gate_id, {}).get("strength") == "medium"),
        "weak": sum(1 for gate_id in gate_ids if gates_by_id.get(gate_id, {}).get("strength") == "weak"),
    }


def _add_surface(
    surfaces: Dict[str, Dict[str, Any]],
    *,
    sid: str,
    title: str,
    kind: str,
    paths: Sequence[str],
    evidence_files: Sequence[str],
    gate_ids: Sequence[str],
    files: Sequence[str],
    gates_by_id: Dict[str, Dict[str, Any]],
) -> None:
    paths = sorted(dict.fromkeys(_norm(path) for path in paths if path))
    evidence_files = sorted(dict.fromkeys(_norm(path) for path in evidence_files if path))
    existing = surfaces.get(sid)
    if existing is None:
        existing = {
            "id": sid,
            "title": title,
            "kind": kind,
            "paths": [],
            "evidence_files": [],
            "gate_ids": [],
            "categories": [],
            "languages": [],
            "gate_counts": {"strong": 0, "medium": 0, "weak": 0},
            "gate_strength": "none",
        }
        surfaces[sid] = existing
    existing["paths"] = sorted(dict.fromkeys(existing["paths"] + list(paths)))
    existing["evidence_files"] = sorted(dict.fromkeys(existing["evidence_files"] + list(evidence_files)))
    existing["gate_ids"] = sorted(dict.fromkeys(existing["gate_ids"] + list(gate_ids)))
    existing["categories"] = sorted({
        gates_by_id[gate_id]["category"]
        for gate_id in existing["gate_ids"]
        if gate_id in gates_by_id
    })
    existing["languages"] = _surface_languages(existing["paths"], files)
    existing["gate_counts"] = _surface_gate_counts(existing["gate_ids"], gates_by_id)
    existing["gate_strength"] = _surface_strength(existing["gate_ids"], gates_by_id)


def infer_surfaces(repo_path: str, gates: Sequence[Dict[str, Any]], files: Sequence[str]) -> List[Dict[str, Any]]:
    """Infer bounded repo surfaces that automation candidates can attach to."""
    del repo_path
    surfaces: Dict[str, Dict[str, Any]] = {}
    gates_by_id = {gate["id"]: gate for gate in gates}
    roots = _repo_roots(files)
    source_roots = [root + "/" for root in roots if root in {"src", "lib", "packages"}]
    test_root = "tests/" if any(rel.startswith("tests/") for rel in files) else ("test/" if any(rel.startswith("test/") for rel in files) else "")

    for gate in gates:
        gate_id = gate["id"]
        source = gate["source"]
        command = gate["command"]
        category = gate["category"]
        mentioned = _mentioned_paths(command, files)

        if source.startswith(".github/workflows/"):
            workflow_name = Path(source).name
            paths = [path for path in mentioned if not path.startswith(".github/")]
            if not paths and category == "test" and test_root:
                paths = [test_root]
            if not paths and category in {"lint", "typecheck", "format"}:
                paths = source_roots or [root + "/" for root in roots[:3]]
            _add_surface(
                surfaces,
                sid=f"ci-workflow-{_slug(workflow_name)}",
                title=f"workflow `{source}`",
                kind="ci_workflow",
                paths=paths,
                evidence_files=[source],
                gate_ids=[gate_id],
                files=files,
                gates_by_id=gates_by_id,
            )

        if category == "test":
            paths = [path for path in mentioned if path.startswith(("tests/", "test/"))]
            if not paths and test_root:
                paths = [test_root]
            for path in paths[:3]:
                _add_surface(
                    surfaces,
                    sid=f"test-suite-{_slug(path)}",
                    title=f"test suite `{path}`",
                    kind="test_suite",
                    paths=[path],
                    evidence_files=[source] if source not in {"python-test-discovery", "Cargo.toml", "go.mod"} else [],
                    gate_ids=[gate_id],
                    files=files,
                    gates_by_id=gates_by_id,
                )

        if category in {"lint", "typecheck", "format"}:
            quality_paths = mentioned or source_roots or ([test_root] if test_root else [])
            _add_surface(
                surfaces,
                sid=f"quality-{category}",
                title=f"{category} gate surface",
                kind="code_quality",
                paths=quality_paths[:6],
                evidence_files=[source] if "/" in source or source.endswith((".toml", ".json", "Makefile")) else [],
                gate_ids=[gate_id],
                files=files,
                gates_by_id=gates_by_id,
            )

        if any(path.startswith(("docs/", "examples/")) for path in mentioned) or "docs" in command.lower():
            doc_paths = [path for path in mentioned if path.startswith(("docs/", "examples/"))]
            if "docs" in command.lower() and any(rel.startswith("docs/") for rel in files):
                doc_paths.append("docs/")
            if doc_paths:
                _add_surface(
                    surfaces,
                    sid="docs-examples",
                    title="docs/examples executable surface",
                    kind="docs_examples",
                    paths=doc_paths,
                    evidence_files=[source] if source else [],
                    gate_ids=[gate_id],
                    files=files,
                    gates_by_id=gates_by_id,
                )

    def sort_key(surface: Dict[str, Any]) -> Tuple[int, int, int, str]:
        counts = surface["gate_counts"]
        kind_weight = {"ci_workflow": 0, "test_suite": 1, "code_quality": 2, "docs_examples": 3}.get(surface["kind"], 9)
        return (kind_weight, -counts["strong"], -counts["medium"], surface["id"])

    return sorted(surfaces.values(), key=sort_key)


def _surface_scope(surface: Dict[str, Any], files: Sequence[str]) -> Dict[str, List[str]]:
    roots = _repo_roots(files)
    source_roots = [root + "/" for root in roots if root in {"src", "lib", "packages"}]
    may_touch = [path for path in surface["paths"] if not path.startswith(".github/")]
    if surface["kind"] == "ci_workflow" and not may_touch:
        may_touch = source_roots or ["src/", "tests/"]
    if surface["kind"] == "test_suite":
        may_touch = sorted(dict.fromkeys(may_touch + source_roots[:2]))
    if surface["kind"] == "code_quality" and not may_touch:
        may_touch = source_roots or ["src/"]
    must_not_touch = [".github/workflows/", "release configuration", "credentials"]
    if surface["kind"] == "code_quality":
        must_not_touch.append("lockfiles unless explicitly required")
    return {"may_touch": may_touch[:8], "must_not_touch": must_not_touch}


def _build_surface_candidates(
    surfaces: Sequence[Dict[str, Any]],
    gates: Sequence[Dict[str, Any]],
    files: Sequence[str],
) -> List[Dict[str, Any]]:
    gates_by_id = {gate["id"]: gate for gate in gates}
    candidates: List[Dict[str, Any]] = []
    kind_limits = {"ci_workflow": 3, "test_suite": 2, "code_quality": 2, "docs_examples": 1}
    kind_counts: Dict[str, int] = {}

    for surface in surfaces:
        kind = surface["kind"]
        if kind_counts.get(kind, 0) >= kind_limits.get(kind, 1):
            continue
        gate_ids = [gate_id for gate_id in surface["gate_ids"] if gate_id in gates_by_id]
        if not gate_ids:
            continue
        strength = surface["gate_strength"]
        if kind == "ci_workflow" and strength in {"strong", "medium"}:
            score = _score(34, 0, 14, 10)
            candidates.append(_candidate(
                cid=f"surface-ci-repair-{_slug(surface['id'])}",
                title=f"Discover repair opportunities in {surface['title']}",
                recommended_path="discovery_required",
                max_agent_autonomy="L0",
                gate_strength=strength,
                evidence_level="static_gate_only",
                score=score,
                why=[
                    f"Static audit found {len(gate_ids)} verifier gate(s) tied to {surface['title']}.",
                    "A verifier alone is not a repair loop; the missing input is a real failing run or recurring failure class.",
                ],
                primary_gates=gate_ids[:5],
                scope_hint=_surface_scope(surface, files),
                missing_evidence=[
                    "one real failure from this exact workflow",
                    "confirmed dependency setup and runtime on a clean or disposable checkout",
                    "maintainer-approved path fence for the repair assistant",
                ],
                next_step=f"Fetch a real failing check or CI log for {surface['title']}, then promote one watched repair case study.",
                surface_id=surface["id"],
                surface_title=surface["title"],
            ))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        elif kind == "test_suite" and strength == "strong":
            candidates.append(_candidate(
                cid=f"surface-test-backfill-{_slug(surface['id'])}",
                title=f"Backfill regressions for {surface['title']}",
                recommended_path="human_in_loop",
                max_agent_autonomy="L1",
                gate_strength=strength,
                score=_score(32, 30, 12, 12),
                why=[
                    f"The audit found strong test gates scoped to {', '.join(surface['paths'])}.",
                    "The suite can reject bad code, but the target bug or invariant still needs human selection.",
                ],
                primary_gates=gate_ids[:4],
                scope_hint=_surface_scope(surface, files),
                missing_evidence=[
                    "specific issue, bug, or invariant to encode",
                    "human confirmation that the generated test captures the intended behavior",
                ],
                next_step=f"Pick one issue touching {', '.join(surface['paths'])} and run a test-only case study first.",
                surface_id=surface["id"],
                surface_title=surface["title"],
            ))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        elif kind == "code_quality" and strength in {"medium", "strong"}:
            categories = ", ".join(surface["categories"])
            candidates.append(_candidate(
                cid=f"surface-quality-fix-{_slug(surface['id'])}",
                title=f"Confirm {categories} repair opportunity for {', '.join(surface['paths']) or 'repo code'}",
                recommended_path="discovery_required",
                max_agent_autonomy="L0",
                gate_strength=strength,
                evidence_level="static_gate_only",
                score=_score(24, 0, 14, 8),
                why=[
                    f"The audit tied {categories} gates to a bounded path surface.",
                    "Static config proves the gate exists, but repair value requires actual failing lint/typecheck output.",
                ],
                primary_gates=gate_ids[:5],
                scope_hint=_surface_scope(surface, files),
                missing_evidence=[
                    f"one real failing {categories} command output",
                    "separate format-only changes from semantic changes",
                    "behavioral tests for any non-format source edits",
                ],
                next_step=f"Run the selected {categories} gates once; promote only if they fail with actionable output.",
                surface_id=surface["id"],
                surface_title=surface["title"],
            ))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        elif kind == "docs_examples":
            candidates.append(_candidate(
                cid=f"surface-docs-examples-{_slug(surface['id'])}",
                title=f"Check drift in {surface['title']}",
                recommended_path="human_in_loop" if strength in {"strong", "medium"} else "discovery_required",
                max_agent_autonomy="L1" if strength in {"strong", "medium"} else "L0",
                gate_strength=strength,
                score=_score(22, 16 if strength in {"strong", "medium"} else 0, 10, 12),
                why=[
                    "Docs or examples are mentioned by executable gates.",
                    "This can become valuable if the gate actually exercises published examples, not just builds pages.",
                ],
                primary_gates=gate_ids[:4],
                scope_hint=_surface_scope(surface, files),
                missing_evidence=[
                    "proof the gate fails when docs/examples drift from behavior",
                    "human-approved definition of stale or misleading documentation",
                ],
                next_step="Run the docs/example gate on a known-bad example before turning this into recurring automation.",
                surface_id=surface["id"],
                surface_title=surface["title"],
            ))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return candidates


def _paths_with_terms(files: Sequence[str], terms: Sequence[str], limit: int = 8) -> List[str]:
    matches: List[str] = []
    for rel in files:
        lower = rel.lower()
        if any(term in lower for term in terms):
            path = rel
            parts = rel.split("/")
            if len(parts) > 1:
                path = "/".join(parts[:2]) + ("/" if len(parts) > 2 else "")
            matches.append(path)
    return sorted(dict.fromkeys(matches))[:limit]


def _surface_gate_ids(surfaces: Sequence[Dict[str, Any]], kind: str, limit: int = 5) -> List[str]:
    out: List[str] = []
    for surface in surfaces:
        if surface["kind"] != kind:
            continue
        out.extend(surface["gate_ids"])
        if len(out) >= limit:
            break
    return sorted(dict.fromkeys(out))[:limit]


def _has_workflow_named(surfaces: Sequence[Dict[str, Any]], terms: Sequence[str]) -> bool:
    return any(
        surface["kind"] == "ci_workflow"
        and any(term in surface["title"].lower() for term in terms)
        for surface in surfaces
    )


def _build_imagined_candidates(
    repo: Path,
    traits: Dict[str, Any],
    surfaces: Sequence[Dict[str, Any]],
    gates: Sequence[Dict[str, Any]],
    files: Sequence[str],
) -> List[Dict[str, Any]]:
    """Propose creative loop hypotheses without promoting guesses to verified findings."""
    del repo
    candidates: List[Dict[str, Any]] = []
    strong_test_ids = _gate_ids(gates, categories=("test",), strengths=("strong",), limit=5)
    build_ids = _gate_ids(gates, categories=("build",), limit=5)
    quality_ids = _gate_ids(gates, categories=("lint", "typecheck", "format"), limit=5)
    docs_example_ids = _surface_gate_ids(surfaces, "docs_examples", limit=5)

    has_examples = any(rel.startswith("examples/") for rel in files)
    has_docs = traits["has_docs"]
    has_cli = bool(_paths_with_terms(files, ("test_cli", "/cli.", "/cli/", "commands/", "console_script", "entry_points"), limit=4))
    integration_paths = _paths_with_terms(files, ("integration", "integrations", "provider", "adapter", "plugin"), limit=8)
    benchmark_paths = _paths_with_terms(files, ("benchmark", "benchmarks", "perf", "performance", "profile"), limit=8)
    api_paths = _paths_with_terms(files, ("/api", "client", "sdk", "schema", "contract"), limit=8)
    release_signal = bool(build_ids or _has_workflow_named(surfaces, ("publish", "release", "build")) or any(
        rel in {"pyproject.toml", "package.json", "Cargo.toml", "go.mod"} for rel in files
    ))

    if traits["has_ci"] and traits["has_tests"] and strong_test_ids:
        candidates.append(_candidate(
            cid="hypothesis-ci-failure-intelligence",
            title="Mine CI history for recurring failures and flaky-test repair loops",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="none",
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(34, 0, 14, 6),
            why=[
                "The repo has CI and strong test gates, but static files do not show which failures recur.",
                "Actual run history could reveal high-leverage loops that a static scan cannot see.",
            ],
            primary_gates=strong_test_ids,
            proposed_verifiers=[
                "GitHub Actions failure-log clustering by workflow, command, and error signature",
                "rerun classifier: same commit fails then passes on rerun means likely flaky",
                "repair acceptance gate: failing workflow passes on the same clean checkout after the proposed change",
            ],
            scope_hint={
                "may_touch": ["tests/", "src/", "workflow-owned source paths"],
                "must_not_touch": [".github/workflows/ unless explicitly selected", "credentials", "release configuration"],
            },
            missing_evidence=[
                "recent CI failure logs or check-run history",
                "frequency of repeated failures by workflow and command",
                "one watched repair or quarantine proposal accepted by a human",
            ],
            discovery_questions=[
                "Which workflow fails most often?",
                "Do failures repeat on the same command or move around?",
                "Does rerunning the same commit pass without code changes?",
            ],
            next_step="Pull the last 50-100 CI failures, cluster by error signature, and choose one recurring failure for a watched case study.",
        ))

    if has_cli and strong_test_ids:
        cli_paths = _paths_with_terms(files, ("test_cli", "/cli.", "/cli/", "commands/"), limit=6) or ["CLI-related paths"]
        candidates.append(_candidate(
            cid="hypothesis-cli-contract-smoke",
            title="Protect CLI behavior with help/output smoke checks",
            recommended_path="human_in_loop",
            max_agent_autonomy="L1",
            gate_strength="strong",
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(28, 22, 12, 8),
            why=[
                f"CLI-shaped files were found: {', '.join(cli_paths[:4])}.",
                "CLI regressions are often cheap to catch with help text, exit-code, and golden-output checks.",
            ],
            primary_gates=strong_test_ids,
            proposed_verifiers=[
                "`<command> --help` exits 0 and includes expected subcommands/options",
                "minimal command smoke tests assert exit code and stable output shape",
                "golden-output snapshots for non-network commands",
            ],
            scope_hint={
                "may_touch": cli_paths[:6] + ["tests/"],
                "must_not_touch": ["release configuration", "credentials", "networked side effects"],
            },
            missing_evidence=[
                "list of commands whose output is stable enough to snapshot",
                "human approval for which output changes are user-visible regressions",
            ],
            discovery_questions=[
                "Which CLI commands are public and stable?",
                "Which commands can run offline and without secrets?",
            ],
            next_step="Create a test-only case study that snapshots one safe CLI command before allowing source edits.",
        ))

    if has_examples:
        example_gate_ids = docs_example_ids or strong_test_ids or quality_ids
        gate_strength = "medium" if docs_example_ids or quality_ids else ("strong" if strong_test_ids else "none")
        candidates.append(_candidate(
            cid="hypothesis-example-smoke-suite",
            title="Keep examples runnable with a lightweight smoke suite",
            recommended_path="human_in_loop" if example_gate_ids else "discovery_required",
            max_agent_autonomy="L1" if example_gate_ids else "L0",
            gate_strength=gate_strength,
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(30, 18 if example_gate_ids else 0, 12, 10),
            why=[
                "The repo contains examples, which often drift as APIs change.",
                "Examples are high-value maintainer artifacts, but the audit must prove they are executable before automation.",
            ],
            primary_gates=example_gate_ids[:5],
            proposed_verifiers=[
                "offline example import/parse smoke tests",
                "example command dry-runs with network and credentials disabled",
                "docs/example snippets executed under the repo's normal test runner",
            ],
            scope_hint={
                "may_touch": ["examples/", "docs/", "tests/"],
                "must_not_touch": ["credentials", "network-requiring examples unless mocked", "release configuration"],
            },
            missing_evidence=[
                "which examples are intended to run offline",
                "mocking strategy for network/provider calls",
                "one known API change that should break an example test",
            ],
            discovery_questions=[
                "Are examples executable tests, docs-only snippets, or demos requiring credentials?",
                "Which examples represent public API contracts?",
            ],
            next_step="Pick one offline example and build the smallest verifier that fails when its public API usage drifts.",
        ))

    if integration_paths:
        integration_gate_ids = strong_test_ids or quality_ids
        candidates.append(_candidate(
            cid="hypothesis-integration-compatibility-drift",
            title="Detect integration/provider compatibility drift",
            recommended_path="discovery_required" if not integration_gate_ids else "human_in_loop",
            max_agent_autonomy="L0" if not integration_gate_ids else "L1",
            gate_strength="strong" if strong_test_ids else ("medium" if quality_ids else "none"),
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(32, 20 if integration_gate_ids else 0, 10, 12),
            why=[
                f"Integration/provider-shaped paths were found: {', '.join(integration_paths[:5])}.",
                "These surfaces tend to break when upstream providers, adapters, or schemas shift.",
            ],
            primary_gates=integration_gate_ids[:5],
            proposed_verifiers=[
                "offline adapter contract tests with fake provider responses",
                "schema/fixture replay tests for each integration",
                "provider matrix smoke tests gated behind explicit credentials only in higher-risk runner mode",
            ],
            scope_hint={
                "may_touch": integration_paths[:6] + ["tests/"],
                "must_not_touch": ["real provider credentials", "networked production calls", "release configuration"],
            },
            missing_evidence=[
                "which integrations are public and recurring pain points",
                "fixtures or mocks that represent valid provider behavior",
                "decision on whether live-provider checks are allowed in disposable runners",
            ],
            discovery_questions=[
                "Which integrations have the highest issue or CI failure rate?",
                "Can each provider be tested offline with fixtures?",
            ],
            next_step="Choose one integration and create a fixture-backed contract test before proposing any repair loop.",
        ))

    if release_signal:
        release_gate_ids = build_ids or strong_test_ids or quality_ids
        candidates.append(_candidate(
            cid="hypothesis-release-package-smoke",
            title="Run pre-release package/install smoke checks",
            recommended_path="human_in_loop" if release_gate_ids else "discovery_required",
            max_agent_autonomy="L1" if release_gate_ids else "L0",
            gate_strength="medium" if build_ids or quality_ids else ("strong" if strong_test_ids else "none"),
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(30, 18 if release_gate_ids else 0, 12, 10),
            why=[
                "Package metadata, build gates, or publish/release workflows suggest release risk.",
                "A pre-release smoke loop can be valuable, but only after install/import checks are proven on a clean environment.",
            ],
            primary_gates=release_gate_ids[:5],
            proposed_verifiers=[
                "build artifact locally",
                "install artifact into a fresh environment",
                "import package or run CLI smoke command without network/secrets",
            ],
            scope_hint={
                "may_touch": ["packaging metadata", "tests/", "release smoke fixtures"],
                "must_not_touch": ["publishing credentials", "release tags", "deployment workflows"],
            },
            missing_evidence=[
                "confirmed package manager and clean install command",
                "a smoke command that proves the built artifact is usable",
                "manual dry-run on a disposable checkout or VM",
            ],
            discovery_questions=[
                "What artifact should a maintainer trust before release?",
                "Can install/import smoke checks run without secrets?",
            ],
            next_step="Run a clean build/install/import smoke check in a disposable environment and record the exact commands.",
        ))

    if benchmark_paths:
        candidates.append(_candidate(
            cid="hypothesis-performance-regression-watch",
            title="Watch for performance or benchmark regressions",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="none",
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(24, 0, 8, 12),
            why=[
                f"Performance-shaped paths were found: {', '.join(benchmark_paths[:5])}.",
                "Performance loops are valuable only if variance, baseline storage, and thresholds are explicit.",
            ],
            primary_gates=[],
            proposed_verifiers=[
                "benchmark command with pinned dataset/input",
                "threshold gate against a stored baseline with variance allowance",
                "no-regression report that includes environment metadata",
            ],
            scope_hint={
                "may_touch": benchmark_paths[:6] + ["benchmarks/", "tests/"],
                "must_not_touch": ["production workloads", "unbounded external API calls"],
            },
            missing_evidence=[
                "stable benchmark command",
                "baseline and acceptable variance",
                "runner environment controls",
            ],
            discovery_questions=[
                "Which benchmark matters to maintainers?",
                "What variance is normal on the runner?",
            ],
            next_step="Run the benchmark three times on the same runner and decide whether variance is low enough for a gate.",
        ))

    if has_docs and api_paths and strong_test_ids:
        candidates.append(_candidate(
            cid="hypothesis-public-api-doc-drift",
            title="Detect public API documentation drift",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="none",
            evidence_level="hypothesis",
            hypothesis=True,
            score=_score(26, 0, 10, 10),
            why=[
                f"API/client/schema-shaped paths were found: {', '.join(api_paths[:5])}.",
                "Docs drift can be high leverage, but static audit does not prove a doc verifier exists.",
            ],
            primary_gates=strong_test_ids[:3],
            proposed_verifiers=[
                "doctest or example execution for documented public API snippets",
                "API reference generation diff checked against source signatures",
                "schema snapshot tests for public request/response shapes",
            ],
            scope_hint={
                "may_touch": ["docs/", "examples/", "tests/"] + api_paths[:4],
                "must_not_touch": ["source behavior unless separately gated", "credentials"],
            },
            missing_evidence=[
                "source of truth for public API",
                "docs/examples that should execute as tests",
                "human approval for breaking-docs vs intentional API change",
            ],
            discovery_questions=[
                "Which APIs are public contracts?",
                "Can docs snippets run without secrets or network access?",
            ],
            next_step="Select one documented API snippet and build a verifier that fails if the source signature or behavior drifts.",
        ))

    return sorted(candidates, key=lambda item: (-item["score"]["total"], item["id"]))[:8]


def build_candidates(
    repo_path: str,
    gates: Sequence[Dict[str, Any]],
    files: Sequence[str],
    surfaces: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build a ranked conservative automation backlog from static evidence."""
    repo = Path(repo_path).resolve()
    traits = _repo_traits(repo, files, gates)
    surfaces = list(surfaces) if surfaces is not None else infer_surfaces(str(repo), gates, files)
    candidates: List[Dict[str, Any]] = _build_surface_candidates(surfaces, gates, files)
    candidates.extend(_build_imagined_candidates(repo, traits, surfaces, gates, files))
    strong_gate_ids = _gate_ids(gates, strengths=("strong",), limit=5)
    medium_gate_ids = _gate_ids(gates, strengths=("medium",), limit=5)
    syntax_gate_ids = _gate_ids(gates, categories=("syntax",), limit=3)
    lint_type_ids = _gate_ids(gates, categories=("lint", "typecheck", "format"), limit=5)

    if strong_gate_ids or medium_gate_ids:
        candidates.append(_candidate(
            cid="repo-native-verification-scheduler",
            title="Run repo-native verification as a scheduled health check",
            recommended_path="plain_scheduler",
            max_agent_autonomy="none",
            gate_strength="strong" if strong_gate_ids else "medium",
            score=_score(22, 30 if strong_gate_ids else 20, 18, 4),
            why=[
                "Static audit found repo-native verification commands.",
                "No agent needs to edit code; scheduling the gates is simpler and safer than a loop.",
            ],
            primary_gates=strong_gate_ids or medium_gate_ids,
            missing_evidence=[],
            next_step="Run the selected gates once on a clean checkout and capture timing/flakiness before scheduling.",
        ))

    if traits["has_ci"] and (strong_gate_ids or medium_gate_ids):
        candidates.append(_candidate(
            cid="ci-failure-repair-assistant",
            title="Discover CI failure repair opportunities from real runs",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="strong" if strong_gate_ids else "medium",
            evidence_level="static_gate_only",
            score=_score(32, 0, 12, 12),
            why=[
                "CI workflows and local verifier commands are present.",
                "Static files prove gates exist, but not that there is a recurring, actionable failure to repair.",
            ],
            primary_gates=(strong_gate_ids + medium_gate_ids)[:5],
            scope_hint={
                "may_touch": ["src/", "tests/", "packages/", "lib/"],
                "must_not_touch": [".github/workflows/", "lockfiles", "release configuration", "credentials"],
            },
            missing_evidence=[
                "recent failing CI log, check run, or repeated failure signature",
                "one proven manual pass on that real CI failure",
                "explicit scope for which packages or paths the repair assistant may edit",
                "accept-rate and regression tracking before any unattended trigger",
            ],
            next_step="Pull real CI failure history, cluster by error signature, and promote one watched repair only after choosing a concrete failure.",
        ))

    if traits["has_tests"] and strong_gate_ids:
        candidates.append(_candidate(
            cid="regression-test-backfill",
            title="Backfill regression tests for confirmed bugs or invariants",
            recommended_path="human_in_loop",
            max_agent_autonomy="L1",
            gate_strength="strong",
            score=_score(30, 30, 10, 14),
            why=[
                "Tests exist, so generated tests can be run by an independent tool gate.",
                "The missing ingredient is the specific bug, invariant, or issue to encode.",
            ],
            primary_gates=strong_gate_ids[:4],
            scope_hint={
                "may_touch": ["tests/", "test/"],
                "must_not_touch": ["production credentials", "release configuration"],
            },
            missing_evidence=[
                "specific bug report, invariant, or failing scenario",
                "human confirmation that the generated test asserts the intended behavior",
            ],
            next_step="Pick one issue or invariant and generate a test-only case study before allowing source edits.",
        ))

    if traits["lockfiles"] or traits["has_dependency_automation"]:
        candidates.append(_candidate(
            cid="dependency-update-repair",
            title="Repair dependency update fallout under existing gates",
            recommended_path="human_in_loop" if strong_gate_ids else "discovery_required",
            max_agent_autonomy="L1" if strong_gate_ids else "L0",
            gate_strength="strong" if strong_gate_ids else "none",
            score=_score(28, 26 if strong_gate_ids else 4, 8, 16),
            why=[
                "Lockfiles or dependency automation markers are present.",
                "Dependency updates recur, but they need real tests before automated repair is safe.",
            ],
            primary_gates=strong_gate_ids[:4],
            scope_hint={
                "may_touch": ["dependency manifests", "lockfiles", "tests/"],
                "must_not_touch": ["release secrets", "CI deployment credentials"],
            },
            missing_evidence=[] if strong_gate_ids else ["repo-native test gate before repair can be trusted"],
            next_step="Run one dependency-update case in propose-only mode and measure whether existing gates catch breakage.",
        ))

    if lint_type_ids:
        candidates.append(_candidate(
            cid="lint-typecheck-fix-assistant",
            title="Confirm lint/typecheck repair opportunity with narrow scope",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="medium",
            evidence_level="static_gate_only",
            score=_score(22, 0, 14, 8),
            why=[
                "Static audit found lint, format, or typecheck commands.",
                "A lint/typecheck repair loop needs actual failing command output; otherwise this is just existing CI/preflight.",
            ],
            primary_gates=lint_type_ids,
            scope_hint={
                "may_touch": ["src/", "tests/", "type stubs", "format-only files"],
                "must_not_touch": ["lockfiles unless explicitly required", ".github/workflows/", "release configuration"],
            },
            missing_evidence=[
                "one real failing lint, format, or typecheck output",
                "format/lint commands must be confirmed non-destructive or run on a disposable checkout",
                "behavioral tests for any non-format source changes",
            ],
            next_step="Run the selected quality gates once; if they fail, promote the captured failure output as the loop input.",
        ))

    if syntax_gate_ids:
        candidates.append(_candidate(
            cid="syntax-canary",
            title="Run a cheap syntax canary before deeper automation",
            recommended_path="plain_scheduler",
            max_agent_autonomy="none",
            gate_strength="weak",
            score=_score(12, 8, 20, 2),
            why=[
                "Python source files exist, so compileall can catch syntax regressions cheaply.",
                "This is useful as a preflight but too weak for behavioral automation claims.",
            ],
            primary_gates=syntax_gate_ids,
            missing_evidence=["repo-native tests, lint, typecheck, or build gates before claiming correctness"],
            next_step="Keep compileall as the first gate, then promote to repo-native gates for maintainer-grade reports.",
        ))

    if traits["has_docs"]:
        candidates.append(_candidate(
            cid="docs-runbook-drift",
            title="Detect docs or runbook drift against executable behavior",
            recommended_path="discovery_required",
            max_agent_autonomy="L0",
            gate_strength="none",
            score=_score(20, 0, 8, 12),
            why=[
                "Documentation exists, but static audit did not prove a doc-specific verifier.",
                "Docs updates are often subjective unless backed by executable examples or link/API checks.",
            ],
            primary_gates=[],
            scope_hint={
                "may_touch": ["docs/", "README.md", "examples/"],
                "must_not_touch": ["source behavior unless separately gated"],
            },
            missing_evidence=[
                "link checker, doctest, example runner, API reference generator, or snapshot gate",
                "human-approved definition of what stale documentation means",
            ],
            next_step="Add or identify a docs verifier before allowing an agent to rewrite docs repeatedly.",
        ))

    candidates.append(_candidate(
        cid="unscoped-improvement-agent",
        title="Reject unscoped 'make the repo better' automation",
        recommended_path="do_not_automate",
        max_agent_autonomy="none",
        gate_strength="none",
        score=_score(2, 0, 0, 30),
        why=[
            "Static repo evidence cannot define a single objective success condition for broad improvement.",
            "Without a gate, scope, and budget, this would become subjective self-grading.",
        ],
        primary_gates=[],
        missing_evidence=[
            "specific recurring task",
            "objective verifier",
            "bounded scope",
            "budget and stop conditions",
        ],
        next_step="Convert the request into a specific candidate such as CI repair, test backfill, dependency repair, or docs drift.",
    ))

    return sorted(candidates, key=lambda item: (-item["score"]["total"], item["id"]))


def render_ranked_backlog(audit: Dict[str, Any]) -> str:
    lines = [
        "# Ranked Automation Backlog",
        "",
        f"Repository: `{audit['repo']['path']}`",
        "",
        "Static audit output is a conservative triage list. It does not grant unattended autonomy.",
        "",
        "| Rank | Candidate | Path | Max Agent Autonomy | Gate | Score |",
        "|---:|---|---|---|---|---:|",
    ]
    for idx, candidate in enumerate(audit["automation_candidates"], start=1):
        lines.append(
            f"| {idx} | {candidate['title']} | `{candidate['recommended_path']}` | "
            f"`{candidate['max_agent_autonomy']}` | `{candidate['gate_strength']}` | {candidate['score']['total']} |"
        )
    lines.extend(["", "## Details", ""])
    for candidate in audit["automation_candidates"]:
        lines.extend([
            f"### {candidate['title']}",
            "",
            f"- Decision: `{candidate['recommended_path']}`",
            f"- Max agent autonomy: `{candidate['max_agent_autonomy']}`",
            f"- Gate strength: `{candidate['gate_strength']}`",
            f"- Evidence level: `{candidate['evidence_level']}`",
            f"- Surface: {candidate.get('surface_title', 'whole repo')}",
            f"- Primary gates: {', '.join('`' + gate + '`' for gate in candidate['primary_gates']) or 'none'}",
            f"- Next step: {candidate['next_step']}",
        ])
        if candidate["proposed_verifiers"]:
            lines.append("- Proposed verifiers:")
            lines.extend(f"  - {item}" for item in candidate["proposed_verifiers"])
        if candidate["missing_evidence"]:
            lines.append("- Missing evidence:")
            lines.extend(f"  - {item}" for item in candidate["missing_evidence"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_recommendations(audit: Dict[str, Any]) -> str:
    top = [
        c
        for c in audit["automation_candidates"]
        if c["recommended_path"] != "do_not_automate" and not c.get("hypothesis")
    ][:3]
    hypotheses = [c for c in audit["automation_candidates"] if c.get("hypothesis")][:5]
    lines = [
        "# Repo Audit Recommendations",
        "",
        "## Positioning",
        "",
        "Use this audit as discovery. The output is a ranked portfolio of possible automation work, not a loop generator.",
        "",
        "## Best Next Moves",
        "",
    ]
    for candidate in top:
        lines.extend([
            f"### {candidate['title']}",
            "",
            f"Recommended path: `{candidate['recommended_path']}`.",
            f"Max agent autonomy from static evidence: `{candidate['max_agent_autonomy']}`.",
            f"Surface: {candidate.get('surface_title', 'whole repo')}.",
            "",
            candidate["next_step"],
            "",
        ])
    if hypotheses:
        lines.extend([
            "## Automation Leads (intake -- a lead is not a loop until it qualifies)",
            "",
            "These are creative opportunities inferred from repo signals. Treat them as discovery leads, not verified loop designs.",
            "",
        ])
        for candidate in hypotheses:
            lines.extend([
                f"### {candidate['title']}",
                "",
                f"Recommended path: `{candidate['recommended_path']}`.",
                f"Max agent autonomy from static evidence: `{candidate['max_agent_autonomy']}`.",
                f"Evidence level: `{candidate['evidence_level']}`.",
                "",
                candidate["next_step"],
                "",
            ])
            if candidate["proposed_verifiers"]:
                lines.append("Proposed verifiers:")
                lines.extend(f"- {item}" for item in candidate["proposed_verifiers"][:3])
                lines.append("")
            if candidate["discovery_questions"]:
                lines.append("Discovery questions:")
                lines.extend(f"- {item}" for item in candidate["discovery_questions"][:3])
                lines.append("")
    lines.extend([
        "## Guardrails",
        "",
        "- Do not promote static audit findings directly to L3.",
        "- Run selected gates once on a clean checkout before scheduling anything.",
        "- Keep plain schedulers separate from agentic loops.",
        "- Treat weak gates such as syntax checks as canaries, not correctness evidence.",
        "- Require accept-rate, cost, regression, and scope-violation tracking before production runtime loops.",
        "",
        "## Gate Inventory Summary",
        "",
        f"- Strong gates: {audit['summary']['gate_counts']['strong']}",
        f"- Medium gates: {audit['summary']['gate_counts']['medium']}",
        f"- Weak gates: {audit['summary']['gate_counts']['weak']}",
        f"- Automation leads: {audit['summary'].get('hypothesis_count', 0)}",
        "",
        "## Surface Summary",
        "",
    ])
    for kind, count in audit["summary"].get("surface_counts", {}).items():
        lines.append(f"- {kind}: {count}")
    return "\n".join(lines).rstrip() + "\n"


def audit_repo(repo_path: str, out_dir: Optional[str] = None, max_files: int = 50_000) -> Dict[str, Any]:
    """Audit a repository and optionally write reviewable artifacts."""
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise RepoAuditError(f"repo path does not exist: {repo}")
    files = _walk_files(repo, max_files)
    gates = discover_gates(str(repo), files=files, max_files=max_files)
    surfaces = infer_surfaces(str(repo), gates, files)
    candidates = build_candidates(str(repo), gates, files, surfaces=surfaces)
    traits = _repo_traits(repo, files, gates)
    audit = {
        "schema_version": 1,
        "mode": "repo-automation-discovery",
        "repo": {
            "path": str(repo),
            "file_count_indexed": len(files),
        },
        "summary": {
            "languages": traits["languages"],
            "has_ci": traits["has_ci"],
            "has_tests": traits["has_tests"],
            "has_docs": traits["has_docs"],
            "gate_counts": traits["gate_counts"],
            "surface_counts": {
                key: sum(1 for surface in surfaces if surface["kind"] == key)
                for key in sorted({surface["kind"] for surface in surfaces})
            },
            "candidate_counts": {
                key: sum(1 for candidate in candidates if candidate["recommended_path"] == key)
                for key in sorted({candidate["recommended_path"] for candidate in candidates})
            },
            "hypothesis_count": sum(1 for candidate in candidates if candidate.get("hypothesis")),
        },
        "gate_inventory": gates,
        "repo_surfaces": surfaces,
        "automation_candidates": candidates,
    }
    if out_dir:
        write_audit_outputs(audit, out_dir)
    return audit


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_audit_outputs(audit: Dict[str, Any], out_dir: str) -> Dict[str, str]:
    """Write repo audit artifacts and return their paths."""
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "repo_audit": root / "repo-audit.json",
        "gate_inventory": root / "gate-inventory.json",
        "repo_surfaces": root / "repo-surfaces.json",
        "automation_candidates": root / "automation-candidates.json",
        "automation_leads": root / "automation-leads.json",
        "loop_hypotheses": root / "loop-hypotheses.json",
        "ranked_backlog": root / "ranked-backlog.md",
        "recommendations": root / "recommendations.md",
    }
    _json_write(outputs["repo_audit"], audit)
    _json_write(outputs["gate_inventory"], {
        "schema_version": audit["schema_version"],
        "repo": audit["repo"],
        "summary": audit["summary"]["gate_counts"],
        "gates": audit["gate_inventory"],
    })
    _json_write(outputs["repo_surfaces"], {
        "schema_version": audit["schema_version"],
        "repo": audit["repo"],
        "summary": audit["summary"].get("surface_counts", {}),
        "surfaces": audit["repo_surfaces"],
    })
    _json_write(outputs["automation_candidates"], {
        "schema_version": audit["schema_version"],
        "repo": audit["repo"],
        "candidates": audit["automation_candidates"],
    })
    leads = [candidate for candidate in audit["automation_candidates"] if candidate.get("hypothesis")]
    _json_write(outputs["automation_leads"], {
        "schema_version": audit["schema_version"],
        "repo": audit["repo"],
        "note": "Automation leads are intake -- a lead becomes a loop only by passing core qualification.",
        "leads": leads,
    })
    _json_write(outputs["loop_hypotheses"], {  # back-compat alias for one release
        "schema_version": audit["schema_version"],
        "repo": audit["repo"],
        "hypotheses": leads,
    })
    outputs["ranked_backlog"].write_text(render_ranked_backlog(audit), encoding="utf-8")
    outputs["recommendations"].write_text(render_recommendations(audit), encoding="utf-8")
    return {key: str(path) for key, path in outputs.items()}


def _load_audit(path: str) -> Dict[str, Any]:
    audit_path = Path(path).resolve()
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepoAuditError(f"could not read audit file {audit_path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "repo-automation-discovery":
        raise RepoAuditError(f"{audit_path} is not a repo-audit.json file")
    return payload


def _candidate_by_id(audit: Dict[str, Any], candidate_id: str) -> Dict[str, Any]:
    for candidate in audit.get("automation_candidates", []):
        if candidate.get("id") == candidate_id:
            return candidate
    raise RepoAuditError(f"candidate not found in audit: {candidate_id}")


def _gates_by_id(audit: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        gate["id"]: gate
        for gate in audit.get("gate_inventory", [])
        if isinstance(gate, dict) and gate.get("id")
    }


def _candidate_gate_commands(audit: Dict[str, Any], candidate: Dict[str, Any]) -> List[str]:
    gates = _gates_by_id(audit)
    commands = [
        gates[gate_id]["command"]
        for gate_id in candidate.get("primary_gates", [])
        if gate_id in gates and gates[gate_id].get("command")
    ]
    return sorted(dict.fromkeys(commands))


def _promotion_slug(text: str) -> str:
    bits = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(bits[:10])[:80].strip("-") or "repo-promotion"


def _repo_name_from_audit(audit: Dict[str, Any]) -> str:
    repo_path = audit.get("repo", {}).get("path") or "target-repo"
    return Path(str(repo_path)).name or "target-repo"


def _repo_slug(repo: str) -> str:
    value = (repo or "").rstrip("/\\")
    if not value:
        return "target-repo"
    name = re.split(r"[/\\]", value)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return _promotion_slug(name or value)


def default_promotion_out_dir(
    audit_path: str,
    candidate_id: str,
    out_root: str = "case-studies",
    repo: str = "",
) -> str:
    """Return the conventional case-study folder for an audit candidate."""
    audit = _load_audit(audit_path)
    candidate = _candidate_by_id(audit, candidate_id)
    repo_name = _repo_slug(repo or _repo_name_from_audit(audit))
    candidate_name = _promotion_slug(candidate.get("id") or candidate.get("title") or "candidate")
    return str(Path(out_root) / repo_name / candidate_name)


def _proof_status(candidate: Dict[str, Any], gate_commands: Sequence[str]) -> str:
    if candidate.get("recommended_path") == "do_not_automate":
        return "rejected"
    if candidate.get("hypothesis") or candidate.get("evidence_level") == "hypothesis":
        return "hypothesis_discovery"
    if candidate.get("recommended_path") == "discovery_required":
        return "discovery_required"
    if candidate.get("recommended_path") == "plain_scheduler":
        return "scheduler_packet"
    if candidate.get("recommended_path") == "human_in_loop":
        return "human_review_required"
    if not gate_commands:
        return "missing_gate"
    return "case_study_ready"


def _answers_for_candidate(
    candidate: Dict[str, Any],
    gate_commands: Sequence[str],
    max_runtime_seconds: int,
) -> Dict[str, Any]:
    scope = candidate.get("scope_hint") or {}
    may_touch = list(scope.get("may_touch") or [])
    must_not_touch = list(scope.get("must_not_touch") or [])
    gate_text = " && ".join(gate_commands) if gate_commands else "unknown"
    base = {
        "task": candidate.get("title") or "Promoted repo automation candidate",
        "recurs": True,
        "wrong_result_signal": f"one of the selected verifier commands exits nonzero: {gate_text}",
        "gate_check": f"all selected verifier commands exit 0: {gate_text}",
        "finished_state": f"{candidate.get('title', 'the candidate')} is resolved and selected gates pass",
        "evidence": f"selected verifier commands exit 0: {gate_text}",
        "may_touch": may_touch,
        "must_not_touch": must_not_touch,
        "budget": {"max_runtime_seconds": max_runtime_seconds},
        "budget_summary": f"at most {max_runtime_seconds} seconds per promoted case-study run",
        "unattended": False,
        "output_reversibility": "reversible",
        "gate_rung": "tool" if gate_commands else "independent_model",
        "end_to_end": candidate.get("gate_strength") == "strong",
        "agent_can_do_end_to_end": True,
        "billing": "unknown",
        "proven_manual_pass": False,
        "proven_cheap": False,
        "trigger_type": "manual",
        "cadence": "manual proof run",
    }
    path = candidate.get("recommended_path")
    if candidate.get("hypothesis") or candidate.get("evidence_level") == "hypothesis":
        base.update({
            "recurs": "unknown",
            "wrong_result_signal": "unknown",
            "gate_check": "unknown",
            "finished_state": candidate.get("next_step") or "discovery facts exist",
        })
    elif path == "discovery_required":
        base.update({
            "wrong_result_signal": "unknown",
            "gate_check": "unknown",
            "finished_state": candidate.get("next_step") or "discovery facts exist",
        })
    elif path == "plain_scheduler":
        base["deterministic_without_llm"] = True
    elif path == "human_in_loop":
        base["agent_can_do_end_to_end"] = False
    return base


def _render_markdown_list(items: Sequence[str]) -> List[str]:
    return [f"- {item}" for item in items] if items else ["- none"]


def _render_verifier_plan(candidate: Dict[str, Any], gate_commands: Sequence[str]) -> str:
    lines = [
        "# Verifier Plan",
        "",
        f"Candidate: `{candidate['id']}`",
        f"Evidence level: `{candidate.get('evidence_level', 'static_evidence')}`",
        f"Recommended path: `{candidate.get('recommended_path')}`",
        "",
        "## Confirmed Commands",
        "",
    ]
    lines.extend(_render_markdown_list([f"`{command}`" for command in gate_commands]))
    if candidate.get("proposed_verifiers"):
        lines.extend(["", "## Proposed Verifiers", ""])
        lines.extend(_render_markdown_list(candidate["proposed_verifiers"]))
    if candidate.get("missing_evidence"):
        lines.extend(["", "## Missing Evidence", ""])
        lines.extend(_render_markdown_list(candidate["missing_evidence"]))
    lines.extend([
        "",
        "## Promotion Rule",
        "",
        "Do not claim upstream verification until the selected verifier commands pass on a clean checkout or disposable runner.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _render_scope_doc(candidate: Dict[str, Any]) -> str:
    scope = candidate.get("scope_hint") or {}
    lines = [
        "# Scope Fence",
        "",
        "## May Touch",
        "",
    ]
    lines.extend(_render_markdown_list([f"`{item}`" for item in scope.get("may_touch", [])]))
    lines.extend(["", "## Must Not Touch", ""])
    lines.extend(_render_markdown_list([f"`{item}`" for item in scope.get("must_not_touch", [])]))
    lines.extend([
        "",
        "## Rule",
        "",
        "Any promoted run must fail its scope check if changed files fall outside `may_touch` or inside `must_not_touch`.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _render_runner_plan_note(manifest: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    setup = "deps" if candidate.get("recommended_path") in {"l2_candidate", "human_in_loop"} else "none"
    lines = [
        "# Runner Plan Note",
        "",
        "Use a disposable runner before installing target-repo dependencies or running untrusted setup scripts.",
        "",
        "```bash",
        "super-looper runner plan \\",
        "  --profile .super-looper/runners/<runner>.profile.json \\",
        "  --case <this-promotion-directory> \\",
        f"  --repo {manifest['repo']} \\",
        f"  --setup {setup} \\",
        "  --isolation container \\",
        "  --allow-network-setup \\",
        "  --out remote-plan.json",
        "```",
        "",
        "Keep verifier network disabled unless the candidate explicitly requires live integration checks.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _render_maintainer_brief(
    audit: Dict[str, Any],
    candidate: Dict[str, Any],
    gate_commands: Sequence[str],
    proof_status: str,
    repo: str = "",
) -> str:
    repo_label = repo or audit.get("repo", {}).get("path", "unknown")
    lines = [
        "# Maintainer Brief",
        "",
        f"Repository: `{repo_label}`",
        f"Candidate: `{candidate['id']}`",
        f"Title: {candidate['title']}",
        f"Proof status: `{proof_status}`",
        f"Recommended path: `{candidate.get('recommended_path')}`",
        f"Max agent autonomy from audit: `{candidate.get('max_agent_autonomy')}`",
        f"Evidence level: `{candidate.get('evidence_level', 'static_evidence')}`",
        "",
        "## Why This Candidate",
        "",
    ]
    lines.extend(_render_markdown_list(candidate.get("why", [])))
    lines.extend(["", "## Gates", ""])
    lines.extend(_render_markdown_list([f"`{command}`" for command in gate_commands]))
    lines.extend(["", "## Next Step", "", candidate.get("next_step") or "Run a watched proof pass."])
    if candidate.get("hypothesis"):
        lines.extend([
            "",
            "## Hypothesis Warning",
            "",
            "This is a creative discovery lead, not a confirmed automation candidate. Build and run the proposed verifier before claiming value.",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _promotion_summary(
    *,
    audit_path: Path,
    out_dir: Path,
    candidate: Dict[str, Any],
    gate_commands: Sequence[str],
    proof_status: str,
    manifest: Dict[str, Any],
    design_report: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "repo-candidate-promotion",
        "source_audit": str(audit_path),
        "candidate_id": candidate["id"],
        "candidate_title": candidate["title"],
        "proof_status": proof_status,
        "recommended_path": candidate.get("recommended_path"),
        "evidence_level": candidate.get("evidence_level", "static_evidence"),
        "hypothesis": bool(candidate.get("hypothesis")),
        "verifier_commands": list(gate_commands),
        "manifest": "case-study.json",
        "design_verdict": design_report.get("report", {}).get("verdict"),
        "taxonomy": {
            "root": ["case-study.json"],
            "inputs": ["audit-summary.json", "candidate.json", "answers.json", "promotion.json"],
            "design": ["design-report.json", "loop.json when answers compile"],
            "proof": ["verifier-plan.md", "scope.md", "runner-plan.md", "runs/"],
            "reports": ["maintainer-brief.md", "promotion-summary.md"],
        },
        "out_dir": str(out_dir),
        "case_study": manifest,
    }


def _render_promotion_summary(payload: Dict[str, Any]) -> str:
    lines = [
        "# Promotion Summary",
        "",
        f"Candidate: `{payload['candidate_id']}`",
        f"Proof status: `{payload['proof_status']}`",
        f"Recommended path: `{payload['recommended_path']}`",
        f"Evidence level: `{payload['evidence_level']}`",
        f"Design verdict: `{payload.get('design_verdict') or 'not_available'}`",
        "",
        "## Taxonomy",
        "",
    ]
    for folder, files in payload["taxonomy"].items():
        lines.append(f"- `{folder}/`: {', '.join(files)}")
    lines.extend(["", "## Verifiers", ""])
    lines.extend(_render_markdown_list([f"`{command}`" for command in payload.get("verifier_commands", [])]))
    return "\n".join(lines).rstrip() + "\n"


def promote_candidate(
    audit_path: str,
    candidate_id: str,
    out_dir: Optional[str] = None,
    repo: Optional[str] = None,
    issue: Optional[str] = None,
    name: Optional[str] = None,
    max_runtime_seconds: int = 1800,
    out_root: str = "case-studies",
) -> Dict[str, Any]:
    """Promote an audit candidate into a clean case-study proof packet."""
    source = Path(audit_path).resolve()
    audit = _load_audit(str(source))
    candidate = _candidate_by_id(audit, candidate_id)
    if candidate.get("recommended_path") == "do_not_automate":
        raise RepoAuditError("refusing to promote a do_not_automate candidate")
    gates = _candidate_gate_commands(audit, candidate)
    target_out = out_dir or default_promotion_out_dir(
        str(source),
        candidate_id,
        out_root=out_root,
        repo=repo or "",
    )
    root = Path(target_out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for subdir in ("inputs", "design", "proof", "proof/runs", "reports"):
        (root / subdir).mkdir(parents=True, exist_ok=True)

    repo_value = repo or audit.get("repo", {}).get("path") or ""
    study_name = name or (
        f"{_repo_slug(repo_value or _repo_name_from_audit(audit))}-"
        f"{_promotion_slug(candidate['id'])}"
    )
    manifest = {
        "name": study_name,
        "repo": repo_value,
        "issue": issue or "",
        "answers": "inputs/answers.json",
        "loop_spec": "design/loop.json",
        "design_report": "design/design-report.json",
        "verifier": gates,
        "may_touch": list((candidate.get("scope_hint") or {}).get("may_touch") or []),
        "must_not_touch": list((candidate.get("scope_hint") or {}).get("must_not_touch") or []),
        "budget": {"max_runtime_seconds": max_runtime_seconds},
        "runs_dir": "proof/runs",
        "promotion": "inputs/promotion.json",
    }

    answers = _answers_for_candidate(candidate, gates, max_runtime_seconds)
    spec, report = build_spec(answers)
    design_report = {
        "manifest": "case-study.json",
        "answers": "inputs/answers.json",
        "candidate": "inputs/candidate.json",
        "report": report,
    }
    if spec is not None:
        design_report["loop_spec"] = "design/loop.json"
        design_report["max_autonomy"] = max_autonomy(spec)[0]
        _json_write(root / "design" / "loop.json", spec)
    else:
        loop_path = root / "design" / "loop.json"
        if loop_path.exists():
            loop_path.unlink()

    proof_status = _proof_status(candidate, gates)
    promotion = _promotion_summary(
        audit_path=source,
        out_dir=root,
        candidate=candidate,
        gate_commands=gates,
        proof_status=proof_status,
        manifest=manifest,
        design_report=design_report,
    )

    audit_summary = {
        "schema_version": audit.get("schema_version"),
        "repo": audit.get("repo"),
        "summary": audit.get("summary"),
    }
    _json_write(root / "case-study.json", manifest)
    _json_write(root / "inputs" / "audit-summary.json", audit_summary)
    _json_write(root / "inputs" / "candidate.json", candidate)
    _json_write(root / "inputs" / "answers.json", answers)
    _json_write(root / "inputs" / "promotion.json", promotion)
    _json_write(root / "design" / "design-report.json", design_report)
    (root / "proof" / "verifier-plan.md").write_text(_render_verifier_plan(candidate, gates), encoding="utf-8")
    (root / "proof" / "scope.md").write_text(_render_scope_doc(candidate), encoding="utf-8")
    (root / "proof" / "runner-plan.md").write_text(_render_runner_plan_note(manifest, candidate), encoding="utf-8")
    (root / "reports" / "maintainer-brief.md").write_text(
        _render_maintainer_brief(audit, candidate, gates, proof_status, repo=repo_value),
        encoding="utf-8",
    )
    (root / "reports" / "promotion-summary.md").write_text(_render_promotion_summary(promotion), encoding="utf-8")

    outputs = {
        "case_study": str(root / "case-study.json"),
        "promotion": str(root / "inputs" / "promotion.json"),
        "answers": str(root / "inputs" / "answers.json"),
        "candidate": str(root / "inputs" / "candidate.json"),
        "design_report": str(root / "design" / "design-report.json"),
        "verifier_plan": str(root / "proof" / "verifier-plan.md"),
        "scope": str(root / "proof" / "scope.md"),
        "runner_plan": str(root / "proof" / "runner-plan.md"),
        "maintainer_brief": str(root / "reports" / "maintainer-brief.md"),
        "promotion_summary": str(root / "reports" / "promotion-summary.md"),
    }
    if spec is not None:
        outputs["loop_spec"] = str(root / "design" / "loop.json")
    return {
        "out_dir": str(root),
        "proof_status": proof_status,
        "candidate": {
            "id": candidate["id"],
            "title": candidate["title"],
            "recommended_path": candidate.get("recommended_path"),
            "evidence_level": candidate.get("evidence_level", "static_evidence"),
            "hypothesis": bool(candidate.get("hypothesis")),
        },
        "design_verdict": report.get("verdict"),
        "outputs": outputs,
    }
