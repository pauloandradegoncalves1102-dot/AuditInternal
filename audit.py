from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime
from typing import Optional
import json

class Severidade(Enum):
    MAIOR = "Maior"
    MENOR = "Menor"
    OBSERVACAO = "Observação"
class StatusAcao(Enum):
    ABERTO = "Aberto"
    EM_ANDAMENTO = "Em andamento"
    CONCLUIDO = "Concluído"
    VERIFICADO = "Verificado"
@dataclass
class Criterio:
    descricao: str
    fonte: str  
@dataclass
class ChecklistItem:
    id: int
    criterio: Criterio
    pergunta: str
    resultado: Optional[str] = None  
    evidencia: Optional[str] = None
@dataclass
class NaoConformidade:
    id: int
    checklist_item_id: int
    severidade: Severidade
    descricao: str
    evidencia: str
    impacto: str
@dataclass
class PlanoAcao:
    id: int
    nc_id: int
    acao_corretiva: str
    responsavel: str
    prazo: date
    status: StatusAcao = StatusAcao.ABERTO
    verificacao: Optional[str] = None
@dataclass
class Auditoria:
    id: int
    titulo: str
    escopo: str
    criterios: list[Criterio]
    data_inicio: date
    data_fim: date
    auditor: str
    checklist: list[ChecklistItem] = field(default_factory=list)
    nao_conformidades: list[NaoConformidade] = field(default_factory=list)
    planos_acao: list[PlanoAcao] = field(default_factory=list)
    resumo_executivo: str = ""
    conclusao: str = ""
class ProgramadorAuditoria:
    def __init__(self):
        self.auditorias: list[Auditoria] = []
        self._next_id = 1
    def criar_auditoria(
        self,
        titulo: str,
        escopo: str,
        criterios: list[Criterio],
        data_inicio: date,
        data_fim: date,
        auditor: str,
    ) -> Auditoria:
        auditoria = Auditoria(
            id=self._next_id,
            titulo=titulo,
            escopo=escopo,
            criterios=criterios,
            data_inicio=data_inicio,
            data_fim=data_fim,
            auditor=auditor,
        )
        self._next_id += 1
        self.auditorias.append(auditoria)
        return auditoria
    def gerar_checklist(self, auditoria: Auditoria, perguntas: list[tuple[Criterio, str]]):
        auditoria.checklist = [
            ChecklistItem(id=i + 1, criterio=c, pergunta=p)
            for i, (c, p) in enumerate(perguntas)
        ]
class ExecutorAuditoria:
    def __init__(self, auditoria: Auditoria):
        self.auditoria = auditoria
        self._next_nc_id = 1
    def registrar_resultado(self, item_id: int, resultado: str, evidencia: str = ""):
        item = next(i for i in self.auditoria.checklist if i.id == item_id)
        item.resultado = resultado
        item.evidencia = evidencia
        if resultado == "NC":
            self._registrar_nc(item, evidencia)
    def _registrar_nc(self, item: ChecklistItem, evidencia: str):
        nc = NaoConformidade(
            id=self._next_nc_id,
            checklist_item_id=item.id,
            severidade=Severidade.MENOR,  # ajustável
            descricao=item.pergunta,
            evidencia=evidencia,
            impacto="A definir",
        )
        self._next_nc_id += 1
        self.auditoria.nao_conformidades.append(nc)
    def classificar_nc(self, nc_id: int, severidade: Severidade, impacto: str):
        nc = next(n for n in self.auditoria.nao_conformidades if n.id == nc_id)
        nc.severidade = severidade
        nc.impacto = impacto
