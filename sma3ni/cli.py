"""Admin CLI.

  docker compose run --rm api python -m sma3ni.cli create-key --name whatsapp-gw --scopes intake
  docker compose run --rm api python -m sma3ni.cli create-key --name agent-casa --scopes agent --service etat_civil
  docker compose run --rm api python -m sma3ni.cli list-keys
  docker compose run --rm api python -m sma3ni.cli revoke-key <key-id>
"""
from __future__ import annotations

import argparse
import sys

import psycopg

from .api.auth import generate_key, hash_key
from .config import get_settings

SCOPES = {"intake", "agent", "admin"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sma3ni")
    sub = parser.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create-key")
    create.add_argument("--name", required=True)
    create.add_argument("--scopes", required=True, help="comma separated: intake,agent,admin")
    create.add_argument("--service", help="restrict an agent key to one service code")
    sub.add_parser("list-keys")
    revoke = sub.add_parser("revoke-key")
    revoke.add_argument("key_id")
    args = parser.parse_args(argv)

    with psycopg.connect(get_settings().database_url) as conn:
        if args.cmd == "create-key":
            scopes = sorted({s.strip() for s in args.scopes.split(",") if s.strip()})
            if not scopes or not set(scopes) <= SCOPES:
                parser.error(f"scopes must be among {sorted(SCOPES)}")
            raw = generate_key()
            key_id = conn.execute(
                "INSERT INTO api_keys (name, key_hash, scopes, service_code) VALUES (%s, %s, %s, %s) RETURNING id",
                (args.name, hash_key(raw), scopes, args.service),
            ).fetchone()[0]
            print(f"id:  {key_id}\nkey: {raw}\n(store it now, it is not recoverable)")
        elif args.cmd == "list-keys":
            for row in conn.execute("SELECT id, name, scopes, service_code, last_used_at, revoked_at "
                                    "FROM api_keys ORDER BY created_at"):
                print(*row, sep=" | ")
        elif args.cmd == "revoke-key":
            n = conn.execute("UPDATE api_keys SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
                             (args.key_id,)).rowcount
            print("revoked" if n else "not found or already revoked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
