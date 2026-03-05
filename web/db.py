from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = Path(os.environ.get("JR_ESCALA_DB_PATH", BASE_DIR / "jr_escala_web.db"))
UPLOAD_DIR = Path(os.environ.get("JR_ESCALA_UPLOAD_DIR", BASE_DIR / "uploads"))
REPORTS_DIR = Path(os.environ.get("JR_ESCALA_REPORTS_DIR", BASE_DIR / "reports"))
LOGO_PATH = Path(os.environ.get("JR_ESCALA_LOGO_PATH", BASE_DIR / "static" / "img" / "logo-jr.png"))
FONT_PATH = Path(os.environ.get("JR_ESCALA_FONT_PATH", BASE_DIR / "static" / "fonts" / "Sora.ttf"))
RUNTIME_FALLBACK_DIR = Path(os.environ.get("JR_ESCALA_RUNTIME_DIR", "/tmp/jr_escala"))
SEED_DATA_PATH = Path(os.environ.get("JR_ESCALA_SEED_PATH", BASE_DIR / "seed_data.json"))


def _activate_runtime_fallback() -> None:
    global DB_PATH, UPLOAD_DIR, REPORTS_DIR
    RUNTIME_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = RUNTIME_FALLBACK_DIR / "jr_escala_web.db"
    UPLOAD_DIR = RUNTIME_FALLBACK_DIR / "uploads"
    REPORTS_DIR = RUNTIME_FALLBACK_DIR / "reports"


def ensure_dirs() -> None:
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        _activate_runtime_fallback()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.OperationalError:
        _activate_runtime_fallback()
        conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _seed_core_data_if_empty(cur: sqlite3.Cursor) -> None:
    if not SEED_DATA_PATH.exists():
        return

    cur.execute("SELECT COUNT(*) FROM colaboradores;")
    total_colaboradores = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM caminhoes;")
    total_caminhoes = cur.fetchone()[0]
    if total_colaboradores > 0 or total_caminhoes > 0:
        return

    try:
        payload = json.loads(SEED_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    colaboradores = payload.get("colaboradores") or []
    caminhoes = payload.get("caminhoes") or []

    for item in colaboradores:
        nome = (item.get("nome") or "").strip()
        funcao = (item.get("funcao") or "").strip()
        if not nome or not funcao:
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO colaboradores (id, nome, funcao, observacao, foto, ativo)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                item.get("id"),
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
            INSERT OR IGNORE INTO caminhoes (id, placa, modelo, observacao, ativo)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                item.get("id"),
                placa,
                (item.get("modelo") or "").strip(),
                (item.get("observacao") or "").strip(),
                1 if item.get("ativo", 1) else 0,
            ),
        )


def init_db() -> None:
    ensure_dirs()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS colaboradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                funcao TEXT NOT NULL,
                observacao TEXT DEFAULT '',
                foto TEXT DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS folgas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                data_fim TEXT,
                data_saida TEXT,
                colaborador_id INTEGER NOT NULL,
                observacao_padrao TEXT,
                observacao_extra TEXT,
                observacao_cor TEXT,
                FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id),
                UNIQUE(data, colaborador_id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ferias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colaborador_id INTEGER NOT NULL,
                data_inicio TEXT NOT NULL,
                data_fim TEXT NOT NULL,
                observacao TEXT,
                FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS carregamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                data_saida TEXT,
                rota TEXT NOT NULL,
                placa TEXT,
                motorista_id INTEGER,
                ajudante_id INTEGER,
                observacao TEXT,
                observacao_extra TEXT,
                observacao_cor TEXT,
                revisado INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(motorista_id) REFERENCES colaboradores(id),
                FOREIGN KEY(ajudante_id) REFERENCES colaboradores(id),
                UNIQUE(data, rota, placa)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS oficinas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                motorista_id INTEGER,
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
            """
            CREATE TABLE IF NOT EXISTS caminhoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa TEXT UNIQUE NOT NULL,
                modelo TEXT,
                observacao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bloqueios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colaborador_id INTEGER NOT NULL,
                data_inicio TEXT NOT NULL,
                data_fim TEXT NOT NULL,
                motivo TEXT,
                carregamento_id INTEGER,
                FOREIGN KEY(colaborador_id) REFERENCES colaboradores(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rotas_semanais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dia_semana TEXT NOT NULL,
                rota TEXT NOT NULL,
                destino TEXT,
                observacao TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rotas_suprimidas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                rota TEXT NOT NULL,
                UNIQUE(data, rota)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS escala_cd (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                motorista_id INTEGER,
                ajudante_id INTEGER,
                observacao TEXT,
                FOREIGN KEY(motorista_id) REFERENCES colaboradores(id),
                FOREIGN KEY(ajudante_id) REFERENCES colaboradores(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ajustes_rotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carregamento_id INTEGER NOT NULL,
                data_ajuste TEXT NOT NULL,
                duracao_anterior INTEGER NOT NULL,
                duracao_nova INTEGER NOT NULL,
                observacao_ajuste TEXT,
                FOREIGN KEY(carregamento_id) REFERENCES carregamentos(id)
            );
            """
        )
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
