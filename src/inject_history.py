#!/usr/bin/env python3
"""
inject_history.py - Injeta mensagens no histórico do agente.

Suporta dois modos de execução:
  gateway — chama o gateway via HTTP (padrão; usa EAI_GATEWAY_API_URL / EAI_GATEWAY_API_TOKEN)
  local   — usa o Agent diretamente via async_query (requer cloud-sql-proxy)

O modo é selecionado via --mode (padrão: gateway).

--- MODO GATEWAY (staging/prod) ---
As variáveis EAI_GATEWAY_API_URL e EAI_GATEWAY_API_TOKEN devem estar no .env ou no ambiente.
O mesmo .env do engine é carregado automaticamente (src/config/.env).

Uso:
    uv run src/inject_history.py \\
        --user-number "5521999999999" \\
        --message "Seu protocolo 123456 está em análise."

--- MODO LOCAL ---
Requer cloud-sql-proxy rodando em outro terminal:
    GOOGLE_APPLICATION_CREDENTIALS=<creds> cloud-sql-proxy "rj-superapp-staging:us-central1:postgres"

Uso:
    uv run src/inject_history.py --mode local \\
        --user-number "5521999999999" \\
        --message "Seu protocolo 123456 está em análise."

--- CSV BATCH ---
Formato do CSV: colunas thread_id, message, role (role é opcional, default "ai").
Linhas com o mesmo thread_id são agrupadas como múltiplas mensagens na mesma chamada.

    uv run src/inject_history.py --csv disparos.csv
    uv run src/inject_history.py --mode local --csv disparos.csv

Exemplo de CSV:
    thread_id,message,role
    5521999999999,Seu protocolo está em análise.,ai
    5521888888888,Identificamos uma pendência no seu cadastro.,ai
"""

import argparse
import asyncio
import csv
import json
import os
import sys

import requests

VALID_ROLES = {"ai", "human"}
DEFAULT_ROLE = "ai"
DEFAULT_TIMEOUT = 60


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Injeta mensagens no histórico do agente (gateway ou local).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Fonte de mensagens: individual ou CSV
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--user-number",
        metavar="NUMBER",
        help="Número do usuário (thread_id). Use com --message.",
    )
    source.add_argument(
        "--csv",
        metavar="FILE",
        help="CSV com colunas thread_id, message[, role]. Processa em batch.",
    )

    parser.add_argument(
        "--message",
        dest="messages",
        action="append",
        metavar="TEXT",
        help="Texto da mensagem (repita para múltiplas). Requer --user-number.",
    )
    parser.add_argument(
        "--role",
        dest="roles",
        action="append",
        metavar="ROLE",
        choices=list(VALID_ROLES),
        help=f"Role correspondente ao --message: {', '.join(sorted(VALID_ROLES))}. "
             f"Default: '{DEFAULT_ROLE}'.",
    )
    parser.add_argument(
        "--mode",
        choices=["local", "gateway"],
        default="gateway",
        help="Modo de execução: 'gateway' (default) ou 'local' (Agent direto, requer proxy).",
    )
    parser.add_argument(
        "--reasoning-engine-id",
        metavar="ID",
        default=None,
        help="ID do Reasoning Engine (modo gateway; opcional, usa o default do gateway).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"Timeout das requisições em segundos (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime o payload sem enviar.",
    )

    args = parser.parse_args()

    if args.user_number and not args.messages:
        parser.error("--user-number requer pelo menos um --message.")
    if args.csv and args.messages:
        parser.error("--csv e --message são mutuamente exclusivos.")

    return args


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_messages(messages: list[str], roles: list[str] | None) -> list[dict]:
    if roles is None:
        roles = [DEFAULT_ROLE] * len(messages)
    if len(roles) != len(messages):
        print(
            f"Erro: número de --role ({len(roles)}) != número de --message ({len(messages)}).",
            file=sys.stderr,
        )
        sys.exit(2)
    return [{"role": role, "content": msg} for msg, role in zip(messages, roles)]


def load_csv(path: str) -> list[dict]:
    """Lê o CSV e retorna lista de {thread_id, messages: [{role, content}]}."""
    rows: dict[str, list[dict]] = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"thread_id", "message"}
            if not required.issubset(set(reader.fieldnames or [])):
                print(
                    f"Erro: CSV deve ter colunas {required}. Encontradas: {reader.fieldnames}",
                    file=sys.stderr,
                )
                sys.exit(2)
            for lineno, row in enumerate(reader, start=2):
                thread_id = row["thread_id"].strip()
                message = row["message"].strip()
                role = row.get("role", DEFAULT_ROLE).strip() or DEFAULT_ROLE
                if role not in VALID_ROLES:
                    print(
                        f"Erro: linha {lineno}: role inválido '{role}'. Use: {VALID_ROLES}",
                        file=sys.stderr,
                    )
                    sys.exit(2)
                rows.setdefault(thread_id, []).append({"role": role, "content": message})
    except FileNotFoundError:
        print(f"Erro: arquivo '{path}' não encontrado.", file=sys.stderr)
        sys.exit(2)
    return [{"thread_id": tid, "messages": msgs} for tid, msgs in rows.items()]


