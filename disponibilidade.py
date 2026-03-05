from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import logging
import sqlite3
from typing import Any, Dict, Iterable, Set

_DB_PATH = Path("jr_escala.db")
_OBS_DURACOES: Dict[str, int] = {}
_MAX_DURACAO = 0
_logger = logging.getLogger(__name__)


def configurar_base_disponibilidade(
    db_path: str | Path, observacao_duracoes: dict[str, int] | None = None
) -> None:
    """Define o caminho do banco e a tabela de duração das observações."""
    global _DB_PATH, _OBS_DURACOES, _MAX_DURACAO
    _DB_PATH = Path(db_path)
    if observacao_duracoes is not None:
        _OBS_DURACOES = dict(observacao_duracoes)
        _MAX_DURACAO = max(_OBS_DURACOES.values() or [0])


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_DB_PATH)


def _safe_fetch(cur: sqlite3.Cursor, query: str, params: Iterable[Any] = ()):
    try:
        cur.execute(query, tuple(params))
    except sqlite3.OperationalError:
        _logger.exception("Erro SQL ao verificar disponibilidade.")
        raise
    return cur.fetchall()


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def verificar_disponibilidade(
    data_iso: str, ignorar: dict[str, int] | None = None
) -> dict[str, Set[Any]]:
    """
    Retorna conjuntos com IDs/placas indisponíveis para a data informada.

    chaves: "motoristas", "ajudantes", "caminhoes"
    """
    resultado: dict[str, Set[Any]] = {
        "motoristas": set(),
        "ajudantes": set(),
        "caminhoes": set(),
    }
    data_iso = (data_iso or "").strip()
    alvo = _parse_date(data_iso)
    if not alvo:
        return resultado

    ignorar = ignorar or {}

    with _connect() as conn:
        cur = conn.cursor()

        ajustes_atuais = {}
        for car_id, duracao_nova in _safe_fetch(
            cur,
            """
            SELECT a.carregamento_id, a.duracao_nova
            FROM ajustes_rotas a
            INNER JOIN (
                SELECT carregamento_id, MAX(id) AS max_id
                FROM ajustes_rotas
                GROUP BY carregamento_id
            ) ult
            ON ult.carregamento_id = a.carregamento_id
            AND ult.max_id = a.id
            """,
        ):
            ajustes_atuais[car_id] = duracao_nova

        # Férias têm prioridade máxima
        for ferias_id, col_id, inicio, fim in _safe_fetch(
            cur,
            "SELECT id, colaborador_id, data_inicio, data_fim FROM ferias",
        ):
            if not col_id or ignorar.get("ferias_id") == ferias_id:
                continue
            d_inicio = _parse_date(inicio)
            d_fim = _parse_date(fim)
            if d_inicio and d_fim and d_inicio <= alvo <= d_fim:
                resultado["motoristas"].add(col_id)
                resultado["ajudantes"].add(col_id)

        # Folgas (bloqueia apenas no dia selecionado)
        for folga_id, col_id in _safe_fetch(
            cur,
            "SELECT id, colaborador_id FROM folgas WHERE data = ?",
            (data_iso,),
        ):
            if not col_id or ignorar.get("folga_id") == folga_id:
                continue
            resultado["motoristas"].add(col_id)
            resultado["ajudantes"].add(col_id)

        # Oficinas bloqueiam motorista e caminhão
        for ofi_id, mot_id, placa in _safe_fetch(
            cur,
            "SELECT id, motorista_id, placa FROM oficinas WHERE data = ?",
            (data_iso,),
        ):
            if ignorar.get("oficina_id") == ofi_id:
                continue
            if mot_id:
                resultado["motoristas"].add(mot_id)
            if placa:
                resultado["caminhoes"].add(placa.upper())

        # Escala CD
        for escala_id, mot_id, aju_id in _safe_fetch(
            cur,
            "SELECT id, motorista_id, ajudante_id FROM escala_cd WHERE data = ?",
            (data_iso,),
        ):
            if ignorar.get("escala_cd_id") == escala_id:
                continue
            if mot_id:
                resultado["motoristas"].add(mot_id)
            if aju_id:
                resultado["ajudantes"].add(aju_id)

        # Bloqueios (rotas longas)
        for bloq_id, col_id, inicio, fim, car_id in _safe_fetch(
            cur,
            """
            SELECT id, colaborador_id, data_inicio, data_fim, carregamento_id
            FROM bloqueios
            """,
        ):
            if not col_id:
                continue
            if car_id:
                if ignorar.get("carregamento_id") == car_id:
                    continue
                # Bloqueios de carregamentos sao tratados abaixo com data_saida.
                continue
            d_inicio = _parse_date(inicio)
            d_fim = _parse_date(fim)
            if d_inicio and d_fim and d_inicio <= alvo <= d_fim:
                resultado["motoristas"].add(col_id)
                resultado["ajudantes"].add(col_id)

        # Carregamentos (motoristas, ajudantes e caminhões)
        if _MAX_DURACAO >= 0:
            for (
                car_id,
                data_registro,
                data_saida,
                mot_id,
                aju_id,
                placa,
                observacao,
            ) in _safe_fetch(
                cur,
                """
                SELECT id, data, data_saida, motorista_id, ajudante_id, placa, observacao
                FROM carregamentos
                """,
            ):
                if ignorar.get("carregamento_id") == car_id:
                    continue
                data_registro_dt = _parse_date(data_registro)
                data_saida_dt = _parse_date(data_saida)
                if not data_registro_dt and not data_saida_dt:
                    continue
                if not data_registro_dt:
                    data_registro_dt = data_saida_dt
                if not data_saida_dt and data_registro_dt:
                    dias_padrao = 3 if data_registro_dt.weekday() == 4 else 1
                    data_saida_dt = data_registro_dt + timedelta(days=dias_padrao)
                if data_saida_dt and data_registro_dt and data_saida_dt < data_registro_dt:
                    data_saida_dt = data_registro_dt
                dias = ajustes_atuais.get(
                    car_id, _OBS_DURACOES.get((observacao or "").strip(), 0)
                )
                if dias < 0:
                    continue
                duracao_dias = max(dias, 0)
                bloquear_registro = data_registro_dt == alvo if data_registro_dt else False
                bloquear_viagem = False
                if duracao_dias > 0:
                    inicio_viagem = data_saida_dt or data_registro_dt
                    if inicio_viagem:
                        fim_viagem = inicio_viagem + timedelta(days=duracao_dias)
                        bloquear_viagem = inicio_viagem <= alvo <= fim_viagem
                if bloquear_registro or bloquear_viagem:
                    if mot_id:
                        resultado["motoristas"].add(mot_id)
                    if aju_id:
                        resultado["ajudantes"].add(aju_id)
                    if placa:
                        resultado["caminhoes"].add(placa.upper())

    return resultado


__all__ = ["configurar_base_disponibilidade", "verificar_disponibilidade"]
