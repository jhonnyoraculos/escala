from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None

try:
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover
    ConnectionPool = None

BASE_DIR = Path(__file__).resolve().parent


def _extract_database_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = text.strip().strip('"').strip("'")
    match = re.search(r"(postgres(?:ql)?://[^\s\"']+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return text


def _default_data_root() -> Path:
    if os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER") == "true":
        return Path("/var/data")
    return BASE_DIR


DATABASE_URL = _extract_database_url(os.environ.get("JR_ESCALA_DATABASE_URL") or os.environ.get("DATABASE_URL") or "")
DB_IS_POSTGRES = DATABASE_URL.lower().startswith(("postgres://", "postgresql://"))

DATA_ROOT = _default_data_root()
DEFAULT_DB_NAME = "jr_escala.db" if DATA_ROOT != BASE_DIR else "jr_escala_web.db"

DB_PATH = Path(os.environ.get("JR_ESCALA_DB_PATH", DATA_ROOT / DEFAULT_DB_NAME))
UPLOAD_DIR = Path(os.environ.get("JR_ESCALA_UPLOAD_DIR", DATA_ROOT / "uploads"))
REPORTS_DIR = Path(os.environ.get("JR_ESCALA_REPORTS_DIR", DATA_ROOT / "reports"))
LOGO_PATH = Path(os.environ.get("JR_ESCALA_LOGO_PATH", BASE_DIR / "static" / "img" / "logo-jr.png"))
FONT_PATH = Path(os.environ.get("JR_ESCALA_FONT_PATH", BASE_DIR / "static" / "fonts" / "Sora.ttf"))
RUNTIME_FALLBACK_DIR = Path(os.environ.get("JR_ESCALA_RUNTIME_DIR", "/tmp/jr_escala"))
SEED_DATA_PATH = Path(os.environ.get("JR_ESCALA_SEED_PATH", BASE_DIR / "seed_data.json"))
SEED_ENABLED = (os.environ.get("JR_ESCALA_ENABLE_SEED", "0").strip().lower() in {"1", "true", "yes", "on"})
PG_POOL_ENABLED = (os.environ.get("JR_ESCALA_ENABLE_PG_POOL", "0").strip().lower() in {"1", "true", "yes", "on"})
PG_POOL = None


def _activate_runtime_fallback() -> None:
    global DB_PATH, UPLOAD_DIR, REPORTS_DIR
    RUNTIME_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = RUNTIME_FALLBACK_DIR / "jr_escala_web.db"
    UPLOAD_DIR = RUNTIME_FALLBACK_DIR / "uploads"
    REPORTS_DIR = RUNTIME_FALLBACK_DIR / "reports"


def ensure_dirs() -> None:
    try:
        if not DB_IS_POSTGRES:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        _activate_runtime_fallback()
        if not DB_IS_POSTGRES:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _append_clause(sql: str, clause: str) -> str:
    stripped = sql.rstrip()
    if stripped.endswith(";"):
        return f"{stripped[:-1]}{clause};"
    return f"{stripped}{clause}"


def _qmark_to_percent(sql: str) -> str:
    out: list[str] = []
    i = 0
    in_single = False
    in_double = False
    length = len(sql)
    while i < length:
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < length and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _translate_query_for_pg(query: str) -> tuple[str, bool]:
    sql = query
    sql = re.sub(r"\s+COLLATE\s+NOCASE\b", "", sql, flags=re.IGNORECASE)

    used_insert_or_ignore = False
    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", sql, flags=re.IGNORECASE):
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.IGNORECASE)
        used_insert_or_ignore = True

    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGSERIAL PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )

    upper_sql = sql.upper()
    is_insert = bool(re.match(r"\s*INSERT\b", upper_sql))

    if used_insert_or_ignore and "ON CONFLICT" not in upper_sql:
        sql = _append_clause(sql, " ON CONFLICT DO NOTHING")
        upper_sql = sql.upper()

    wants_lastrowid = False
    if is_insert and "RETURNING" not in upper_sql:
        sql = _append_clause(sql, " RETURNING id")
        wants_lastrowid = True

    sql = _qmark_to_percent(sql)
    return sql, wants_lastrowid


class PgCompatCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid: int | None = None

    def execute(self, query: str, params: Iterable[Any] = ()):
        sql, wants_lastrowid = _translate_query_for_pg(query)
        values = tuple(params or ())
        self._cur.execute(sql, values)
        if wants_lastrowid:
            row = self._cur.fetchone()
            if isinstance(row, dict):
                self.lastrowid = row.get("id")
            elif row:
                self.lastrowid = row[0]
            else:
                self.lastrowid = None
        return self

    def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]):
        for params in seq_of_params:
            self.execute(query, params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self) -> None:
        self._cur.close()

    def __iter__(self):
        return iter(self._cur)


