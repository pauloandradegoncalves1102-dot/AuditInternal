import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime
from typing import Optional


# ─────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────

DB_NAME = "auditoria.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            escopo TEXT NOT NULL,
            auditor TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            resumo_executivo TEXT,
            conclusao TEXT
        );

        CREATE TABLE IF NOT EXISTS criterios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            fonte TEXT NOT NULL,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias(id)
        );

        CREATE TABLE IF NOT EXISTS checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL,
            criterio_id INTEGER NOT NULL,
            pergunta TEXT NOT NULL,
            resultado TEXT,
            evidencia TEXT,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias(id),
            FOREIGN KEY (criterio_id) REFERENCES criterios(id)
        );

        CREATE TABLE IF NOT EXISTS nao_conformidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL,
            checklist_item_id INTEGER NOT NULL,
            severidade TEXT NOT NULL,
            descricao TEXT NOT NULL,
            evidencia TEXT,
            impacto TEXT,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias(id),
            FOREIGN KEY (checklist_item_id) REFERENCES checklist(id)
        );

        CREATE TABLE IF NOT EXISTS planos_acao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL,
            nc_id INTEGER NOT NULL,
            acao TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            prazo TEXT NOT NULL,
            status TEXT DEFAULT 'Aberto',
            verificacao TEXT,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias(id),
            FOREIGN KEY (nc_id) REFERENCES nao_conformidades(id)
        );

        CREATE TABLE IF NOT EXISTS log_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            acao TEXT NOT NULL,
            detalhes TEXT
        );
    """)
    conn.commit()
    conn.close()


def log(acao: str, detalhes: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO log_auditoria (timestamp, acao, detalhes) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), acao, detalhes),
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# OPERAÇÕES
# ─────────────────────────────────────────────

def criar_auditoria(titulo, escopo, auditor, data_inicio, data_fim):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO auditorias (titulo, escopo, auditor, data_inicio, data_fim) VALUES (?,?,?,?,?)",
        (titulo, escopo, auditor, data_inicio, data_fim),
    )
    aud_id = cur.lastrowid
    conn.commit()
    conn.close()
    log("CRIAR_AUDITORIA", f"#{aud_id} {titulo}")
    return aud_id


def adicionar_criterio(auditoria_id, descricao, fonte):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO criterios (auditoria_id, descricao, fonte) VALUES (?,?,?)",
        (auditoria_id, descricao, fonte),
    )
    crit_id = cur.lastrowid
    conn.commit()
    conn.close()
    log("ADICIONAR_CRITERIO", f"Auditoria #{auditoria_id}: {descricao}")
    return crit_id


def adicionar_item_checklist(auditoria_id, criterio_id, pergunta):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO checklist (auditoria_id, criterio_id, pergunta) VALUES (?,?,?)",
        (auditoria_id, criterio_id, pergunta),
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    log("ADICIONAR_ITEM", f"Auditoria #{auditoria_id}, item #{item_id}: {pergunta}")
    return item_id


def registrar_resultado(item_id, resultado, evidencia=""):
    conn = get_conn()
    conn.execute(
        "UPDATE checklist SET resultado=?, evidencia=? WHERE id=?",
        (resultado, evidencia, item_id),
    )
    conn.commit()
    conn.close()
    log("REGISTRAR_RESULTADO", f"Item #{item_id}: {resultado}")

    if resultado == "NC":
        conn = get_conn()
        row = conn.execute("SELECT * FROM checklist WHERE id=?", (item_id,)).fetchone()
        conn.execute(
            "INSERT INTO nao_conformidades (auditoria_id, checklist_item_id, severidade, descricao, evidencia, impacto) VALUES (?,?,?,?,?,?)",
            (row["auditoria_id"], item_id, "Menor", row["pergunta"], evidencia, "A definir"),
        )
        nc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        log("CRIAR_NC", f"NC #{nc_id} gerada do item #{item_id}")
        return nc_id
    return None


def classificar_nc(nc_id, severidade, impacto):
    conn = get_conn()
    conn.execute(
        "UPDATE nao_conformidades SET severidade=?, impacto=? WHERE id=?",
        (severidade, impacto, nc_id),
    )
    conn.commit()
    conn.close()
    log("CLASSIFICAR_NC", f"NC #{nc_id} → {severidade} | {impacto}")


def criar_plano_acao(auditoria_id, nc_id, acao, responsavel, prazo):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO planos_acao (auditoria_id, nc_id, acao, responsavel, prazo) VALUES (?,?,?,?,?)",
        (auditoria_id, nc_id, acao, responsavel, prazo),
    )
    plano_id = cur.lastrowid
    conn.commit()
    conn.close()
    log("CRIAR_PLANO", f"Plano #{plano_id} para NC #{nc_id}")
    return plano_id


def atualizar_plano(plano_id, status, verificacao=""):
    conn = get_conn()
    conn.execute(
        "UPDATE planos_acao SET status=?, verificacao=? WHERE id=?",
        (status, verificacao, plano_id),
    )
    conn.commit()
    conn.close()
    log("ATUALIZAR_PLANO", f"Plano #{plano_id} → {status}")


def gerar_relatorio(auditoria_id):
    conn = get_conn()
    aud = conn.execute("SELECT * FROM auditorias WHERE id=?", (auditoria_id,)).fetchone()
    itens = conn.execute("SELECT * FROM checklist WHERE auditoria_id=?", (auditoria_id,)).fetchall()
    ncs = conn.execute("SELECT * FROM nao_conformidades WHERE auditoria_id=?", (auditoria_id,)).fetchall()
    planos = conn.execute("SELECT * FROM planos_acao WHERE auditoria_id=?", (auditoria_id,)).fetchall()
    conn.close()

    linhas = [
        "=" * 60,
        f"RELATÓRIO DE AUDITORIA INTERNA #{auditoria_id}",
        "=" * 60,
        f"Título:  {aud['titulo']}",
        f"Escopo:  {aud['escopo']}",
        f"Auditor: {aud['auditor']}",
        f"Período: {aud['data_inicio']} a {aud['data_fim']}",
        "-" * 60,
        f"CHECKLIST ({len(itens)} itens)",
    ]
    for it in itens:
        linhas.append(f"  [{it['id']}] {it['resultado'] or 'Pendente':15s} | {it['pergunta']}")

    linhas.append("-" * 60)
    linhas.append(f"NAO CONFORMIDADES ({len(ncs)})")
    for nc in ncs:
        linhas.append(f"  NC-{nc['id']} [{nc['severidade']}] {nc['descricao']}")
        linhas.append(f"       Evidência: {nc['evidencia']}  |  Impacto: {nc['impacto']}")

    linhas.append("-" * 60)
    linhas.append(f"PLANOS DE AÇÃO ({len(planos)})")
    for p in planos:
        linhas.append(f"  PA-{p['id']} [{p['status']}] {p['acao']} → {p['responsavel']} até {p['prazo']}")

    linhas.append("=" * 60)
    log("GERAR_RELATORIO", f"Auditoria #{auditoria_id}")
    return "\n".join(linhas)


def listar_auditorias():
    conn = get_conn()
    rows = conn.execute("SELECT id, titulo, auditor, data_inicio, data_fim FROM auditorias ORDER BY id").fetchall()
    conn.close()
    if not rows:
        return "  (nenhuma auditoria cadastrada)"
    linhas = [f"  {'ID':<4} {'Título':<35} {'Auditor':<15} {'Início':<12} {'Fim'}"]
    for r in rows:
        linhas.append(f"  {r['id']:<4} {r['titulo']:<35} {r['auditor']:<15} {r['data_inicio']:<12} {r['data_fim']}")
    return "\n".join(linhas)


def ver_log(n=20):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM log_auditoria ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    conn.close()
    if not rows:
        return "  (log vazio)"
    linhas = []
    for r in rows:
        linhas.append(f"  [{r['timestamp']}] {r['acao']}: {r['detalhes']}")
    return "\n".join(linhas)


# ─────────────────────────────────────────────
# INTERFACE INTERATIVA
# ─────────────────────────────────────────────

MENU = """
╔══════════════════════════════════════════╗
║   SISTEMA DE AUDITORIA INTERNA           ║
╠══════════════════════════════════════════╣
║  1. Nova auditoria                       ║
║  2. Adicionar critério                   ║
║  3. Adicionar item de checklist          ║
║  4. Registrar resultado                  ║
║  5. Classificar NC                       ║
║  6. Criar plano de ação                  ║
║  7. Atualizar plano de ação              ║
║  8. Gerar relatório                      ║
║  9. Listar auditorias                    ║
║ 10. Ver log de operações                 ║
║  0. Sair                                 ║
╚══════════════════════════════════════════╝
"""


def prompt_int(msg, default=None):
    val = input(msg).strip()
    if not val and default is not None:
        return default
    return val


def main():
    init_db()
    print("Banco de dados inicializado: " + DB_NAME)

    while True:
        print(MENU)
        op = input("Escolha uma opção: ").strip()

        if op == "1":
            titulo = prompt_int("Título: ")
            escopo = prompt_int("Escopo: ")
            auditor = prompt_int("Auditor: ")
            di = prompt_int("Data início (AAAA-MM-DD): ")
            df = prompt_int("Data fim (AAAA-MM-DD): ")
            aud_id = criar_auditoria(titulo, escopo, auditor, di, df)
            print(f"  ✓ Auditoria #{aud_id} criada.")

        elif op == "2":
            aid = int(prompt_int("Auditoria ID: "))
            desc = prompt_int("Descrição: ")
            fonte = prompt_int("Fonte (norma/política/lei): ")
            cid = adicionar_criterio(aid, desc, fonte)
            print(f"  ✓ Critério #{cid} adicionado.")

        elif op == "3":
            aid = int(prompt_int("Auditoria ID: "))
            cid = int(prompt_int("Critério ID: "))
            pergunta = prompt_int("Pergunta: ")
            iid = adicionar_item_checklist(aid, cid, pergunta)
            print(f"  ✓ Item #{iid} adicionado ao checklist.")

        elif op == "4":
            iid = int(prompt_int("Item de checklist ID: "))
            resultado = prompt_int("Resultado (Conforme / NC / Oportunidade): ")
            evidencia = prompt_int("Evidência: ", default="")
            nc_id = registrar_resultado(iid, resultado, evidencia)
            if nc_id:
                print(f"  ✓ NC #{nc_id} gerada automaticamente.")
            else:
                print(f"  ✓ Item #{iid} atualizado.")

        elif op == "5":
            nc_id = int(prompt_int("NC ID: "))
            sev = prompt_int("Severidade (Maior/Menor/Observação): ")
            impacto = prompt_int("Impacto: ")
            classificar_nc(nc_id, sev, impacto)
            print(f"  ✓ NC #{nc_id} classificada.")

        elif op == "6":
            aid = int(prompt_int("Auditoria ID: "))
            nc_id = int(prompt_int("NC ID: "))
            acao = prompt_int("Ação corretiva: ")
            resp = prompt_int("Responsável: ")
            prazo = prompt_int("Prazo (AAAA-MM-DD): ")
            pid = criar_plano_acao(aid, nc_id, acao, resp, prazo)
            print(f"  ✓ Plano de ação #{pid} criado.")

        elif op == "7":
            pid = int(prompt_int("Plano de ação ID: "))
            status = prompt_int("Novo status (Aberto/Em andamento/Concluído/Verificado): ")
            verif = prompt_int("Verificação: ", default="")
            atualizar_plano(pid, status, verif)
            print(f"  ✓ Plano #{pid} atualizado.")

        elif op == "8":
            aid = int(prompt_int("Auditoria ID: "))
            print("\n" + gerar_relatorio(aid))

        elif op == "9":
            print("\n" + listar_auditorias())

        elif op == "10":
            print("\n" + ver_log())

        elif op == "0":
            print("Até logo.")
            break

        else:
            print("  Opção inválida.")


if __name__ == "__main__":
    main()   