from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
app = Flask(__name__)
app.secret_key = "auditoria-interna-2026"
DB = "auditoria.db"
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            titulo TEXT NOT NULL,
            escopo TEXT NOT NULL,
            auditor TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Planejamento',
            resumo TEXT,
            conclusao TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS criterios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL REFERENCES auditorias(id),
            descricao TEXT NOT NULL,
            fonte TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL REFERENCES auditorias(id),
            criterio_id INTEGER NOT NULL REFERENCES criterios(id),
            pergunta TEXT NOT NULL,
            resultado TEXT CHECK(resultado IN ('Conforme','NC','Oportunidade')),
            evidencia TEXT,
            avaliado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS nao_conformidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL REFERENCES auditorias(id),
            item_id INTEGER NOT NULL REFERENCES checklist(id),
            severidade TEXT NOT NULL DEFAULT 'Menor',
            descricao TEXT NOT NULL,
            evidencia TEXT,
            causa_raiz TEXT,
            impacto TEXT,
            aberta_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS planos_acao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL REFERENCES auditorias(id),
            nc_id INTEGER NOT NULL REFERENCES nao_conformidades(id),
            acao TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            prazo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aberto',
            verificacao TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS log_operacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            operacao TEXT NOT NULL,
            entidade TEXT,
            detalhe TEXT
        );
    """)
    conn.commit()
    conn.close()


def _log(op, entidade="", detalhe=""):
    conn = _conn()
    conn.execute(
        "INSERT INTO log_operacoes (timestamp, operacao, entidade, detalhe) VALUES (?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), op, entidade, detalhe),
    )
    conn.commit()
    conn.close()


# ── Rotas ──────────────────────────────────────────────

@app.route("/")
def dashboard():
    conn = _conn()
    stats = {
        "auditorias": conn.execute("SELECT COUNT(*) FROM auditorias").fetchone()[0],
        "ncs": conn.execute("SELECT COUNT(*) FROM nao_conformidades").fetchone()[0],
        "ncs_maior": conn.execute("SELECT COUNT(*) FROM nao_conformidades WHERE severidade='Maior'").fetchone()[0],
        "planos_abertos": conn.execute("SELECT COUNT(*) FROM planos_acao WHERE status IN ('Aberto','Em andamento')").fetchone()[0],
        "auditorias_ativas": conn.execute("SELECT COUNT(*) FROM auditorias WHERE status != 'Concluída'").fetchone()[0],
    }
    recentes = conn.execute("SELECT * FROM auditorias ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, recentes=recentes)


@app.route("/auditorias")
def listar_auditorias():
    conn = _conn()
    rows = conn.execute("SELECT * FROM auditorias ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("auditorias.html", auditorias=rows)


@app.route("/auditorias/nova", methods=["GET", "POST"])
def nova_auditoria():
    if request.method == "POST":
        titulo = request.form["titulo"].strip()
        escopo = request.form["escopo"].strip()
        auditor = request.form["auditor"].strip()
        di = request.form["data_inicio"]
        df = request.form["data_fim"]
        if not all([titulo, escopo, auditor, di, df]):
            flash("Todos os campos são obrigatórios.", "error")
            return render_template("nova_auditoria.html")
        conn = _conn()
        ultimo = conn.execute("SELECT MAX(id) FROM auditorias").fetchone()[0] or 0
        codigo = f"AUD-{datetime.now().year}-{ultimo + 1:03d}"
        cur = conn.execute(
            "INSERT INTO auditorias (codigo, titulo, escopo, auditor, data_inicio, data_fim, criado_em) VALUES (?,?,?,?,?,?,?)",
            (codigo, titulo, escopo, auditor, di, df, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        aid = cur.lastrowid
        conn.commit()
        conn.close()
        _log("CRIAR_AUDITORIA", codigo, titulo)
        flash(f"Auditoria {codigo} criada.", "success")
        return redirect(url_for("detalhe_auditoria", aid=aid))
    return render_template("nova_auditoria.html")


@app.route("/auditorias/<int:aid>")
def detalhe_auditoria(aid):
    conn = _conn()
    aud = conn.execute("SELECT * FROM auditorias WHERE id=?", (aid,)).fetchone()
    if not aud:
        flash("Auditoria não encontrada.", "error")
        return redirect(url_for("listar_auditorias"))
    itens = conn.execute("SELECT * FROM checklist WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    ncs = conn.execute("SELECT * FROM nao_conformidades WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    planos = conn.execute("SELECT * FROM planos_acao WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    criterios = conn.execute("SELECT * FROM criterios WHERE auditoria_id=?", (aid,)).fetchall()
    conn.close()
    return render_template("detalhe_auditoria.html", aud=aud, itens=itens, ncs=ncs, planos=planos, criterios=criterios)


@app.route("/auditorias/<int:aid>/criterio", methods=["POST"])
def add_criterio(aid):
    desc = request.form["descricao"].strip()
    fonte = request.form["fonte"].strip()
    if not desc or not fonte:
        flash("Preencha todos os campos.", "error")
        return redirect(url_for("detalhe_auditoria", aid=aid))
    conn = _conn()
    conn.execute("INSERT INTO criterios (auditoria_id, descricao, fonte) VALUES (?,?,?)", (aid, desc, fonte))
    conn.commit()
    conn.close()
    _log("ADICIONAR_CRITERIO", f"AUD-{aid}", desc)
    flash("Critério adicionado.", "success")
    return redirect(url_for("detalhe_auditoria", aid=aid))


@app.route("/auditorias/<int:aid>/item", methods=["POST"])
def add_item(aid):
    cid = int(request.form["criterio_id"])
    pergunta = request.form["pergunta"].strip()
    if not pergunta:
        flash("Pergunta obrigatória.", "error")
        return redirect(url_for("detalhe_auditoria", aid=aid))
    conn = _conn()
    conn.execute("INSERT INTO checklist (auditoria_id, criterio_id, pergunta) VALUES (?,?,?)", (aid, cid, pergunta))
    conn.commit()
    conn.close()
    _log("ADICIONAR_ITEM", f"AUD-{aid}", pergunta)
    flash("Item adicionado.", "success")
    return redirect(url_for("detalhe_auditoria", aid=aid))


@app.route("/checklist/<int:iid>/resultado", methods=["POST"])
def registrar_resultado(iid):
    resultado = request.form["resultado"]
    evidencia = request.form.get("evidencia", "").strip()
    conn = _conn()
    item = conn.execute("SELECT * FROM checklist WHERE id=?", (iid,)).fetchone()
    if not item:
        flash("Item não encontrado.", "error")
        return redirect(url_for("dashboard"))
    conn.execute(
        "UPDATE checklist SET resultado=?, evidencia=?, avaliado_em=? WHERE id=?",
        (resultado, evidencia, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), iid),
    )
    if resultado == "NC":
        conn.execute(
            "INSERT INTO nao_conformidades (auditoria_id, item_id, severidade, descricao, evidencia, aberta_em) VALUES (?,?,?,?,?,?)",
            (item["auditoria_id"], iid, "Menor", item["pergunta"], evidencia,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    conn.commit()
    conn.close()
    _log("REGISTRAR_RESULTADO", f"Item-{iid}", resultado)
    flash(f"Resultado registrado: {resultado}", "success")
    return redirect(url_for("detalhe_auditoria", aid=item["auditoria_id"]))


@app.route("/nc/<int:ncid>/classificar", methods=["POST"])
def classificar_nc(ncid):
    sev = request.form["severidade"]
    causa = request.form.get("causa_raiz", "").strip()
    impacto = request.form["impacto"].strip()
    conn = _conn()
    conn.execute(
        "UPDATE nao_conformidades SET severidade=?, causa_raiz=?, impacto=? WHERE id=?",
        (sev, causa, impacto, ncid),
    )
    conn.commit()
    conn.close()
    _log("CLASSIFICAR_NC", f"NC-{ncid}", f"{sev} | {impacto}")
    flash("NC classificada.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/plano", methods=["POST"])
def criar_plano():
    aid = int(request.form["auditoria_id"])
    ncid = int(request.form["nc_id"])
    acao = request.form["acao"].strip()
    resp = request.form["responsavel"].strip()
    prazo = request.form["prazo"]
    conn = _conn()
    conn.execute(
        "INSERT INTO planos_acao (auditoria_id, nc_id, acao, responsavel, prazo, criado_em) VALUES (?,?,?,?,?,?)",
        (aid, ncid, acao, resp, prazo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()
    _log("CRIAR_PLANO", f"NC-{ncid}", f"→ {resp}")
    flash("Plano de ação criado.", "success")
    return redirect(url_for("detalhe_auditoria", aid=aid))


@app.route("/plano/<int:pid>/status", methods=["POST"])
def atualizar_plano(pid):
    status = request.form["status"]
    verif = request.form.get("verificacao", "").strip()
    conn = _conn()
    conn.execute("UPDATE planos_acao SET status=?, verificacao=? WHERE id=?", (status, verif, pid))
    conn.commit()
    conn.close()
    _log("ATUALIZAR_PLANO", f"PA-{pid}", status)
    flash(f"Plano → {status}", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/auditorias/<int:aid>/finalizar", methods=["POST"])
def finalizar(aid):
    resumo = request.form["resumo"].strip()
    conclusao = request.form["conclusao"].strip()
    conn = _conn()
    pendentes = conn.execute(
        "SELECT COUNT(*) FROM checklist WHERE auditoria_id=? AND resultado IS NULL", (aid,)
    ).fetchone()[0]
    if pendentes:
        flash(f"Não é possível finalizar: {pendentes} item(ns) pendente(s).", "error")
        return redirect(url_for("detalhe_auditoria", aid=aid))
    conn.execute("UPDATE auditorias SET status='Concluída', resumo=?, conclusao=? WHERE id=?",
                 (resumo, conclusao, aid))
    conn.commit()
    conn.close()
    _log("FINALIZAR", f"AUD-{aid}", conclusao[:50])
    flash("Auditoria finalizada.", "success")
    return redirect(url_for("detalhe_auditoria", aid=aid))


@app.route("/log")
def ver_log():
    conn = _conn()
    rows = conn.execute("SELECT * FROM log_operacoes ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("log.html", logs=rows)


# ── Inicialização ──────────────────────────────────────
init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)   