class PgCompatConnection:
    def __init__(self, raw_conn, pool=None):
        self._conn = raw_conn
        self._pool = pool
        self._released = False
        self.row_factory = None

    def cursor(self):
        kwargs = {}
        if self.row_factory is not None and dict_row is not None:
            kwargs["row_factory"] = dict_row
        return PgCompatCursor(self._conn.cursor(**kwargs))

    def execute(self, query: str, params: Iterable[Any] = ()):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        if self._pool is not None:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def _pool_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _get_pg_pool():
    global PG_POOL
    if not DB_IS_POSTGRES or ConnectionPool is None or not PG_POOL_ENABLED:
        return None
    if PG_POOL is None:
        min_size = _pool_int("JR_ESCALA_PG_POOL_MIN", 1, 1, 20)
        max_size = _pool_int("JR_ESCALA_PG_POOL_MAX", 8, min_size, 40)
        timeout_raw = os.environ.get("JR_ESCALA_PG_POOL_TIMEOUT", "10")
        try:
            timeout = max(1.0, float(timeout_raw))
        except ValueError:
            timeout = 10.0
        PG_POOL = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            kwargs={"autocommit": False},
            open=True,
        )
    return PG_POOL


def get_connection():
    if DB_IS_POSTGRES:
        if psycopg is None:
            raise RuntimeError("psycopg não está instalado. Adicione 'psycopg[binary]' ao requirements.txt")
        pool = _get_pg_pool()
        if pool is not None:
            try:
                raw = pool.getconn()
                return PgCompatConnection(raw, pool=pool)
            except Exception:
                pass
        raw = psycopg.connect(DATABASE_URL, autocommit=False)
        return PgCompatConnection(raw)

    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.OperationalError:
        _activate_runtime_fallback()
        conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ping_database() -> dict[str, Any]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        row = cur.fetchone()
        valor = None
        if isinstance(row, dict):
            valor = next(iter(row.values()), None)
        elif row:
            valor = row[0]
        return {
            "db_is_postgres": DB_IS_POSTGRES,
            "value": valor,
        }


def _seed_core_data_if_empty(cur) -> None:
    if not SEED_ENABLED:
        return
    if not SEED_DATA_PATH.exists():
        return

    try:
        payload = json.loads(SEED_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    colaboradores = payload.get("colaboradores") or []
    caminhoes = payload.get("caminhoes") or []
    rotas_semanais = payload.get("rotas_semanais") or []

    for item in colaboradores:
        nome = (item.get("nome") or "").strip()
        funcao = (item.get("funcao") or "").strip()
        if not nome or not funcao:
            continue
        cur.execute(
            """
            SELECT 1
            FROM colaboradores
            WHERE UPPER(TRIM(nome)) = UPPER(?)
              AND LOWER(TRIM(funcao)) = LOWER(?)
            LIMIT 1;
            """,
            (nome, funcao),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO colaboradores (nome, funcao, observacao, foto, ativo)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                nome,
                funcao,
                (item.get("observacao") or "").strip(),
                (item.get("foto") or "").strip(),
                1 if item.get("ativo", 1) else 0,
            ),
        )

    for item in caminhoes:
        placa = (item.get("placa") or "").strip().upper()
        if not placa:
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO caminhoes (placa, modelo, observacao, ativo)
            VALUES (?, ?, ?, ?);
            """,
            (
                placa,
                (item.get("modelo") or "").strip(),
                (item.get("observacao") or "").strip(),
                1 if item.get("ativo", 1) else 0,
            ),
        )

    for item in rotas_semanais:
        dia_semana = (item.get("dia_semana") or "").strip().lower()
        rota = (item.get("rota") or "").strip()
        destino = (item.get("destino") or "").strip()
        observacao = (item.get("observacao") or "").strip()
        if not dia_semana or not rota:
            continue
        cur.execute(
            """
            SELECT 1
            FROM rotas_semanais
            WHERE LOWER(TRIM(dia_semana)) = LOWER(?)
              AND TRIM(rota) = ?
              AND COALESCE(TRIM(destino), '') = ?
              AND COALESCE(TRIM(observacao), '') = ?
            LIMIT 1;
            """,
            (dia_semana, rota, destino, observacao),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO rotas_semanais (dia_semana, rota, destino, observacao)
            VALUES (?, ?, ?, ?);
            """,
            (dia_semana, rota, destino, observacao),
        )


