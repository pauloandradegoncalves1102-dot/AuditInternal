import sqlite3
import sys
from datetime import datetime, date
from typing import Optional

DB_PATH = "auditoria.db"
VALID_RESULTADOS = ("Conforme", "NC", "Oportunidade")
VALID_SEVERIDADES = ("Maior", "Menor", "Observação")
VALID_STATUS = ("Aberto", "Em andamento", "Concluído", "Verificado")

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c
def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auditorias (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo          TEXT UNIQUE NOT NULL,
            titulo          TEXT NOT NULL,
            escopo          TEXT NOT NULL,
            auditor         TEXT NOT NULL,
            data_inicio     TEXT NOT NULL,
            data_fim        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Planejamento',
            resumo          TEXT,
            conclusao       TEXT,
            criado_em       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS criterios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id    INTEGER NOT NULL REFERENCES auditorias(id),
            descricao       TEXT NOT NULL,
            fonte           TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checklist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id    INTEGER NOT NULL REFERENCES auditorias(id),
            criterio_id     INTEGER NOT NULL REFERENCES criterios(id),
            pergunta        TEXT NOT NULL,
            resultado       TEXT CHECK(resultado IN ('Conforme','NC','Oportunidade')),
            evidencia       TEXT,
            avaliado_em     TEXT
        );
        CREATE TABLE IF NOT EXISTS nao_conformidades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id    INTEGER NOT NULL REFERENCES auditorias(id),
            item_id         INTEGER NOT NULL REFERENCES checklist(id),
            severidade      TEXT NOT NULL CHECK(severidade IN ('Maior','Menor','Observação')),
            descricao       TEXT NOT NULL,
            evidencia       TEXT,
            causa_raiz      TEXT,
            impacto         TEXT,
            aberta_em       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS planos_acao (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id    INTEGER NOT NULL REFERENCES auditorias(id),
            nc_id           INTEGER NOT NULL REFERENCES nao_conformidades(id),
            acao            TEXT NOT NULL,
            responsavel     TEXT NOT NULL,
            prazo           TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Aberto'
                            CHECK(status IN ('Aberto','Em andamento','Concluído','Verificado')),
            verificacao     TEXT,
            criado_em       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS log_operacoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            operacao        TEXT NOT NULL,
            entidade        TEXT,
            detalhe         TEXT
        );
    """)
    conn.commit()
    conn.close()
def _log(operacao: str, entidade: str = "", detalhe: str = ""):
    conn = _conn()
    conn.execute(
        "INSERT INTO log_operacoes (timestamp, operacao, entidade, detalhe) VALUES (?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), operacao, entidade, detalhe),
    )
    conn.commit()
    conn.close()
class ValidacaoError(Exception):
    pass
def validar_data(s: str) -> str:
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return d.isoformat()
    except ValueError:
        raise ValidacaoError(f"Data inválida: '{s}'. Use o formato AAAA-MM-DD.")
def validar_id(s: str, entidade: str) -> int:
    try:
        v = int(s)
        if v < 1:
            raise ValidacaoError(f"ID deve ser positivo.")
        return v
    except ValueError:
        raise ValidacaoError(f"ID inválido para {entidade}: '{s}'.")
def validar_enum(s: str, opcoes: tuple, campo: str) -> str:
    for o in opcoes:
        if s.lower() == o.lower():
            return o
    raise ValidacaoError(f"{campo} inválido: '{s}'. Opções: {', '.join(opcoes)}")
def validar_nao_vazio(s: str, campo: str) -> str:
    s = s.strip()
    if not s:
        raise ValidacaoError(f"Campo obrigatório: {campo}.")
    return s

def criar_auditoria(titulo, escopo, auditor, data_inicio, data_fim) -> int:
    data_inicio = validar_data(data_inicio)
    data_fim = validar_data(data_fim)
    if data_fim <= data_inicio:
        raise ValidacaoError("Data fim deve ser posterior à data início.")
    conn = _conn()
    ultimo = conn.execute("SELECT MAX(id) as m FROM auditorias").fetchone()["m"] or 0
    codigo = f"AUD-{datetime.now().year}-{ultimo + 1:03d}"
    cur = conn.execute(
        "INSERT INTO auditorias (codigo, titulo, escopo, auditor, data_inicio, data_fim, criado_em) "
        "VALUES (?,?,?,?,?,?,?)",
        (codigo, titulo, escopo, auditor, data_inicio, data_fim,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    _log("CRIAR_AUDITORIA", codigo, f"{titulo} | {auditor}")
    return aid
def adicionar_criterio(auditoria_id, descricao, fonte) -> int:
    _verificar_auditoria(auditoria_id)
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO criterios (auditoria_id, descricao, fonte) VALUES (?,?,?)",
        (auditoria_id, descricao, fonte),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    _log("ADICIONAR_CRITERIO", f"AUD-{auditoria_id}", descricao)
    return cid
def adicionar_item(auditoria_id, criterio_id, pergunta) -> int:
    _verificar_auditoria(auditoria_id)
    conn = _conn()
    crit = conn.execute("SELECT id FROM criterios WHERE id=? AND auditoria_id=?",
                        (criterio_id, auditoria_id)).fetchone()
    if not crit:
        conn.close()
        raise ValidacaoError(f"Critério #{criterio_id} não pertence à auditoria #{auditoria_id}.")
    cur = conn.execute(
        "INSERT INTO checklist (auditoria_id, criterio_id, pergunta) VALUES (?,?,?)",
        (auditoria_id, criterio_id, pergunta),
    )
    iid = cur.lastrowid
    conn.commit()
    conn.close()
    _log("ADICIONAR_ITEM", f"AUD-{auditoria_id}", f"Item #{iid}")
    return iid
def registrar_resultado(item_id, resultado, evidencia) -> Optional[int]:
    resultado = validar_enum(resultado, VALID_RESULTADOS, "Resultado")
    conn = _conn()
    item = conn.execute("SELECT * FROM checklist WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        raise ValidacaoError(f"Item de checklist #{item_id} não encontrado.")
    conn.execute(
        "UPDATE checklist SET resultado=?, evidencia=?, avaliado_em=? WHERE id=?",
        (resultado, evidencia, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_id),
    )
    conn.commit()
    _log("REGISTRAR_RESULTADO", f"Item-{item_id}", resultado)

    nc_id = None
    if resultado == "NC":
        cur = conn.execute(
            "INSERT INTO nao_conformidades (auditoria_id, item_id, severidade, descricao, evidencia, aberta_em) "
            "VALUES (?,?,?,?,?,?)",
            (item["auditoria_id"], item_id, "Menor", item["pergunta"], evidencia,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        nc_id = cur.lastrowid
        conn.commit()
        _log("GERAR_NC", f"NC-{nc_id}", f"Origem: item #{item_id}")
    conn.close()
    return nc_id
def classificar_nc(nc_id, severidade, causa_raiz, impacto):
    severidade = validar_enum(severidade, VALID_SEVERIDADES, "Severidade")
    conn = _conn()
    nc = conn.execute("SELECT id FROM nao_conformidades WHERE id=?", (nc_id,)).fetchone()
    if not nc:
        conn.close()
        raise ValidacaoError(f"NC #{nc_id} não encontrada.")
    conn.execute(
        "UPDATE nao_conformidades SET severidade=?, causa_raiz=?, impacto=? WHERE id=?",
        (severidade, causa_raiz, impacto, nc_id),
    )
    conn.commit()
    conn.close()
    _log("CLASSIFICAR_NC", f"NC-{nc_id}", f"{severidade} | {impacto}")
def criar_plano(auditoria_id, nc_id, acao, responsavel, prazo):
    prazo = validar_data(prazo)
    conn = _conn()
    nc = conn.execute("SELECT id FROM nao_conformidades WHERE id=? AND auditoria_id=?",
                      (nc_id, auditoria_id)).fetchone()
    if not nc:
        conn.close()
        raise ValidacaoError(f"NC #{nc_id} não pertence à auditoria #{auditoria_id}.")
    cur = conn.execute(
        "INSERT INTO planos_acao (auditoria_id, nc_id, acao, responsavel, prazo, criado_em) "
        "VALUES (?,?,?,?,?,?)",
        (auditoria_id, nc_id, acao, responsavel, prazo,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    _log("CRIAR_PLANO", f"PA-{pid}", f"NC-{nc_id} → {responsavel}")
    return pid
def atualizar_plano(plano_id, status, verificacao=""):
    status = validar_enum(status, VALID_STATUS, "Status")
    conn = _conn()
    p = conn.execute("SELECT id FROM planos_acao WHERE id=?", (plano_id,)).fetchone()
    if not p:
        conn.close()
        raise ValidacaoError(f"Plano de ação #{plano_id} não encontrado.")
    conn.execute(
        "UPDATE planos_acao SET status=?, verificacao=? WHERE id=?",
        (status, verificacao, plano_id),
    )
    conn.commit()
    conn.close()
    _log("ATUALIZAR_PLANO", f"PA-{plano_id}", status)
def finalizar_auditoria(auditoria_id, resumo, conclusao):
    conn = _conn()
    aud = conn.execute("SELECT id FROM auditorias WHERE id=?", (auditoria_id,)).fetchone()
    if not aud:
        conn.close()
        raise ValidacaoError(f"Auditoria #{auditoria_id} não encontrada.")
    pendentes = conn.execute(
        "SELECT COUNT(*) as c FROM checklist WHERE auditoria_id=? AND resultado IS NULL",
        (auditoria_id,),
    ).fetchone()["c"]
    if pendentes > 0:
        conn.close()
        raise ValidacaoError(f"Não é possível finalizar: {pendentes} item(ns) sem resultado.")
    conn.execute(
        "UPDATE auditorias SET status='Concluída', resumo=?, conclusao=? WHERE id=?",
        (resumo, conclusao, auditoria_id),
    )
    conn.commit()
    conn.close()
    _log("FINALIZAR_AUDITORIA", f"AUD-{auditoria_id}", conclusao[:50])
def _verificar_auditoria(aid: int):
    conn = _conn()
    r = conn.execute("SELECT id FROM auditorias WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not r:
        raise ValidacaoError(f"Auditoria #{aid} não encontrada.")
def listar_auditorias():
    conn = _conn()
    rows = conn.execute(
        "SELECT id, codigo, titulo, auditor, data_inicio, data_fim, status FROM auditorias ORDER BY id"
    ).fetchall()
    conn.close()
    if not rows:
        return "Nenhuma auditoria registrada."
    hdr = f"{'ID':<4} {'Código':<12} {'Título':<30} {'Auditor':<15} {'Início':<12} {'Fim':<12} {'Status'}"
    linhas = [hdr, "─" * len(hdr)]
    for r in rows:
        linhas.append(
            f"{r['id']:<4} {r['codigo']:<12} {r['titulo']:<30} {r['auditor']:<15} "
            f"{r['data_inicio']:<12} {r['data_fim']:<12} {r['status']}"
        )
    return "\n".join(linhas)
def detalhar_auditoria(aid):
    conn = _conn()
    aud = conn.execute("SELECT * FROM auditorias WHERE id=?", (aid,)).fetchone()
    if not aud:
        conn.close()
        raise ValidacaoError(f"Auditoria #{aid} não encontrada.")
    itens = conn.execute("SELECT * FROM checklist WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    ncs = conn.execute("SELECT * FROM nao_conformidades WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    planos = conn.execute("SELECT * FROM planos_acao WHERE auditoria_id=? ORDER BY id", (aid,)).fetchall()
    conn.close()
    L = []
    L.append("─" * 64)
    L.append(f"  {aud['codigo']}  |  {aud['titulo']}")
    L.append(f"  Escopo:     {aud['escopo']}")
    L.append(f"  Auditor:    {aud['auditor']}")
    L.append(f"  Período:    {aud['data_inicio']} a {aud['data_fim']}")
    L.append(f"  Status:     {aud['status']}")
    L.append("─" * 64)
    L.append(f"\n  CHECKLIST ({len(itens)} itens)")
    for it in itens:
        st = it["resultado"] or "PENDENTE"
        L.append(f"    [{it['id']:>2}] {st:<15} {it['pergunta']}")
    L.append(f"\n  NÃO CONFORMIDADES ({len(ncs)})")
    for nc in ncs:
        L.append(f"    NC-{nc['id']}  [{nc['severidade']}]  {nc['descricao']}")
        L.append(f"           Evidência: {nc['evidencia']}")
        if nc["causa_raiz"]:
            L.append(f"           Causa raiz: {nc['causa_raiz']}")
        if nc["impacto"]:
            L.append(f"           Impacto: {nc['impacto']}")
    L.append(f"\n  PLANOS DE AÇÃO ({len(planos)})")
    for p in planos:
        L.append(f"    PA-{p['id']}  [{p['status']}]  {p['acao']}")
        L.append(f"           Responsável: {p['responsavel']}  |  Prazo: {p['prazo']}")
    if aud["resumo"]:
        L.append(f"\n  RESUMO: {aud['resumo']}")
    if aud["conclusao"]:
        L.append(f"  CONCLUSÃO: {aud['conclusao']}")
    L.append("─" * 64)
    return "\n".join(L)
def ver_log(n=25):
    conn = _conn()
    rows = conn.execute(
        "SELECT timestamp, operacao, entidade, detalhe FROM log_operacoes ORDER BY id DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()
    if not rows:
        return "Log vazio."
    hdr = f"{'Horário':<20} {'Operação':<22} {'Entidade':<12} Detalhe"
    linhas = [hdr, "─" * 70]
    for r in rows:
        linhas.append(f"{r['timestamp']:<20} {r['operacao']:<22} {r['entidade']:<12} {r['detalhe']}")
    return "\n".join(linhas)
def _input(msg: str, obrigatorio: bool = True, default: str = "") -> str:
    sufixo = " [obrigatório]" if obrigatorio else " [opcional]"
    hint = f" (padrão: {default})" if default and not obrigatorio else ""
    val = input(f"  {msg}{sufixo}{hint}: ").strip()
    if not val:
        if default:
            return default
        if obrigatorio:
            raise ValidacaoError(f"Campo obrigatório: {msg}")
        return ""
    return val
def _input_id(msg: str) -> int:
    return validar_id(_input(msg), msg)
def _input_data(msg: str) -> str:
    return validar_data(_input(msg))
MENU = """
┌──────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE AUDITORIA INTERNA                   │
├──────────────────────────────────────────────────────────────────┤
│  [1]  Nova auditoria                                             │
│  [2]  Adicionar critério                                         │
│  [3]  Adicionar item de checklist                                │
│  [4]  Registrar resultado                                        │
│  [5]  Classificar não conformidade                               │
│  [6]  Criar plano de ação                                        │
│  [7]  Atualizar plano de ação                                    │
│  [8]  Finalizar auditoria                                        │
│  [9]  Listar auditorias                                          │
│  [10] Detalhar auditoria                                         │
│  [11] Ver log de operações                                       │
│  [0]  Sair                                                       │
└──────────────────────────────────────────────────────────────────┘
"""


def main():
    init_db()
    print(f"\n  Sistema de Auditoria Interna — Banco: {DB_PATH}\n")

    while True:
        print(MENU)
        op = input("  Opção: ").strip()

        try:
            if op == "1":
                print("\n  ── NOVA AUDITORIA ──")
                titulo = _input("Título")
                escopo = _input("Escopo / área")
                auditor = _input("Auditor responsável")
                di = _input_data("Data de início (AAAA-MM-DD)")
                df = _input_data("Data de término (AAAA-MM-DD)")
                aid = criar_auditoria(titulo, escopo, auditor, di, df)
                print(f"\n  Auditoria #{aid} criada com sucesso.")

            elif op == "2":
                print("\n  ── ADICIONAR CRITÉRIO ──")
                aid = _input_id("Auditoria ID")
                desc = _input("Descrição do critério")
                fonte = _input("Fonte (norma / política / lei)")
                cid = adicionar_criterio(aid, desc, fonte)
                print(f"\n  Critério #{cid} adicionado.")

            elif op == "3":
                print("\n  ── ADICIONAR ITEM DE CHECKLIST ──")
                aid = _input_id("Auditoria ID")
                cid = _input_id("Critério ID")
                pergunta = _input("Pergunta de verificação")
                iid = adicionar_item(aid, cid, pergunta)
                print(f"\n  Item #{iid} adicionado.")

            elif op == "4":
                print("\n  ── REGISTRAR RESULTADO ──")
                iid = _input_id("Item de checklist ID")
                resultado = _input("Resultado (Conforme / NC / Oportunidade)")
                evidencia = _input("Evidência", obrigatorio=False)
                nc_id = registrar_resultado(iid, resultado, evidencia)
                if nc_id:
                    print(f"\n  Resultado registrado. NC #{nc_id} gerada automaticamente.")
                else:
                    print(f"\n  Item #{iid} atualizado.")

            elif op == "5":
                print("\n  ── CLASSIFICAR NÃO CONFORMIDADE ──")
                nc_id = _input_id("NC ID")
                sev = _input("Severidade (Maior / Menor / Observação)")
                causa = _input("Causa raiz", obrigatorio=False)
                impacto = _input("Impacto")
                classificar_nc(nc_id, sev, causa, impacto)
                print(f"\n  NC #{nc_id} classificada.")

            elif op == "6":
                print("\n  ── CRIAR PLANO DE AÇÃO ──")
                aid = _input_id("Auditoria ID")
                nc_id = _input_id("NC ID")
                acao = _input("Ação corretiva")
                resp = _input("Responsável")
                prazo = _input_data("Prazo (AAAA-MM-DD)")
                pid = criar_plano(aid, nc_id, acao, resp, prazo)
                print(f"\n  Plano de ação #{pid} criado.")

            elif op == "7":
                print("\n  ── ATUALIZAR PLANO DE AÇÃO ──")
                pid = _input_id("Plano de ação ID")
                status = _input("Novo status (Aberto / Em andamento / Concluído / Verificado)")
                verif = _input("Evidência de verificação", obrigatorio=False)
                atualizar_plano(pid, status, verif)
                print(f"\n  Plano #{pid} → {status}")

            elif op == "8":
                print("\n  ── FINALIZAR AUDITORIA ──")
                aid = _input_id("Auditoria ID")
                resumo = _input("Resumo executivo")
                conclusao = _input("Conclusão")
                finalizar_auditoria(aid, resumo, conclusao)
                print(f"\n  Auditoria #{aid} finalizada.")

            elif op == "9":
                print(f"\n{listar_auditorias()}\n")

            elif op == "10":
                aid = _input_id("Auditoria ID")
                print(f"\n{detalhar_auditoria(aid)}\n")

            elif op == "11":
                print(f"\n{ver_log()}\n")

            elif op == "0":
                print("\n  Encerrando.\n")
                break

            else:
                print("\n  Opção inválida.\n")

        except ValidacaoError as e:
            print(f"\n  [ERRO] {e}\n")
        except KeyboardInterrupt:
            print("\n\n  Encerrando.\n")
            break


if __name__ == "__main__":
    main()   