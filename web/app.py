from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import time

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for

from .db import UPLOAD_DIR, init_db
from . import services as svc
from .reports import (
    desenhar_relatorio_carregamentos,
    exportar_log_para_excel,
    gerar_relatorio_escala_cd,
    gerar_relatorio_folgas,
    gerar_relatorio_oficinas,
)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "jr-escala-web"

init_db()

NAV_ITEMS = [
    ("carregamentos", "Carregamentos", "/carregamentos"),
    ("escala_cd", "Escala (CD)", "/escala-cd"),
    ("folgas", "Folgas", "/folgas"),
    ("oficinas", "Oficinas", "/oficinas"),
    ("rotas", "Rotas Semanais", "/rotas-semanais"),
    ("caminhoes", "Caminhões", "/caminhoes"),
    ("ferias", "Férias", "/ferias"),
    ("colaboradores", "Colaboradores", "/colaboradores"),
    ("log", "LOG", "/log"),
]


def _data_param(nome: str, default: str | None = None) -> str:
    valor = (request.args.get(nome) or "").strip()
    if valor:
        return valor
    return default or date.today().isoformat()


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


@app.context_processor
def inject_globals():
    static_files = [
        Path(app.static_folder) / "js" / "app.js",
        Path(app.static_folder) / "css" / "app.css",
    ]
    mtimes = [p.stat().st_mtime for p in static_files if p.exists()]
    static_version = str(int(max(mtimes))) if mtimes else str(int(time.time()))
    return {
        "NAV_ITEMS": NAV_ITEMS,
        "TODAY_ISO": date.today().isoformat(),
        "data_iso_para_br": svc.data_iso_para_br,
        "data_iso_para_extenso": svc.data_iso_para_extenso,
        "OBS_OPCOES": svc.OBSERVACAO_OPCOES,
        "OBS_MARCADORES": svc.OBS_MARCADORES,
        "VALOR_SEM_MOTORISTA": svc.VALOR_SEM_MOTORISTA,
        "VALOR_SEM_AJUDANTE": svc.VALOR_SEM_AJUDANTE,
        "VALOR_SEM_CAMINHAO": svc.VALOR_SEM_CAMINHAO,
        "STATIC_VERSION": static_version,
        "CARREG_DATA_ISO": session.get("carreg_data_iso") or date.today().isoformat(),
    }


@app.route("/")
def index():
    return redirect(url_for("carregamentos"))


@app.get("/assistente-rotas")
def assistente_rotas():
    data_iso = (request.args.get("data") or session.get("carreg_data_iso") or date.today().isoformat()).strip()
    registros = svc.listar_carregamentos(data_iso)
    pendentes = []
    for item in registros:
        if item.get("revisado"):
            continue
        rota = item.get("rota") or svc.DISPLAY_VAZIO
        placa = (item.get("placa") or "").strip() or svc.DISPLAY_VAZIO
        motorista = item.get("motorista_nome") or svc.DISPLAY_VAZIO
        pendentes.append(
            {
                "rota": rota,
                "label": f"{rota} | {placa} | {motorista}",
            }
        )
    pendentes.sort(key=_numero_rota_ordem)
    return jsonify(
        {
            "data": data_iso,
            "data_br": svc.data_iso_para_br(data_iso),
            "total": len(pendentes),
            "rotas": pendentes,
        }
    )


@app.get("/assistente-disponiveis")
def assistente_disponiveis():
    data_iso = (request.args.get("data") or session.get("carreg_data_iso") or date.today().isoformat()).strip()
    motoristas = svc.listar_colaboradores_por_funcao("Motorista", data_iso)
    ajudantes = svc.listar_colaboradores_por_funcao("Ajudante", data_iso)
    nomes_motoristas = sorted([m.get("nome") for m in motoristas if m.get("nome")])
    nomes_ajudantes = sorted([a.get("nome") for a in ajudantes if a.get("nome")])
    total = len(nomes_motoristas) + len(nomes_ajudantes)
    return jsonify(
        {
            "data": data_iso,
            "data_br": svc.data_iso_para_br(data_iso),
            "total": total,
            "motoristas": nomes_motoristas,
            "ajudantes": nomes_ajudantes,
        }
    )


