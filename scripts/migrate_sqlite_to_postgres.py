from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TABLES: list[tuple[str, list[str]]] = [
    ("colaboradores", ["id", "nome", "funcao", "observacao", "foto", "ativo"]),
    ("caminhoes", ["id", "placa", "modelo", "observacao", "ativo"]),
    ("rotas_semanais", ["id", "dia_semana", "rota", "destino", "observacao"]),
    ("ferias", ["id", "colaborador_id", "data_inicio", "data_fim", "observacao"]),
    ("folgas", ["id", "data", "data_fim", "data_saida", "colaborador_id", "observacao_padrao", "observacao_extra", "observacao_cor"]),
    ("carregamentos", ["id", "data", "data_saida", "rota", "placa", "motorista_id", "ajudante_id", "observacao", "observacao_extra", "observacao_cor", "revisado"]),
    ("oficinas", ["id", "data", "motorista_id", "placa", "observacao", "observacao_extra", "data_saida", "observacao_cor"]),
    ("escala_cd", ["id", "data", "motorista_id", "ajudante_id", "observacao"]),
    ("bloqueios", ["id", "colaborador_id", "data_inicio", "data_fim", "motivo", "carregamento_id"]),
    ("ajustes_rotas", ["id", "carregamento_id", "data_ajuste", "duracao_anterior", "duracao_nova", "observacao_ajuste"]),
    ("rotas_suprimidas", ["id", "data", "rota"]),
]

DEFAULT_VALUES: dict[str, object] = {
    "ativo": 1,
    "revisado": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra dados do SQLite para PostgreSQL (Neon)")
    parser.add_argument("--source", default="jr_escala.db", help="Arquivo SQLite de origem")
    parser.add_argument(
        "--target",
        default=os.environ.get("JR_ESCALA_DATABASE_URL") or os.environ.get("DATABASE_URL") or "",
        help="URL de conexão PostgreSQL",
    )
    return parser.parse_args()


def table_exists_sqlite(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,))
    return cur.fetchone() is not None


def source_columns_sqlite(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def migrate_table(sqlite_cur: sqlite3.Cursor, pg_cur, table: str, columns: list[str]) -> int:
    if not table_exists_sqlite(sqlite_cur, table):
        return 0

    src_cols = source_columns_sqlite(sqlite_cur, table)
    load_cols = [c for c in columns if c in src_cols]
    if not load_cols:
        return 0

    order_by = " ORDER BY id" if "id" in src_cols else ""
    sqlite_cur.execute(f"SELECT {', '.join(load_cols)} FROM {table}{order_by}")
    rows = sqlite_cur.fetchall()
    if not rows:
        return 0

    placeholders = ", ".join(["%s"] * len(columns))
    insert_cols = ", ".join(columns)
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in columns if c != "id"])
    upsert_sql = (
        f"INSERT INTO {table} ({insert_cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates};"
    )

    prepared_rows = []
    for row in rows:
        data = {col: row[idx] for idx, col in enumerate(load_cols)}
        values = []
        for col in columns:
            value = data.get(col)
            if value is None and col in DEFAULT_VALUES:
                value = DEFAULT_VALUES[col]
            values.append(value)
        prepared_rows.append(tuple(values))

    pg_cur.executemany(upsert_sql, prepared_rows)

    # Ajusta sequence para novos inserts sem colisão
    pg_cur.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true);"
    )
    return len(prepared_rows)


def main() -> int:
    args = parse_args()
    source_path = Path(args.source)
    target_url = (args.target or "").strip()

    if not source_path.exists():
        raise SystemExit(f"SQLite não encontrado: {source_path}")
    if not target_url:
        raise SystemExit("Informe --target ou JR_ESCALA_DATABASE_URL")

    # Garante schema do app no PostgreSQL
    os.environ["JR_ESCALA_DATABASE_URL"] = target_url
    os.environ["JR_ESCALA_ENABLE_SEED"] = "0"
    from web.db import init_db

    init_db()

    sqlite_conn = sqlite3.connect(source_path)
    sqlite_cur = sqlite_conn.cursor()

    imported_total = 0
    with psycopg.connect(target_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as pg_cur:
            for table, columns in TABLES:
                count = migrate_table(sqlite_cur, pg_cur, table, columns)
                imported_total += count
                print(f"{table}: {count}")
        pg_conn.commit()

    sqlite_conn.close()
    print(f"Total migrado: {imported_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