def _create_schema(cur) -> None:
    id_col = "BIGSERIAL PRIMARY KEY" if DB_IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    int_col = "BIGINT" if DB_IS_POSTGRES else "INTEGER"
    flag_col = "SMALLINT" if DB_IS_POSTGRES else "INTEGER"

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS colaboradores (
            id {id_col},
            nome TEXT NOT NULL,
            funcao TEXT NOT NULL,
            observacao TEXT DEFAULT '',
            foto TEXT DEFAULT '',
            ativo {flag_col} NOT NULL DEFAULT 1
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS folgas (
            id {id_col},
            data TEXT NOT NULL,
            data_fim TEXT,
            data_saida TEXT,
            colaborador_id {int_col} NOT NULL,
            observacao_padrao TEXT,
            observacao_extra TEXT,
            observacao_cor TEXT,
            FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id),
            UNIQUE(data, colaborador_id)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ferias (
            id {id_col},
            colaborador_id {int_col} NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            observacao TEXT,
            FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS carregamentos (
            id {id_col},
            data TEXT NOT NULL,
            data_saida TEXT,
            rota TEXT NOT NULL,
            placa TEXT,
            motorista_id {int_col},
            ajudante_id {int_col},
            observacao TEXT,
            observacao_extra TEXT,
            observacao_cor TEXT,
            revisado {flag_col} NOT NULL DEFAULT 0,
            FOREIGN KEY(motorista_id) REFERENCES colaboradores(id),
            FOREIGN KEY(ajudante_id) REFERENCES colaboradores(id),
            UNIQUE(data, rota, placa)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS oficinas (
            id {id_col},
            data TEXT NOT NULL,
            motorista_id {int_col},
            placa TEXT NOT NULL,
            observacao TEXT,
            observacao_extra TEXT,
            data_saida TEXT,
            observacao_cor TEXT,
            FOREIGN KEY(motorista_id) REFERENCES colaboradores(id),
            UNIQUE(data, placa)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS caminhoes (
            id {id_col},
            placa TEXT UNIQUE NOT NULL,
            modelo TEXT,
            observacao TEXT,
            ativo {flag_col} NOT NULL DEFAULT 1
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS bloqueios (
            id {id_col},
            colaborador_id {int_col} NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            motivo TEXT,
            carregamento_id {int_col},
            FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS rotas_semanais (
            id {id_col},
            dia_semana TEXT NOT NULL,
            rota TEXT NOT NULL,
            destino TEXT,
            observacao TEXT
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS rotas_suprimidas (
            id {id_col},
            data TEXT NOT NULL,
            rota TEXT NOT NULL,
            UNIQUE(data, rota)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS escala_cd (
            id {id_col},
            data TEXT NOT NULL,
            motorista_id {int_col},
            ajudante_id {int_col},
            observacao TEXT,
            FOREIGN KEY(motorista_id) REFERENCES colaboradores(id),
            FOREIGN KEY(ajudante_id) REFERENCES colaboradores(id)
        );
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ajustes_rotas (
            id {id_col},
            carregamento_id {int_col} NOT NULL,
            data_ajuste TEXT NOT NULL,
            duracao_anterior INTEGER NOT NULL,
            duracao_nova INTEGER NOT NULL,
            observacao_ajuste TEXT,
            FOREIGN KEY(carregamento_id) REFERENCES carregamentos(id)
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_ativo_nome ON colaboradores (ativo, nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_funcao_nome ON colaboradores (funcao, nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_folgas_data ON folgas (data);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_folgas_colaborador ON folgas (colaborador_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_periodo ON ferias (data_inicio, data_fim);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_colaborador ON ferias (colaborador_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_carregamentos_data ON carregamentos (data);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_carregamentos_data_saida ON carregamentos (data_saida);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_carregamentos_motorista ON carregamentos (motorista_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_carregamentos_ajudante ON carregamentos (ajudante_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_carregamentos_placa ON carregamentos (placa);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_data ON oficinas (data);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_data_saida ON oficinas (data_saida);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_motorista ON oficinas (motorista_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oficinas_placa ON oficinas (placa);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_caminhoes_ativo_placa ON caminhoes (ativo, placa);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bloqueios_periodo ON bloqueios (data_inicio, data_fim);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bloqueios_colaborador_periodo ON bloqueios (colaborador_id, data_inicio, data_fim);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bloqueios_carregamento ON bloqueios (carregamento_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rotas_semanais_dia_rota ON rotas_semanais (dia_semana, rota);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_escala_cd_data ON escala_cd (data);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ajustes_rotas_carregamento_id ON ajustes_rotas (carregamento_id, id);")


def init_db() -> None:
    ensure_dirs()
    with get_connection() as conn:
        cur = conn.cursor()
        _create_schema(cur)

        if DB_IS_POSTGRES:
            cur.execute("ALTER TABLE carregamentos ADD COLUMN IF NOT EXISTS revisado SMALLINT NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE folgas ADD COLUMN IF NOT EXISTS data_saida TEXT;")
        else:
            cur.execute("PRAGMA table_info(carregamentos);")
            colunas_carregamentos = {row[1] for row in cur.fetchall()}
            if "revisado" not in colunas_carregamentos:
                cur.execute("ALTER TABLE carregamentos ADD COLUMN revisado INTEGER NOT NULL DEFAULT 0;")
            cur.execute("PRAGMA table_info(folgas);")
            colunas_folgas = {row[1] for row in cur.fetchall()}
            if "data_saida" not in colunas_folgas:
                cur.execute("ALTER TABLE folgas ADD COLUMN data_saida TEXT;")

        _seed_core_data_if_empty(cur)
        conn.commit()