class GeradorRelatorio:
    def __init__(self, auditoria: Auditoria):
        self.auditoria = auditoria
    def gerar(self, resumo_executivo: str, conclusao: str) -> str:
        self.auditoria.resumo_executivo = resumo_executivo
        self.auditoria.conclusao = conclusao
        linhas = [
            "=" * 60,
            f"RELATÓRIO DE AUDITORIA INTERNA #{self.auditoria.id}",
            "=" * 60,
            f"Título:      {self.auditoria.titulo}",
            f"Escopo:      {self.auditoria.escopo}",
            f"Auditor:     {self.auditoria.auditor}",
            f"Período:     {self.auditoria.data_inicio} a {self.auditoria.data_fim}",
            "-" * 60,
            "RESUMO EXECUTIVO",
            resumo_executivo,
            "-" * 60,
            f"CHECKLIST ({len(self.auditoria.checklist)} itens)",
        ]
        for item in self.auditoria.checklist:
            status = item.resultado or "Pendente"
            linhas.append(f"  [{item.id}] {status:15s} | {item.pergunta}")
        linhas.append("-" * 60)
        linhas.append(f"NAO CONFORMIDADES ({len(self.auditoria.nao_conformidades)})")
        for nc in self.auditoria.nao_conformidades:
            linhas.append(
                f"  NC-{nc.id} [{nc.severidade.value}] {nc.descricao}\n"
                f"         Evidência: {nc.evidencia}\n"
                f"         Impacto:   {nc.impacto}"
            )
        linhas.append("-" * 60)
        linhas.append("CONCLUSÃO")
        linhas.append(conclusao)
        linhas.append("=" * 60)
        return "\n".join(linhas)
class GestorPlanoAcao:
    def __init__(self, auditoria: Auditoria):
        self.auditoria = auditoria
        self._next_id = 1
    def criar_acao(self, nc_id: int, acao: str, responsavel: str, prazo: date):
        plano = PlanoAcao(
            id=self._next_id,
            nc_id=nc_id,
            acao_corretiva=acao,
            responsavel=responsavel,
            prazo=prazo,
        )
        self._next_id += 1
        self.auditoria.planos_acao.append(plano)
    def atualizar_status(self, plano_id: int, status: StatusAcao, verificacao: str = ""):
        plano = next(p for p in self.auditoria.planos_acao if p.id == plano_id)
        plano.status = status
        if verificacao:
            plano.verificacao = verificacao
    def resumo_acoes(self) -> str:
        linhas = [f"{'ID':<4} {'NC':<4} {'Status':<12} {'Responsável':<15} {'Prazo'}"]
        for p in self.auditoria.planos_acao:
            linhas.append(
                f"{p.id:<4} {p.nc_id:<4} {p.status.value:<12} {p.responsavel:<15} {p.prazo}"
            )
        return "\n".join(linhas)
if __name__ == "__main__":
    programador = ProgramadorAuditoria()
    aud = programador.criar_auditoria(
        titulo="Auditoria do Processo de Compras",
        escopo="Departamento de Suprimentos",
        criterios=[
            Criterio("Política de Compras v3.2", "Política interna"),
            Criterio("Lei 14.133/2021", "Legislação"),
        ],
        data_inicio=date(2026, 10, 1),
        data_fim=date(2026, 10, 15),
        auditor="Ana Souza",
    )
    programador.gerar_checklist(aud, [
        (aud.criterios[0], "Os pedidos seguem a hierarquia de aprovação?"),
        (aud.criterios[0], "Há cotação mínima de 3 fornecedores?"),
        (aud.criterios[1], "Contratos estão registrados no SICAF?"),
    ])
    executor = ExecutorAuditoria(aud)
    executor.registrar_resultado(1, "Conforme", "Amostra de 20 pedidos OK")
    executor.registrar_resultado(2, "NC", "3 pedidos com apenas 1 cotação")
    executor.registrar_resultado(3, "Conforme", "Todos registrados")
    executor.classificar_nc(1, Severidade.MENOR, "Risco de sobrepreço")
    relatorio = GeradorRelatorio(aud)
    texto = relatorio.gerar(
        resumo_executivo="Processo de compras 80% conforme. 1 NC menor identificada.",
        conclusao="Sistema parcialmente eficaz. Requer ação corretiva em cotações.",
    )
    print(texto)
    gestor = GestorPlanoAcao(aud)
    gestor.criar_acao(1, "Revisar política de cotação e treinar equipe", "Carlos Lima", date(2026, 11, 15))
    gestor.atualizar_status(1, StatusAcao.EM_ANDAMENTO)
    print("\n--- PLANOS DE AÇÃO ---")
    print(gestor.resumo_acoes())   