import unicodedata

from app.core.config_loader import listar_categorias
from app.models.categoria import CampoEsperado

SINONIMOS: dict[str, dict[str, list[str]]] = {
    "vendas": {
        "data": ["data da venda", "dia", "dt venda"],
        "valor": ["valor total", "faturamento", "valor da venda", "total"],
        "vendedor": ["responsavel", "responsável", "consultor"],
        "produto": ["item", "produto/categoria", "categoria do produto"],
        "regiao": ["região", "praca", "praça", "uf", "estado"],
    },
    "financeiro": {
        "data": ["dia", "data do lancamento", "data do lançamento"],
        "receita": ["entrada", "faturamento", "receitas"],
        "despesa": ["saida", "saída", "custo", "gasto", "despesas"],
        "centro_custo": ["centro de custo", "departamento", "setor"],
        "tipo_conta": ["tipo de conta", "conta", "natureza"],
    },
    "estoque": {
        "data": ["data de entrada", "data do movimento", "dia"],
        "produto": ["item", "sku", "descricao", "descrição"],
        "categoria_produto": ["categoria", "categoria do produto", "familia", "família", "grupo"],
        "quantidade": ["qtd", "qtde", "quantidade em estoque", "estoque atual"],
        "valor_unitario": ["valor unitario", "valor unitário", "preco unitario", "preço unitário", "custo unitario", "custo unitário"],
        "fornecedor": ["fornecedor", "supplier", "marca"],
    },
    "rh": {
        "data": ["data de admissao", "data de admissão", "data do evento", "dia"],
        "colaborador": ["funcionario", "funcionário", "nome", "empregado", "colaborador(a)"],
        "departamento": ["setor", "area", "área", "diretoria"],
        "cargo": ["funcao", "função", "posicao", "posição", "cargo/funcao"],
        "status": ["situacao", "situação", "status do colaborador"],
        "salario": ["salario", "salário", "remuneracao", "remuneração", "salario base", "salário base"],
    },
    "marketing": {
        "data": ["dia", "data da campanha"],
        "canal": ["origem", "fonte", "source", "midia", "mídia"],
        "campanha": ["campaign", "acao", "ação"],
        "leads": ["contatos", "cadastros", "oportunidades"],
        "custo": ["investimento", "gasto", "spend", "valor investido"],
        "conversoes": ["vendas", "conversao", "conversões fechadas", "fechamentos"],
    },
    "operacoes": {
        "data": ["dia", "data da operacao", "data da operação"],
        "equipe": ["time", "squad", "setor"],
        "tipo_operacao": ["tipo", "categoria da operacao", "categoria da operação", "processo"],
        "tempo_ciclo_horas": ["tempo de ciclo", "lead time", "duracao", "duração", "tempo gasto"],
        "dentro_do_sla": ["sla", "dentro do prazo", "cumpriu sla", "atendeu sla"],
    },
    "atendimento": {
        "data": ["dia", "data do ticket", "data de abertura"],
        "canal": ["origem", "fonte", "meio de contato"],
        "categoria_ticket": ["categoria", "tipo de ticket", "assunto", "motivo"],
        "tempo_resposta_horas": ["tempo de resposta", "tempo de atendimento", "sla de resposta"],
        "nota_satisfacao": ["csat", "nps", "satisfacao", "satisfação", "avaliacao", "avaliação"],
        "status": ["situacao", "situação", "status do ticket"],
    },
}


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def _candidatos(campo: CampoEsperado, categoria_id: str) -> list[str]:
    candidatos = [campo.id, campo.nome_exibicao]
    candidatos += SINONIMOS.get(categoria_id, {}).get(campo.id, [])
    return [normalizar(candidato) for candidato in candidatos]


PESO_EXATO = 1.0
PESO_PARCIAL = 0.5


def _melhor_correspondencia(
    campo: CampoEsperado, categoria_id: str, colunas: list[str]
) -> tuple[str | None, float]:
    """Retorna (coluna, peso): peso 1.0 para correspondência exata (nome/sinônimo
    idêntico à coluna normalizada), 0.5 para correspondência parcial (substring)."""
    colunas_normalizadas = {normalizar(coluna): coluna for coluna in colunas}
    candidatos = _candidatos(campo, categoria_id)

    for candidato in candidatos:
        if candidato in colunas_normalizadas:
            return colunas_normalizadas[candidato], PESO_EXATO

    for candidato in candidatos:
        for coluna_normalizada, coluna_original in colunas_normalizadas.items():
            if candidato in coluna_normalizada or coluna_normalizada in candidato:
                return coluna_original, PESO_PARCIAL

    return None, 0.0


def coluna_correspondente(
    campo: CampoEsperado, categoria_id: str, colunas: list[str]
) -> str | None:
    coluna, _ = _melhor_correspondencia(campo, categoria_id, colunas)
    return coluna


def sugerir_categoria(colunas: list[str]) -> dict:
    resultados = []

    for categoria in listar_categorias():
        obrigatorios = [c for c in categoria.campos_esperados if c.obrigatorio]
        pesos = [_melhor_correspondencia(campo, categoria.categoria, colunas)[1] for campo in obrigatorios]
        total = len(obrigatorios)
        confianca = (sum(pesos) / total) if total else 0.0
        encontrados = sum(1 for peso in pesos if peso > 0)

        resultados.append({
            "categoria_id": categoria.categoria,
            "nome_exibicao": categoria.nome_exibicao,
            "icone": categoria.icone,
            "confianca": round(confianca, 2),
            "campos_obrigatorios_encontrados": encontrados,
            "campos_obrigatorios_total": total,
        })

    resultados.sort(key=lambda item: item["confianca"], reverse=True)
    sugestao = resultados[0]["categoria_id"] if resultados and resultados[0]["confianca"] > 0 else None

    return {"sugestao": sugestao, "categorias": resultados}