@app.route("/uploads/<path:filename>")
def uploads(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/carregamentos", methods=["GET", "POST"])
def carregamentos():
    data_iso = _data_param("data")
    permitir_mot_aj = (request.values.get("permitir_mot_aj") or "") == "1"
    session["carreg_data_iso"] = data_iso

    if request.method == "POST":
        carregamento_id = _int(request.form.get("carregamento_id"))
        data_iso = (request.form.get("data") or data_iso).strip()
        data_saida = (request.form.get("data_saida") or "").strip() or None
        session["carreg_data_iso"] = data_iso
        session["carreg_data_saida_iso"] = data_saida or ""
        rota_num = (request.form.get("rota_num") or "").strip()
        rota_destino = (request.form.get("rota_destino") or "").strip()
        placa = (request.form.get("placa") or "").strip() or None
        motorista_id = _int(request.form.get("motorista_id"))
        ajudante_id = _int(request.form.get("ajudante_id"))
        observacao = (request.form.get("observacao") or "0").strip() or "0"
        observacao_extra = (request.form.get("observacao_extra") or "").strip() or None
        observacao_cor = (request.form.get("observacao_cor") or "").strip() or None
        registro_anterior = svc.obter_carregamento(carregamento_id) if carregamento_id else None
        redirect_params_base = {"data": data_iso, "permitir_mot_aj": int(permitir_mot_aj)}
        if data_saida:
            redirect_params_base["data_saida"] = data_saida
        redirect_params_edit = dict(redirect_params_base)
        if carregamento_id:
            redirect_params_edit["edit_id"] = carregamento_id

        if not rota_num or not rota_destino:
            flash("Informe rota e destino.", "error")
            return redirect(url_for("carregamentos", **redirect_params_edit))

        rota_texto = f"{rota_num} - {rota_destino}"
        ignorar = {"carregamento_id": carregamento_id} if carregamento_id else None
        disponibilidade = svc.verificar_disponibilidade(data_iso, ignorar)
        indis_colaboradores = disponibilidade.get("motoristas", set()).union(
            disponibilidade.get("ajudantes", set())
        )
        if motorista_id and motorista_id in indis_colaboradores:
            flash("Motorista indisponível nesta data.", "error")
            return redirect(url_for("carregamentos", **redirect_params_edit))
        if ajudante_id and ajudante_id in indis_colaboradores:
            flash("Ajudante indisponível nesta data.", "error")
            return redirect(url_for("carregamentos", **redirect_params_edit))
        if placa and placa.upper() in disponibilidade.get("caminhoes", set()):
            flash("Caminhão indisponível nesta data.", "error")
            return redirect(url_for("carregamentos", **redirect_params_edit))

        sucesso = False
        try:
            if carregamento_id:
                svc.atualizar_carregamento(
                    carregamento_id,
                    data_iso,
                    data_saida,
                    rota_texto,
                    placa,
                    motorista_id,
                    ajudante_id,
                    observacao,
                    observacao_extra,
                    observacao_cor,
                )
                if registro_anterior and registro_anterior.get("rota") != rota_texto:
                    svc.registrar_rota_suprimida(registro_anterior.get("data"), registro_anterior.get("rota"))
                svc.remover_bloqueios_por_carregamento(carregamento_id)
                svc.criar_bloqueios_para_carregamento(
                    carregamento_id,
                    data_iso,
                    [motorista_id, ajudante_id],
                    observacao,
                )
                flash("Carregamento atualizado.", "success")
                sucesso = True
            else:
                novo_id = svc.salvar_carregamento(
                    data_iso,
                    rota_texto,
                    placa,
                    motorista_id,
                    ajudante_id,
                    observacao,
                    observacao_extra,
                    observacao_cor,
                    data_saida,
                    revisado=True,
                )
                svc.criar_bloqueios_para_carregamento(
                    novo_id,
                    data_iso,
                    [motorista_id, ajudante_id],
                    observacao,
                )
                flash("Carregamento salvo.", "success")
                sucesso = True
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")

        return redirect(url_for("carregamentos", **(redirect_params_base if sucesso else redirect_params_edit)))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = svc.obter_carregamento(edit_id) if edit_id else None
    if edit_item:
        edit_item["data_saida"] = svc.obter_data_saida_registro(edit_item)

    rota_num = ""
    rota_destino = ""
    if edit_item and edit_item.get("rota"):
        rota_texto = edit_item.get("rota") or ""
        if " - " in rota_texto:
            rota_num, rota_destino = rota_texto.split(" - ", 1)
            rota_num = rota_num.strip()
            rota_destino = rota_destino.strip()
        else:
            rota_num = rota_texto.strip()

    data_saida = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_carregamento(data_iso)
    session["carreg_data_saida_iso"] = data_saida or ""

    registros = svc.listar_carregamentos(data_iso)
    for item in registros:
        item["data_saida"] = svc.obter_data_saida_registro(item)
    total_registros = len(registros)
    pendentes = sum(1 for item in registros if not item.get("revisado"))
    preenchidas = total_registros - pendentes
    if not registros:
        svc.preencher_carregamentos_automaticos(data_iso, data_saida)
        registros = svc.listar_carregamentos(data_iso)
    disponibilidade = svc.verificar_disponibilidade(data_iso, {"carregamento_id": edit_id} if edit_id else None)

    motoristas = svc.listar_colaboradores_por_funcao("Motorista")
    ajudantes = svc.listar_colaboradores_por_funcao("Ajudante")
    ajudantes_ids = {a.get("id") for a in ajudantes}
    ajudantes = ajudantes + [
        {
            "id": m["id"],
            "nome": f"{m['nome']} {svc.MOTORISTA_AJUDANTE_TAG}",
            "foto": m.get("foto"),
            "mot_aj": True,
        }
        for m in motoristas
        if m.get("id") not in ajudantes_ids
    ]

    caminhoes = svc.listar_caminhoes_ativos()
    carregamentos_dia = [
        {
            "id": item.get("id"),
            "label": f"{item.get('rota') or svc.DISPLAY_VAZIO} | {item.get('placa') or svc.DISPLAY_VAZIO} | {item.get('motorista_nome') or svc.DISPLAY_VAZIO}",
            "revisado": bool(item.get("revisado")),
        }
        for item in registros
    ]

    return render_template(
        "carregamentos.html",
        data_iso=data_iso,
        data_saida=data_saida,
        registros=registros,
        edit_item=edit_item,
        rota_num=rota_num,
        rota_destino=rota_destino,
        motoristas=motoristas,
        ajudantes=ajudantes,
        caminhoes=caminhoes,
        disponibilidade=disponibilidade,
        permitir_mot_aj=permitir_mot_aj,
        carregamentos_dia=carregamentos_dia,
        total_registros=total_registros,
        preenchidas=preenchidas,
        pendentes=pendentes,
    )


@app.post("/carregamentos/<int:carregamento_id>/excluir")
def excluir_carregamento(carregamento_id: int):
    data_iso = _data_param("data")
    try:
        registro = svc.obter_carregamento(carregamento_id)
        if registro:
            svc.registrar_rota_suprimida(registro.get("data"), registro.get("rota"))
        svc.remover_carregamento_completo(carregamento_id)
        flash("Carregamento excluído.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("carregamentos", data=data_iso))


@app.post("/carregamentos/<int:carregamento_id>/duplicar")
def duplicar_carregamento(carregamento_id: int):
    data_iso = _data_param("data")
    permitir_mot_aj = (request.values.get("permitir_mot_aj") or "") == "1"
    try:
        svc.duplicar_carregamento(carregamento_id)
        flash("Carregamento duplicado. Placa, motorista e ajudante ficaram em branco.", "success")
    except Exception as exc:
        flash(f"Erro ao duplicar: {exc}", "error")
    return redirect(url_for("carregamentos", data=data_iso, permitir_mot_aj=int(permitir_mot_aj)))


@app.post("/carregamentos/recarregar-rotas")
def recarregar_rotas_semanais():
    data_iso = _data_param("data")
    data_saida = (request.values.get("data_saida") or "").strip() or svc.calcular_data_saida_carregamento(data_iso)
    permitir_mot_aj = (request.values.get("permitir_mot_aj") or "") == "1"
    try:
        svc.limpar_rotas_suprimidas(data_iso)
        inseridos = svc.preencher_carregamentos_automaticos(data_iso, data_saida)
        if inseridos:
            flash(f"{inseridos} rota(s) semanal(is) adicionada(s).", "success")
        else:
            flash("Todas as rotas semanais já estão carregadas.", "success")
    except Exception as exc:
        flash(f"Erro ao recarregar rotas semanais: {exc}", "error")
    return redirect(url_for("carregamentos", data=data_iso, data_saida=data_saida, permitir_mot_aj=int(permitir_mot_aj)))


@app.post("/carregamentos/limpar-alteracoes")
def limpar_alteracoes_carregamentos():
    data_iso = _data_param("data")
    data_saida = (request.values.get("data_saida") or "").strip() or svc.calcular_data_saida_carregamento(data_iso)
    permitir_mot_aj = (request.values.get("permitir_mot_aj") or "") == "1"
    try:
        registros = svc.listar_carregamentos(data_iso)
        for item in registros:
            svc.remover_carregamento_completo(item["id"])
        svc.limpar_rotas_suprimidas(data_iso)
        inseridos = svc.preencher_carregamentos_automaticos(data_iso, data_saida)
        if registros and inseridos:
            flash(f"Alterações removidas. {inseridos} rota(s) semanal(is) recarregada(s).", "success")
        elif registros:
            flash("Alterações removidas. Nenhuma rota semanal para recarregar.", "success")
        elif inseridos:
            flash(f"{inseridos} rota(s) semanal(is) carregada(s).", "success")
        else:
            flash("Nada para limpar neste dia.", "success")
    except Exception as exc:
        flash(f"Erro ao limpar alterações: {exc}", "error")
    return redirect(url_for("carregamentos", data=data_iso, data_saida=data_saida, permitir_mot_aj=int(permitir_mot_aj)))


@app.get("/relatorios/carregamentos")
def relatorio_carregamentos():
    data_iso = _data_param("data")
    data_saida_iso = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_carregamento(data_iso)
    registros = svc.listar_carregamentos(data_iso)
    registros.sort(key=_numero_rota_ordem)
    linhas: list[list[str]] = []
    cores_obs: list[str | None] = []
    for item in registros:
        valores, cor = svc.DISPLAY_VAZIO, None
        valores, cor = __linha_relatorio_carregamento(item)
        linhas.append(valores)
        cores_obs.append(cor)
    caminho = desenhar_relatorio_carregamentos(data_iso, data_saida_iso, linhas, len(registros), cores_obs)
    return send_file(caminho, as_attachment=True)


def __linha_relatorio_carregamento(item: dict):
    from .reports import _linha_relatorio_carregamento

    return _linha_relatorio_carregamento(item)


def _numero_rota_ordem(item: dict) -> tuple[int, int | str]:
    rota = (item.get("rota") or "").strip()
    numero = rota.split(" - ", 1)[0].strip() if " - " in rota else rota
    if any(ch.isalpha() for ch in numero):
        return (1, numero.upper())
    digitos = "".join(ch for ch in numero if ch.isdigit())
    if digitos:
        return (0, int(digitos))
    return (1, numero.upper())

@app.route("/oficinas", methods=["GET", "POST"])
def oficinas():
    data_iso = _data_param("data")

    if request.method == "POST":
        oficina_id = _int(request.form.get("oficina_id"))
        data_iso = (request.form.get("data") or data_iso).strip()
        data_saida = (request.form.get("data_saida") or "").strip() or None
        motorista_id = _int(request.form.get("motorista_id"))
        placa = (request.form.get("placa") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()
        observacao_extra = (request.form.get("observacao_extra") or "").strip() or None
        observacao_cor = (request.form.get("observacao_cor") or "").strip() or None

        if not placa:
            flash("Informe a placa.", "error")
            return redirect(url_for("oficinas", data=data_iso))

        try:
            if oficina_id:
                svc.editar_oficina(
                    oficina_id,
                    motorista_id,
                    placa,
                    observacao,
                    observacao_extra,
                    data_saida,
                    observacao_cor,
                )
                flash("Oficina atualizada.", "success")
            else:
                svc.salvar_oficina(
                    data_iso,
                    motorista_id,
                    placa,
                    observacao,
                    observacao_extra,
                    data_saida,
                    observacao_cor,
                )
                flash("Oficina salva.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")

        return redirect(url_for("oficinas", data=data_iso))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = svc.obter_oficina(edit_id) if edit_id else None
    data_saida = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_padrao(data_iso)

    registros = svc.listar_oficinas(data_iso)
    disponibilidade = svc.verificar_disponibilidade(data_iso, {"oficina_id": edit_id} if edit_id else None)
    motoristas = svc.listar_colaboradores_por_funcao("Motorista")
    caminhoes = svc.listar_caminhoes_ativos()

    return render_template(
        "oficinas.html",
        data_iso=data_iso,
        data_saida=data_saida,
        registros=registros,
        edit_item=edit_item,
        motoristas=motoristas,
        caminhoes=caminhoes,
        disponibilidade=disponibilidade,
    )


@app.post("/oficinas/<int:oficina_id>/excluir")
def excluir_oficina(oficina_id: int):
    data_iso = _data_param("data")
    try:
        svc.excluir_oficina(oficina_id)
        flash("Oficina excluída.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("oficinas", data=data_iso))


@app.get("/relatorios/oficinas")
def relatorio_oficinas():
    data_iso = _data_param("data")
    data_saida_iso = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_padrao(data_iso)
    data_ref = data_saida_iso or data_iso
    registros = svc.listar_oficinas_por_data_saida(data_ref)
    caminho = gerar_relatorio_oficinas(data_iso, data_saida_iso, registros)
    return send_file(caminho, as_attachment=True)

@app.route("/folgas", methods=["GET", "POST"])
def folgas():
    data_iso = _data_param("data")

    if request.method == "POST":
        folga_id = _int(request.form.get("folga_id"))
        data_iso = (request.form.get("data") or data_iso).strip()
        data_fim = (request.form.get("data_fim") or "").strip() or None
        data_saida = svc.calcular_data_saida_padrao(data_iso)
        colaborador_id = _int(request.form.get("colaborador_id"))
        observacao_padrao = None
        observacao_extra = None
        observacao_cor = None

        if not colaborador_id:
            flash("Selecione um colaborador.", "error")
            return redirect(url_for("folgas", data=data_iso))

        try:
            if folga_id:
                svc.editar_folga(
                    folga_id,
                    data_iso,
                    data_fim,
                    data_saida,
                    colaborador_id,
                    observacao_padrao,
                    observacao_extra,
                    observacao_cor,
                )
                flash("Folga atualizada.", "success")
            else:
                svc.salvar_folga(
                    data_iso,
                    colaborador_id,
                    data_fim,
                    data_saida,
                    observacao_padrao,
                    observacao_extra,
                    observacao_cor,
                )
                flash("Folga salva.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")

        return redirect(url_for("folgas", data=data_iso))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = None
    if edit_id:
        for item in svc.listar_folgas(data_iso):
            if item.get("folga_id") == edit_id:
                edit_item = item
                break

    registros = svc.listar_folgas(data_iso)
    colaboradores = svc.listar_colaboradores(ativos_only=True)
    data_saida = svc.calcular_data_saida_padrao(data_iso)
    disponibilidade = svc.verificar_disponibilidade(
        data_iso, {"folga_id": edit_id} if edit_id else None
    )

    return render_template(
        "folgas.html",
        data_iso=data_iso,
        data_saida=data_saida,
        registros=registros,
        edit_item=edit_item,
        colaboradores=colaboradores,
        disponibilidade=disponibilidade,
    )


@app.post("/folgas/<int:folga_id>/excluir")
def excluir_folga(folga_id: int):
    data_iso = _data_param("data")
    try:
        svc.remover_folga(folga_id)
        flash("Folga excluída.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("folgas", data=data_iso))


@app.get("/relatorios/folgas")
def relatorio_folgas():
    data_iso = _data_param("data")
    data_saida_iso = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_padrao(data_iso)
    data_ref = data_saida_iso or data_iso
    registros = svc.listar_folgas_por_data_saida(data_ref)
    caminho = gerar_relatorio_folgas(data_iso, data_saida_iso, registros)
    return send_file(caminho, as_attachment=True)

@app.route("/escala-cd", methods=["GET", "POST"])
def escala_cd():
    data_iso = _data_param("data")

    if request.method == "POST":
        escala_id = _int(request.form.get("escala_id"))
        data_iso = (request.form.get("data") or data_iso).strip()
        data_saida = (request.form.get("data_saida") or "").strip() or None
        motorista_id = _int(request.form.get("motorista_id"))
        ajudante_id = _int(request.form.get("ajudante_id"))
        observacao = (request.form.get("observacao") or "").strip()

        ignorar = {"escala_cd_id": escala_id} if escala_id else None
        disponibilidade = svc.verificar_disponibilidade(data_iso, ignorar)
        indis_colaboradores = disponibilidade.get("motoristas", set()).union(
            disponibilidade.get("ajudantes", set())
        )
        if motorista_id and motorista_id in indis_colaboradores:
            flash("Motorista indisponível nesta data.", "error")
            return redirect(url_for("escala_cd", data=data_iso))
        if ajudante_id and ajudante_id in indis_colaboradores:
            flash("Ajudante indisponível nesta data.", "error")
            return redirect(url_for("escala_cd", data=data_iso))

        try:
            if escala_id:
                svc.editar_escala_cd(escala_id, motorista_id, ajudante_id, observacao)
                flash("Escala (CD) atualizada.", "success")
            else:
                svc.adicionar_escala_cd(data_iso, motorista_id, ajudante_id, observacao)
                flash("Escala (CD) salva.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")

        return redirect(url_for("escala_cd", data=data_iso))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = svc.obter_escala_cd(edit_id) if edit_id else None
    registros = svc.listar_escala_cd(data_iso)
    data_saida = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_padrao(data_iso)

    motoristas = svc.listar_colaboradores_por_funcao("Motorista")
    ajudantes = svc.listar_colaboradores_por_funcao("Ajudante")
    disponibilidade = svc.verificar_disponibilidade(data_iso, {"escala_cd_id": edit_id} if edit_id else None)

    return render_template(
        "escala_cd.html",
        data_iso=data_iso,
        data_saida=data_saida,
        registros=registros,
        edit_item=edit_item,
        motoristas=motoristas,
        ajudantes=ajudantes,
        disponibilidade=disponibilidade,
    )


@app.post("/escala-cd/<int:escala_id>/excluir")
def excluir_escala_cd(escala_id: int):
    data_iso = _data_param("data")
    try:
        svc.excluir_escala_cd(escala_id)
        flash("Escala (CD) excluída.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("escala_cd", data=data_iso))


@app.get("/relatorios/escala-cd")
def relatorio_escala_cd():
    data_iso = _data_param("data")
    data_saida_iso = (request.args.get("data_saida") or "").strip() or svc.calcular_data_saida_padrao(data_iso)
    registros = svc.listar_escala_cd(data_iso)
    caminho = gerar_relatorio_escala_cd(data_iso, data_saida_iso, registros)
    return send_file(caminho, as_attachment=True)

@app.route("/rotas-semanais", methods=["GET", "POST"])
def rotas_semanais():
    dia = svc.normalizar_dia_semana(request.args.get("dia"))

    if request.method == "POST":
        rota_id = _int(request.form.get("rota_id"))
        dia_form = svc.normalizar_dia_semana(request.form.get("dia_semana"))
        rota = (request.form.get("rota") or "").strip()
        destino = (request.form.get("destino") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()

        if not rota:
            flash("Informe a rota.", "error")
            return redirect(url_for("rotas_semanais", dia=dia_form))

        try:
            if rota_id:
                svc.editar_rota_semana(rota_id, dia_form, rota, destino, observacao)
                flash("Rota semanal atualizada.", "success")
            else:
                svc.adicionar_rota_semana(dia_form, rota, destino, observacao)
                svc.sincronizar_rota_semana_com_carregamentos(
                    session.get("carreg_data_iso"),
                    dia_form,
                    rota,
                    destino,
                    observacao,
                    session.get("carreg_data_saida_iso"),
                )
                flash("Rota semanal salva.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")

        return redirect(url_for("rotas_semanais", dia=dia_form))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = None
    if edit_id:
        for item in svc.listar_rotas_semanais(dia):
            if item.get("id") == edit_id:
                edit_item = item
                break

    registros = svc.listar_rotas_semanais(dia)

    return render_template(
        "rotas.html",
        dia_semana=dia,
        registros=registros,
        edit_item=edit_item,
        dias_semana=svc.DIAS_SEMANA,
    )


@app.post("/rotas-semanais/<int:rota_id>/excluir")
def excluir_rota_semana(rota_id: int):
    dia = svc.normalizar_dia_semana(request.args.get("dia"))
    try:
        svc.remover_rota_semana(rota_id)
        flash("Rota semanal excluída.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("rotas_semanais", dia=dia))

@app.route("/caminhoes", methods=["GET", "POST"])
def caminhoes():
    if request.method == "POST":
        caminhao_id = _int(request.form.get("caminhao_id"))
        placa = (request.form.get("placa") or "").strip()
        modelo = (request.form.get("modelo") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()
        ativo = (request.form.get("ativo") or "") == "on"

        if not placa:
            flash("Informe a placa.", "error")
            return redirect(url_for("caminhoes"))

        try:
            if caminhao_id:
                svc.editar_caminhao(caminhao_id, placa, modelo, observacao, ativo)
                flash("Caminhão atualizado.", "success")
            else:
                svc.add_caminhao(placa, modelo, observacao)
                flash("Caminhão salvo.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")
        return redirect(url_for("caminhoes"))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = None
    if edit_id:
        for item in svc.listar_caminhoes(ativos_only=False):
            if item.get("id") == edit_id:
                edit_item = item
                break

    registros = svc.listar_caminhoes(ativos_only=False)
    return render_template("caminhoes.html", registros=registros, edit_item=edit_item)


@app.post("/caminhoes/<int:caminhao_id>/excluir")
def excluir_caminhao(caminhao_id: int):
    try:
        svc.remover_caminhao(caminhao_id)
        flash("Caminhão excluído.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("caminhoes"))

@app.route("/ferias", methods=["GET", "POST"])
def ferias():
    if request.method == "POST":
        ferias_id = _int(request.form.get("ferias_id"))
        colaborador_id = _int(request.form.get("colaborador_id"))
        data_inicio = (request.form.get("data_inicio") or "").strip()
        data_fim = (request.form.get("data_fim") or "").strip()
        observacao = (request.form.get("observacao") or "").strip() or None

        if not colaborador_id or not data_inicio or not data_fim:
            flash("Informe colaborador e período.", "error")
            return redirect(url_for("ferias"))

        ignorar = {"ferias_id": ferias_id} if ferias_id else None
        disponibilidade = svc.verificar_disponibilidade(data_inicio, ignorar)
        indisponiveis = disponibilidade.get("motoristas", set()).union(
            disponibilidade.get("ajudantes", set())
        )
        if colaborador_id in indisponiveis:
            flash("Colaborador indisponível na data de início.", "error")
            return redirect(
                url_for(
                    "ferias",
                    edit_id=ferias_id,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                )
            )

        try:
            if ferias_id:
                svc.atualizar_ferias(ferias_id, colaborador_id, data_inicio, data_fim, observacao)
                flash("Férias atualizadas.", "success")
            else:
                svc.adicionar_ferias(colaborador_id, data_inicio, data_fim, observacao)
                flash("Férias salvas.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")
        return redirect(url_for("ferias"))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = None
    if edit_id:
        for item in svc.listar_ferias():
            if item.get("id") == edit_id:
                edit_item = item
                break

    registros = svc.listar_ferias()
    colaboradores = svc.listar_colaboradores(ativos_only=True)
    data_inicio_param = (request.args.get("data_inicio") or "").strip()
    data_fim_param = (request.args.get("data_fim") or "").strip()
    data_inicio_ref = edit_item["data_inicio"] if edit_item else data_inicio_param
    disponibilidade = svc.verificar_disponibilidade(
        data_inicio_ref, {"ferias_id": edit_id} if edit_id else None
    )

    return render_template(
        "ferias.html",
        registros=registros,
        edit_item=edit_item,
        colaboradores=colaboradores,
        disponibilidade=disponibilidade,
        data_inicio_param=data_inicio_param,
        data_fim_param=data_fim_param,
    )


@app.post("/ferias/<int:ferias_id>/excluir")
def excluir_ferias(ferias_id: int):
    try:
        svc.remover_ferias(ferias_id)
        flash("Férias excluídas.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("ferias"))

@app.route("/colaboradores", methods=["GET", "POST"])
def colaboradores():
    if request.method == "POST":
        colaborador_id = _int(request.form.get("colaborador_id"))
        nome = (request.form.get("nome") or "").strip()
        funcao = (request.form.get("funcao") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()
        ativo = (request.form.get("ativo") or "") == "on"

        if not nome or not funcao:
            flash("Informe nome e fun??o.", "error")
            return redirect(url_for("colaboradores"))

        try:
            if colaborador_id:
                atual = svc.obter_colaborador_por_id(colaborador_id) or {}
                svc.atualizar_colaborador(
                    colaborador_id,
                    nome,
                    funcao,
                    observacao,
                    atual.get("foto"),
                    ativo,
                )
                flash("Colaborador atualizado.", "success")
            else:
                svc.add_colaborador(nome, funcao, observacao, None)
                flash("Colaborador salvo.", "success")
        except Exception as exc:
            flash(f"Erro ao salvar: {exc}", "error")
        return redirect(url_for("colaboradores"))

    edit_id = _int(request.args.get("edit_id"))
    edit_item = None
    if edit_id:
        edit_item = svc.obter_colaborador_por_id(edit_id)

    registros = svc.listar_colaboradores(ativos_only=False)
    return render_template("colaboradores.html", registros=registros, edit_item=edit_item)


@app.post("/colaboradores/<int:colaborador_id>/desativar")
def desativar_colaborador(colaborador_id: int):
    try:
        svc.desativar_colaborador(colaborador_id)
        flash("Colaborador desativado.", "success")
    except Exception as exc:
        flash(f"Erro ao desativar: {exc}", "error")
    return redirect(url_for("colaboradores"))


@app.post("/colaboradores/<int:colaborador_id>/excluir")
def excluir_colaborador(colaborador_id: int):
    is_fetch = request.headers.get("X-Requested-With") == "fetch"
    try:
        foto_path = svc.excluir_colaborador(colaborador_id)
        if foto_path:
            foto_abs = UPLOAD_DIR / foto_path
            if foto_abs.exists():
                foto_abs.unlink()
        if is_fetch:
            total = len(svc.listar_colaboradores(ativos_only=False))
            return jsonify({"ok": True, "message": "Colaborador excluído.", "total": total})
        flash("Colaborador excluído.", "success")
    except Exception as exc:
        if is_fetch:
            return jsonify({"ok": False, "message": f"Erro ao excluir: {exc}"}), 400
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("colaboradores"))

@app.get("/log")
def log_view():
    filtros = {
        "data_inicio": (request.args.get("data_inicio") or "").strip() or None,
        "data_fim": (request.args.get("data_fim") or "").strip() or None,
        "status": (request.args.get("status") or "Em andamento").strip(),
        "motorista_id": _int(request.args.get("motorista_id")),
        "placa": (request.args.get("placa") or "").strip() or None,
    }
    registros = svc.consultar_log_carregamentos(filtros)
    motoristas = svc.listar_colaboradores_por_funcao("Motorista")
    ajudantes = svc.listar_colaboradores_por_funcao("Ajudante")
    ajudantes_ids = {a.get("id") for a in ajudantes}
    ajudantes = ajudantes + [
        {
            "id": m["id"],
            "nome": f"{m['nome']} {svc.MOTORISTA_AJUDANTE_TAG}",
            "foto": m.get("foto"),
            "mot_aj": True,
        }
        for m in motoristas
        if m.get("id") not in ajudantes_ids
    ]
    placas = [item.get("placa") for item in svc.listar_caminhoes(ativos_only=False)]

    return render_template(
        "log.html",
        filtros=filtros,
        registros=registros,
        motoristas=motoristas,
        ajudantes=ajudantes,
        placas=placas,
        query_args=request.args.to_dict(),
    )


@app.get("/log/export")
def log_export():
    filtros = {
        "data_inicio": (request.args.get("data_inicio") or "").strip() or None,
        "data_fim": (request.args.get("data_fim") or "").strip() or None,
        "status": (request.args.get("status") or "Em andamento").strip(),
        "motorista_id": _int(request.args.get("motorista_id")),
        "placa": (request.args.get("placa") or "").strip() or None,
    }
    registros = svc.consultar_log_carregamentos(filtros)
    caminho = exportar_log_para_excel(registros)
    return send_file(caminho, as_attachment=True)


@app.post("/log/<int:carregamento_id>/ajuste")
def log_ajuste(carregamento_id: int):
    duracao_nova = _int(request.form.get("duracao_nova"))
    observacao = (request.form.get("observacao") or "").strip() or None
    liberar_imediato = (request.form.get("liberar_imediato") or "") == "on"

    if duracao_nova is None:
        flash("Informe a nova duração.", "error")
        return redirect(url_for("log_view"))

    registro = svc.obter_carregamento(carregamento_id)
    if not registro:
        flash("Carregamento não encontrado.", "error")
        return redirect(url_for("log_view"))

    observacao_padrao = (registro.get("observacao") or "0").strip()
    duracao_planejada = svc.OBSERVACAO_DURACAO.get(observacao_padrao, 0)
    ajustes_map = svc.listar_ajustes_por_carregamentos([carregamento_id])
    ajustes = ajustes_map.get(carregamento_id, [])
    duracao_atual = ajustes[-1]["duracao_nova"] if ajustes else duracao_planejada

    try:
        svc.registrar_ajuste_rota(carregamento_id, duracao_atual, duracao_nova, observacao)
        data_inicio_iso = svc.obter_data_saida_registro(registro)
        inicio_dt = svc.parse_date(data_inicio_iso) or date.today()
        nova_data_fim = inicio_dt + timedelta(days=duracao_nova)
        svc.atualizar_bloqueios_para_ajuste(carregamento_id, nova_data_fim.isoformat(), liberar_imediato)
        flash("Ajuste registrado.", "success")
    except Exception as exc:
        flash(f"Erro ao registrar ajuste: {exc}", "error")

    return redirect(url_for("log_view"))


@app.post("/log/<int:carregamento_id>/colaboradores")
def log_colaboradores(carregamento_id: int):
    motorista_id = _int(request.form.get("motorista_id"))
    ajudante_id = _int(request.form.get("ajudante_id"))
    if motorista_id and ajudante_id and motorista_id == ajudante_id:
        flash("Motorista e ajudante devem ser pessoas diferentes.", "error")
        return redirect(url_for("log_view", **request.args.to_dict()))

    registro = svc.obter_carregamento(carregamento_id)
    if not registro:
        flash("Carregamento não encontrado.", "error")
        return redirect(url_for("log_view", **request.args.to_dict()))

    data_iso = (registro.get("data") or "").strip() or date.today().isoformat()
    data_base_iso = svc.obter_data_saida_registro(registro)
    disponibilidade = svc.verificar_disponibilidade(data_base_iso, {"carregamento_id": carregamento_id})
    indis_colaboradores = disponibilidade.get("motoristas", set()).union(
        disponibilidade.get("ajudantes", set())
    )
    if motorista_id and motorista_id in indis_colaboradores:
        flash("Motorista indisponível nesta data.", "error")
        return redirect(url_for("log_view", **request.args.to_dict()))
    if ajudante_id and ajudante_id in indis_colaboradores:
        flash("Ajudante indisponível nesta data.", "error")
        return redirect(url_for("log_view", **request.args.to_dict()))

    observacao = (registro.get("observacao") or "0").strip() or "0"
    try:
        svc.atualizar_carregamento(
            carregamento_id,
            data_iso,
            registro.get("data_saida"),
            registro.get("rota") or "",
            registro.get("placa"),
            motorista_id,
            ajudante_id,
            observacao,
            registro.get("observacao_extra"),
            registro.get("observacao_cor"),
        )
        svc.remover_bloqueios_por_carregamento(carregamento_id)
        svc.criar_bloqueios_para_carregamento(
            carregamento_id,
            data_iso,
            [motorista_id, ajudante_id],
            observacao,
        )
        flash("Colaboradores atualizados.", "success")
    except Exception as exc:
        flash(f"Erro ao atualizar colaboradores: {exc}", "error")

    return redirect(url_for("log_view", **request.args.to_dict()))


@app.post("/log/<int:carregamento_id>/liberar")
def log_liberar(carregamento_id: int):
    registro = svc.obter_carregamento(carregamento_id)
    if not registro:
        flash("Carregamento não encontrado.", "error")
        return redirect(url_for("log_view", **request.args.to_dict()))

    observacao_padrao = (registro.get("observacao") or "0").strip()
    duracao_planejada = svc.OBSERVACAO_DURACAO.get(observacao_padrao, 0)
    ajustes_map = svc.listar_ajustes_por_carregamentos([carregamento_id])
    ajustes = ajustes_map.get(carregamento_id, [])
    duracao_atual = ajustes[-1]["duracao_nova"] if ajustes else duracao_planejada

    try:
        svc.registrar_ajuste_rota(carregamento_id, duracao_atual, 0, "Liberado agora")
        data_inicio_iso = svc.obter_data_saida_registro(registro)
        inicio_dt = svc.parse_date(data_inicio_iso) or date.today()
        nova_data_fim = inicio_dt
        svc.atualizar_bloqueios_para_ajuste(
            carregamento_id,
            nova_data_fim.isoformat(),
            liberar_imediato=True,
        )
        flash("Carregamento liberado.", "success")
    except Exception as exc:
        flash(f"Erro ao liberar: {exc}", "error")
    return redirect(url_for("log_view", **request.args.to_dict()))


@app.post("/log/<int:carregamento_id>/excluir")
def log_excluir(carregamento_id: int):
    try:
        svc.remover_carregamento_completo(carregamento_id)
        flash("Carregamento excluído.", "success")
    except Exception as exc:
        flash(f"Erro ao excluir: {exc}", "error")
    return redirect(url_for("log_view", **request.args.to_dict()))


if __name__ == "__main__":
    app.run(debug=True, port=5000)