def print_job(thread_id: str, messages: list[dict]) -> None:
    print(f"\nthread_id : {thread_id}")
    print(f"Mensagens : {len(messages)}")
    for i, m in enumerate(messages, 1):
        preview = m["content"][:80] + ("..." if len(m["content"]) > 80 else "")
        print(f"  [{i}] role={m['role']}  \"{preview}\"")


# ---------------------------------------------------------------------------
# Modo gateway
# ---------------------------------------------------------------------------

def send_via_gateway(
    thread_id: str,
    messages: list[dict],
    gateway_url: str,
    gateway_token: str,
    reasoning_engine_id: str | None,
    timeout: int,
    dry_run: bool,
) -> bool:
    endpoint = f"{gateway_url.rstrip('/')}/api/v1/message/webhook/update_history"
    payload: dict = {"user_number": thread_id, "messages": messages}
    if reasoning_engine_id:
        payload["reasoning_engine_id"] = reasoning_engine_id

    if dry_run:
        print(f"\n--- Payload (dry-run) para {thread_id} ---")
        print(json.dumps({"endpoint": endpoint, "body": payload}, ensure_ascii=False, indent=2))
        return True

    print(f"\nEnviando... (timeout={timeout}s)")
    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {gateway_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        print(f"Erro de rede: {e}", file=sys.stderr)
        return False

    print(f"Status HTTP: {resp.status_code}")
    try:
        body = resp.json()
        print("Resposta:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
    except ValueError:
        print(f"Resposta (texto): {resp.text}")
        body = {}

    output = body.get("output", body)
    inner_status = output.get("status_code", resp.status_code)
    if resp.status_code == 200 and inner_status == 200:
        print(f"OK: histórico de {thread_id} atualizado com sucesso.")
        return True

    print(f"Falha: status_code={inner_status}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Modo local
# ---------------------------------------------------------------------------

async def send_local(
    thread_id: str,
    messages: list[dict],
    dry_run: bool,
) -> bool:
    import vertexai
    from src.config import env
    from src.prompt import prompt_data
    from src.tools import mcp_tools
    from engine.agent import Agent

    payload = {"messages": messages}
    config = {"configurable": {"thread_id": thread_id}}

    if dry_run:
        print(f"\n--- Payload (dry-run) para {thread_id} ---")
        print(json.dumps({"input": payload, "config": config, "type": "history"}, ensure_ascii=False, indent=2))
        return True

    vertexai.init(
        project=env.PROJECT_ID,
        location=env.LOCATION,
        staging_bucket=env.GCS_BUCKET,
    )

    prompt_version = prompt_data["version"]
    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt=prompt_data["prompt"],
        temperature=0.7,
        tools=mcp_tools,
        include_thoughts=True,
        thinking_budget=-1,
        otpl_service=f"eai-langgraph-v{prompt_version}",
    )

    print("\nChamando agent.async_query(type='history')...")
    try:
        result = await agent.async_query(input=payload, config=config, type="history")
    except Exception as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return False
    finally:
        if hasattr(agent, "cleanup"):
            await agent.cleanup()

    print("Resposta do agente:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("status_code") == 200:
        print(f"OK: histórico de {thread_id} atualizado com sucesso.")
        return True

    print(f"Falha: status_code={result.get('status_code')}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def get_gateway_credentials() -> tuple[str, str]:
    from src.config import env  # carrega src/config/.env automaticamente
    url = env.EAI_GATEWAY_API_URL
    token = env.EAI_GATEWAY_API_TOKEN
    if not url:
        print(
            "Erro: EAI_GATEWAY_API_URL não configurada. Defina em src/config/.env ou no ambiente.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not token:
        print(
            "Erro: EAI_GATEWAY_API_TOKEN não configurada. Defina em src/config/.env ou no ambiente.",
            file=sys.stderr,
        )
        sys.exit(2)
    return url, token


async def run(args: argparse.Namespace) -> int:
    if args.csv:
        jobs = load_csv(args.csv)
        print(f"CSV carregado: {len(jobs)} thread(s) únicas.")
    else:
        jobs = [{"thread_id": args.user_number, "messages": build_messages(args.messages, args.roles)}]

    failures = 0

    if args.mode == "gateway":
        url, token = get_gateway_credentials()
        for job in jobs:
            print_job(job["thread_id"], job["messages"])
            ok = send_via_gateway(
                thread_id=job["thread_id"],
                messages=job["messages"],
                gateway_url=url,
                gateway_token=token,
                reasoning_engine_id=args.reasoning_engine_id,
                timeout=args.timeout,
                dry_run=args.dry_run,
            )
            if not ok:
                failures += 1
    else:
        for job in jobs:
            print_job(job["thread_id"], job["messages"])
            ok = await send_local(
                thread_id=job["thread_id"],
                messages=job["messages"],
                dry_run=args.dry_run,
            )
            if not ok:
                failures += 1

    if failures:
        print(f"\n{failures}/{len(jobs)} job(s) falharam.", file=sys.stderr)
        return 1

    print(f"\nConcluído: {len(jobs) - failures}/{len(jobs)} job(s) com sucesso.")
    return 0


def main():
    args = parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
