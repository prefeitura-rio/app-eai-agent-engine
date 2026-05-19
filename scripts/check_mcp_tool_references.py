#!/usr/bin/env python3
"""Warn-only check: tools MCP referenciadas nos prompt_modules existem no registry?

Lê `media-types.yaml` do repo MCP (`app-mcp-server`) e compara com tool names
mencionadas em `src/prompt_modules/*.py`. Emite WARNINGS pra stderr mas SEMPRE
retorna exit code 0 — não bloqueia commit. Objetivo: visibilidade de drift
cross-repo, não gate rígido.

Fontes do registry (em ordem de preferência):
  1. Env var MCP_REGISTRY_PATH apontando pra checkout local de app-mcp-server
  2. GitHub raw URL (staging branch)

Se nenhuma fonte funcionar, imprime nota e exit 0 (sem fail, sem ruído).

Uso (manual):
    python scripts/check_mcp_tool_references.py

Uso (pre-commit, automaticamente via .pre-commit-config.yaml):
    Roda em qualquer commit que toca src/prompt_modules/*.py
"""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_MODULES_DIR = REPO_ROOT / "src" / "prompt_modules"
# URL ficará válida quando https://github.com/prefeitura-rio/app-mcp-server/pull/74
# (Fase 1 da generalização de mídia) entrar em staging. Pré-merge retorna 404
# e o script degrada silencioso (warn-only). Override via env pra debug pré-merge:
#   MCP_REGISTRY_URL=https://raw.githubusercontent.com/.../feat/media-types-registry/media-types.yaml
REGISTRY_RAW_URL = os.environ.get(
    "MCP_REGISTRY_URL",
    "https://raw.githubusercontent.com/prefeitura-rio/app-mcp-server/staging/media-types.yaml",
)

# Tool patterns conhecidos. Lista curada — adicionar quando surgir tool nova
# que apareça em prompt module. Falsos positivos são silenciosos (não trava).
KNOWN_TOOL_PATTERNS = [
    re.compile(r"\b(send_whatsapp_media)\b"),
    re.compile(r"\b(generate_audio_response)\b"),
    re.compile(r"\b(register_inbound_media)\b"),
    re.compile(r"\b(analyze_inbound_audio)\b"),
    re.compile(r"\b(analyze_inbound_image)\b"),
    re.compile(r"\b(analyze_inbound_video)\b"),
]


def _load_registry_yaml() -> dict | None:
    local_path = os.environ.get("MCP_REGISTRY_PATH")
    if local_path:
        p = Path(local_path)
        # Accept either file path OR checkout directory (resolve to <dir>/media-types.yaml).
        if p.is_dir():
            p = p / "media-types.yaml"
        if p.is_file():
            try:
                # encoding explicito: registry tem UTF-8 (acentos, emojis em comments).
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                print(
                    f"[check-mcp-tools] Falha lendo {p}: {e}. Skip (warn-only).",
                    file=sys.stderr,
                )
                return None
            return _parse_yaml(text)
        print(
            f"[check-mcp-tools] MCP_REGISTRY_PATH={local_path} não é file nem dir-com-media-types.yaml; "
            f"tentando GitHub raw",
            file=sys.stderr,
        )
    try:
        with urllib.request.urlopen(REGISTRY_RAW_URL, timeout=5) as resp:
            return _parse_yaml(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as e:
        print(
            f"[check-mcp-tools] Não consegui fetch registry de {REGISTRY_RAW_URL}: {e}. "
            f"Skip (warn-only).",
            file=sys.stderr,
        )
        return None


def _parse_yaml(text: str) -> dict | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        print(
            "[check-mcp-tools] PyYAML não instalado; skip. "
            "(uv add pyyaml pra ativar.)",
            file=sys.stderr,
        )
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        # Registry mid-edit / malformado / 404 HTML body. Warn-only contract:
        # nunca bloqueia commit por isso.
        print(
            f"[check-mcp-tools] YAML inválido no registry: {e}. Skip (warn-only).",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(
            f"[check-mcp-tools] Registry não é mapping (got {type(data).__name__}). "
            f"Skip (warn-only).",
            file=sys.stderr,
        )
        return None
    return data


def _registered_tools(registry: dict) -> set[str] | None:
    """Retorna set de tools registradas. None se shape inválido (warn-only)."""
    tools: set[str] = set()
    types = registry.get("types")
    if not isinstance(types, dict):
        print(
            f"[check-mcp-tools] Registry shape inválido (types={type(types).__name__}). "
            f"Skip (warn-only).",
            file=sys.stderr,
        )
        return None
    for type_name, spec in types.items():
        if not isinstance(spec, dict):
            print(
                f"[check-mcp-tools] Registry entry types.{type_name} não é mapping "
                f"({type(spec).__name__}); pulando este entry.",
                file=sys.stderr,
            )
            continue
        for direction in ("inbound", "outbound"):
            sub = spec.get(direction)
            if not isinstance(sub, dict):
                continue
            for field in ("analyzer_tool", "builder_tool"):
                t = sub.get(field)
                if isinstance(t, str) and t:
                    tools.add(t)
    return tools


def _referenced_tools() -> dict[str, list[str]]:
    """Map tool_name → list of files referencing it."""
    refs: dict[str, list[str]] = {}
    if not PROMPT_MODULES_DIR.exists():
        return refs
    for py in PROMPT_MODULES_DIR.glob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            # Warn-only contract: nunca bloqueia commit por leitura falha. Os
            # prompt modules são UTF-8 (acentos PT-BR); locales não-UTF-8
            # default (Windows cp1252) sem encoding="utf-8" explicito quebrariam.
            print(f"[check-mcp-tools] Falha lendo {py}: {e}", file=sys.stderr)
            continue
        for pat in KNOWN_TOOL_PATTERNS:
            for m in pat.finditer(text):
                tool = m.group(1)
                refs.setdefault(tool, []).append(py.name)
    for tool in refs:
        refs[tool] = sorted(set(refs[tool]))
    return refs


def main() -> int:
    registry = _load_registry_yaml()
    if registry is None:
        return 0  # warn-only — no registry, no check

    registered = _registered_tools(registry)
    if registered is None:
        return 0  # warn-only — shape invalido
    referenced = _referenced_tools()

    orphans = {tool: files for tool, files in referenced.items() if tool not in registered}

    if orphans:
        print("[check-mcp-tools] ⚠ Tools referenciadas em prompt_modules sem entry no MCP registry:", file=sys.stderr)
        for tool, files in sorted(orphans.items()):
            print(f"  - {tool} (em: {', '.join(files)})", file=sys.stderr)
        print(
            "[check-mcp-tools] Registry consultado: " + REGISTRY_RAW_URL,
            file=sys.stderr,
        )
        print(
            "[check-mcp-tools] WARN-ONLY: commit não bloqueado. "
            "Considere adicionar entry em media-types.yaml ou remover referência.",
            file=sys.stderr,
        )
    else:
        # Silencioso no caso happy path — pre-commit hooks barulhentos viram ruído.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
