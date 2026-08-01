import re
from datetime import timedelta
from pathlib import Path

import pandas as pd

from app.core import sessions
from app.core.config_loader import carregar_categoria
from app.core.planilha import ler_planilha
from app.models.categoria import Categoria

TOP_N_RANKING = 8
TOP_N_COMPOSICAO = 5
TAMANHO_PAGINA = 20

ROTULOS_KPI = {
    "faturamento": "Faturamento",
    "pedidos": "Pedidos",
    "ticket_medio": "Ticket médio",
    "taxa_conversao": "Taxa de conversão",
    "receita_total": "Receita total",
    "despesa_total": "Despesa total",
    "saldo": "Saldo",
    "margem": "Margem",
    "valor_total_estoque": "Valor total em estoque",
    "produtos_distintos": "Produtos distintos",
    "quantidade_total": "Quantidade total",
    "giro_medio": "Giro médio",
    "headcount_ativo": "Headcount ativo",
    "desligamentos_periodo": "Desligamentos no período",
    "turnover": "Turnover",
    "custo_folha": "Custo de folha",
    "total_leads": "Total de leads",
    "custo_total": "Custo total",
    "cac": "CAC (custo por conversão)",
    "tempo_ciclo_medio": "Tempo de ciclo médio (h)",
    "sla_cumprido_percentual": "SLA cumprido",
    "total_operacoes": "Total de operações",
    "tickets_abertos": "Tickets abertos",
    "tickets_resolvidos": "Tickets resolvidos",
    "tempo_resposta_medio": "Tempo de resposta médio (h)",
    "nps_medio": "Nota de satisfação média",
}

TITULOS_PADRAO_GRAFICO = {
    "barras_mensais_pareadas": "Valores por mês",
    "saldo_mensal": "Saldo por mês",
    "ranking": "Ranking",
    "composicao": "Composição",
}

MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


class SessaoIncompletaError(Exception):
    pass


class VersaoInvalidaError(Exception):
    pass


def _serializar_valor(valor):
    if pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%d")
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _carregar_dados_mapeados(sessao_id: str) -> tuple[pd.DataFrame, Categoria]:
    sessao = sessions.carregar_sessao(sessao_id)

    if not sessao.get("categoria_id") or not sessao.get("mapeamento_confirmado"):
        raise SessaoIncompletaError(
            "Esta sessão ainda não tem uma categoria e um mapeamento de colunas confirmados."
        )

    categoria = carregar_categoria(sessao["categoria_id"])
    mapeamento = {
        item["campo_id"]: item["coluna"]
        for item in sessao["mapeamento_confirmado"]
        if item["coluna"]
    }

    df_bruto = ler_planilha(Path(sessao["caminho_arquivo"]))

    df = pd.DataFrame(index=df_bruto.index)
    for campo_id, coluna in mapeamento.items():
        df[campo_id] = df_bruto[coluna]

    for campo in categoria.campos_esperados:
        if campo.id not in df.columns:
            continue
        if campo.tipo == "data":
            df[campo.id] = pd.to_datetime(df[campo.id], errors="coerce")
        elif campo.tipo == "numero":
            df[campo.id] = pd.to_numeric(df[campo.id], errors="coerce")

    return df, categoria


def _aplicar_filtros(df: pd.DataFrame, filtros: dict, categoria: Categoria) -> pd.DataFrame:
    resultado = df

    if filtros.get("periodo_inicio") and "data" in resultado.columns:
        resultado = resultado[resultado["data"] >= pd.to_datetime(filtros["periodo_inicio"])]
    if filtros.get("periodo_fim") and "data" in resultado.columns:
        resultado = resultado[resultado["data"] <= pd.to_datetime(filtros["periodo_fim"])]

    for campo in categoria.filtros:
        if campo == "periodo":
            continue
        valor = filtros.get(campo)
        if valor and campo in resultado.columns:
            resultado = resultado[resultado[campo] == valor]

    return resultado


def _periodo_atual_e_anterior(df: pd.DataFrame, filtros: dict):
    if filtros.get("periodo_inicio") and filtros.get("periodo_fim"):
        inicio = pd.to_datetime(filtros["periodo_inicio"])
        fim = pd.to_datetime(filtros["periodo_fim"])
    elif "data" in df.columns and df["data"].notna().any():
        inicio = df["data"].min()
        fim = df["data"].max()
    else:
        return None, None, None, None

    duracao = (fim - inicio) + timedelta(days=1)
    fim_anterior = inicio - timedelta(days=1)
    inicio_anterior = fim_anterior - duracao + timedelta(days=1)
    return inicio, fim, inicio_anterior, fim_anterior


def _avaliar_formula(formula: str, df: pd.DataFrame) -> float | None:
    formula = formula.strip()
    if formula == "customizado" or not formula:
        return None

    for operador in (" - ", " + "):
        if operador in formula:
            esquerda, direita = formula.split(operador, 1)
            valor_esquerda = _avaliar_formula(esquerda, df)
            valor_direita = _avaliar_formula(direita, df)
            if valor_esquerda is None or valor_direita is None:
                return None
            return valor_esquerda - valor_direita if operador == " - " else valor_esquerda + valor_direita

    if " / " in formula:
        esquerda, direita = formula.split(" / ", 1)
        valor_esquerda = _avaliar_formula(esquerda, df)
        valor_direita = _avaliar_formula(direita, df)
        if valor_esquerda is None or not valor_direita:
            return None
        return valor_esquerda / valor_direita

    if " onde " in formula:
        expressao, condicao = formula.split(" onde ", 1)
        campo_condicao, valor_condicao = (parte.strip() for parte in condicao.split("=", 1))
        if campo_condicao not in df.columns:
            return None
        df = df[df[campo_condicao] == valor_condicao]
        formula = expressao.strip()

    correspondencia = re.match(r"(\w+)\(([^)]+)\)", formula)
    if not correspondencia:
        return None

    funcao, argumento = correspondencia.group(1), correspondencia.group(2).strip()

    if funcao == "contagem":
        return float(len(df))
    if funcao == "contagem_unica":
        return float(df[argumento].nunique()) if argumento in df.columns else None

    serie = _serie_numerica(df, argumento)
    if serie is None:
        return None

    if funcao == "soma":
        return float(serie.sum())
    if funcao == "media":
        return float(serie.mean()) if len(df) else 0.0
    return None


def _rotulo_kpi(kpi_id: str) -> str:
    return ROTULOS_KPI.get(kpi_id, kpi_id.replace("_", " ").capitalize())


def _escalar_para_formato(valor: float | None, formato: str) -> float | None:
    if valor is None:
        return None
    return valor * 100 if formato == "percentual" else valor


def _cor_kpi(polaridade: str, valor: float, tendencia: str | None) -> str:
    if polaridade == "sinal_do_valor":
        return "positiva" if valor >= 0 else "negativa"
    if tendencia is None:
        return "neutra"
    if polaridade == "alta_negativa":
        return "negativa" if tendencia == "alta" else "positiva"
    return "positiva" if tendencia == "alta" else "negativa"


def calcular_kpis(df_atual: pd.DataFrame, df_anterior: pd.DataFrame | None, categoria: Categoria) -> list[dict]:
    kpis = []
    for kpi in categoria.kpis:
        valor_atual = _escalar_para_formato(_avaliar_formula(kpi.formula, df_atual), kpi.formato)
        if valor_atual is None:
            continue

        valor_anterior = None
        if df_anterior is not None:
            valor_anterior = _escalar_para_formato(_avaliar_formula(kpi.formula, df_anterior), kpi.formato)

        variacao = None
        tendencia = None
        if valor_anterior:
            variacao = round(((valor_atual - valor_anterior) / valor_anterior) * 100, 1)
            tendencia = "alta" if variacao >= 0 else "baixa"

        kpis.append({
            "id": kpi.id,
            "label": _rotulo_kpi(kpi.id),
            "formato": kpi.formato,
            "valor": round(valor_atual, 2),
            "variacao_percentual": variacao,
            "tendencia": tendencia,
            "cor": _cor_kpi(kpi.polaridade, valor_atual, tendencia),
            "destacar_valor_por_sinal": kpi.polaridade == "sinal_do_valor",
        })

    return kpis


def _serie_numerica(df: pd.DataFrame, campo_valor: str) -> pd.Series | None:
    if "*" in campo_valor:
        campo_a, campo_b = (c.strip() for c in campo_valor.split("*", 1))
        if campo_a not in df.columns or campo_b not in df.columns:
            return None
        return df[campo_a] * df[campo_b]
    if campo_valor not in df.columns:
        return None
    return df[campo_valor]


def _grade_e_chave_temporal(datas: pd.Series, inicio: pd.Timestamp | None, fim: pd.Timestamp | None):
    if inicio is None or fim is None:
        inicio, fim = datas.min(), datas.max()

    inicio_normalizado = inicio.normalize()
    fim_normalizado = fim.normalize()
    dias_periodo = (fim_normalizado - inicio_normalizado).days + 1

    if dias_periodo <= 45:
        chave_por_linha = datas.dt.normalize()
        grade = list(pd.date_range(inicio_normalizado, fim_normalizado, freq="D"))
        return chave_por_linha, grade, False

    if dias_periodo <= 120:
        deslocamento_dias = (datas.dt.normalize() - inicio_normalizado).dt.days // 7 * 7
        chave_por_linha = inicio_normalizado + pd.to_timedelta(deslocamento_dias, unit="D")
        grade = list(pd.date_range(inicio_normalizado, fim_normalizado, freq="7D"))
        return chave_por_linha, grade, False

    chave_por_linha = datas.dt.to_period("M")
    grade = list(pd.period_range(inicio.to_period("M"), fim.to_period("M"), freq="M"))
    return chave_por_linha, grade, True


def _rotulos_temporais(chaves: list, mensal: bool) -> list[str]:
    if mensal:
        return [f"{MESES_PT[chave.month - 1]}/{chave.year}" for chave in chaves]
    return [f"{chave.day:02d}/{chave.month:02d}" for chave in chaves]


def grafico_tendencia_periodo(
    df: pd.DataFrame, series: list, inicio: pd.Timestamp | None, fim: pd.Timestamp | None
) -> dict:
    if "data" not in df.columns:
        return {"erro": "Data não está mapeada para esta categoria."}

    validos = df.dropna(subset=["data"])
    if validos.empty:
        return {"erro": "Não há datas válidas para montar o gráfico."}

    chave_por_linha, grade, mensal = _grade_e_chave_temporal(validos["data"], inicio, fim)

    if len(grade) < 2:
        return {"erro": "Dados insuficientes para o gráfico (mínimo de 2 pontos)."}

    datasets = []
    for serie in series:
        if serie.campo_valor == "contagem":
            agrupado = validos.assign(_chave=chave_por_linha).groupby("_chave").size()
        else:
            serie_valor = _serie_numerica(validos, serie.campo_valor)
            if serie_valor is None:
                continue
            agrupado = validos.assign(_chave=chave_por_linha, _valor=serie_valor).groupby("_chave")["_valor"].sum()

        agrupado = agrupado.reindex(grade, fill_value=0)
        datasets.append({
            "label": serie.nome,
            "data": [round(float(v), 2) for v in agrupado.tolist()],
            "cor": serie.cor,
            "preenchido": serie.preenchido,
        })

    if not datasets:
        return {"erro": "Campo(s) de valor não estão mapeados para esta categoria."}

    labels = _rotulos_temporais(grade, mensal)
    return {"labels": labels, "datasets": datasets}


def grafico_saldo_periodo(
    df: pd.DataFrame,
    campo_valor_a: str,
    campo_valor_b: str,
    inicio: pd.Timestamp | None,
    fim: pd.Timestamp | None,
) -> dict:
    if "data" not in df.columns:
        return {"erro": "Data não está mapeada para esta categoria."}

    validos = df.dropna(subset=["data"])
    if validos.empty:
        return {"erro": "Não há datas válidas para montar o gráfico de saldo."}

    serie_a = _serie_numerica(validos, campo_valor_a)
    serie_b = _serie_numerica(validos, campo_valor_b)
    if serie_a is None or serie_b is None:
        return {"erro": "Campos de valor não estão mapeados para esta categoria."}

    chave_por_linha, grade, mensal = _grade_e_chave_temporal(validos["data"], inicio, fim)

    if len(grade) < 2:
        return {"erro": "Dados insuficientes para o gráfico de saldo (mínimo de 2 pontos)."}

    diferenca = serie_a - serie_b
    agrupado = validos.assign(_chave=chave_por_linha, _dif=diferenca).groupby("_chave")["_dif"].sum()
    agrupado = agrupado.reindex(grade, fill_value=0)

    labels = _rotulos_temporais(grade, mensal)
    valores = [round(float(v), 2) for v in agrupado.tolist()]
    return {"labels": labels, "datasets": [{"label": "Saldo", "data": valores}]}


def grafico_ranking(df: pd.DataFrame, campo: str, campo_valor: str, valor_selecionado: str | None = None) -> dict:
    if campo not in df.columns:
        return {"erro": f"Coluna para '{campo}' não está mapeada para esta categoria."}

    trabalho = df.dropna(subset=[campo])

    if campo_valor == "contagem":
        agrupado = trabalho.groupby(campo).size().sort_values(ascending=False).head(TOP_N_RANKING)
        rotulo = "Quantidade"
    else:
        serie_valor = _serie_numerica(trabalho, campo_valor)
        if serie_valor is None:
            return {"erro": f"Campo '{campo_valor}' não está mapeado para esta categoria."}
        agrupado = (
            trabalho.assign(_valor=serie_valor)
            .groupby(campo)["_valor"]
            .sum()
            .sort_values(ascending=False)
            .head(TOP_N_RANKING)
        )
        rotulo = "Total"

    if agrupado.empty:
        return {"erro": "Sem dados suficientes para montar o ranking."}

    resultado = {
        "labels": [str(item) for item in agrupado.index.tolist()],
        "datasets": [{"label": rotulo, "data": [round(float(v), 2) for v in agrupado.tolist()]}],
    }
    if valor_selecionado is not None:
        resultado["selecionado"] = valor_selecionado
    return resultado


def grafico_composicao(df: pd.DataFrame, campo: str, campo_valor: str) -> dict:
    if campo not in df.columns:
        return {"erro": f"Coluna para '{campo}' não está mapeada para esta categoria."}

    trabalho = df.dropna(subset=[campo])

    if campo_valor == "contagem":
        agrupado = trabalho.groupby(campo).size().sort_values(ascending=False)
    else:
        serie_valor = _serie_numerica(trabalho, campo_valor)
        if serie_valor is None:
            return {"erro": f"Campo '{campo_valor}' não está mapeado para esta categoria."}
        agrupado = trabalho.assign(_valor=serie_valor).groupby(campo)["_valor"].sum().sort_values(ascending=False)

    total = agrupado.sum()
    if total == 0 or agrupado.empty:
        return {"erro": "Sem dados suficientes para montar a composição."}

    principais = agrupado.head(TOP_N_COMPOSICAO)
    outros = agrupado.iloc[TOP_N_COMPOSICAO:].sum()

    labels = [str(item) for item in principais.index.tolist()]
    valores_abs = [round(float(v), 2) for v in principais.tolist()]
    valores_pct = [round(float((v / total) * 100), 1) for v in principais.tolist()]

    if outros > 0:
        labels.append("Outros")
        valores_abs.append(round(float(outros), 2))
        valores_pct.append(round(float((outros / total) * 100), 1))

    return {
        "labels": labels,
        "datasets": [{"label": "% do total", "data": valores_pct}],
        "valores_absolutos": valores_abs,
    }


def valores_disponiveis_para_filtros(df: pd.DataFrame, categoria: Categoria) -> dict[str, dict]:
    rotulos_por_campo = {campo.id: campo.nome_exibicao for campo in categoria.campos_esperados}
    disponiveis = {}
    for filtro in categoria.filtros:
        if filtro == "periodo" or filtro not in df.columns:
            continue
        disponiveis[filtro] = {
            "label": rotulos_por_campo.get(filtro, filtro.replace("_", " ").capitalize()),
            "valores": sorted(str(v) for v in df[filtro].dropna().unique().tolist()),
        }
    return disponiveis


def tabela_paginada(df: pd.DataFrame, categoria: Categoria, pagina: int) -> dict:
    total_linhas = len(df)
    inicio = (pagina - 1) * TAMANHO_PAGINA
    fim = inicio + TAMANHO_PAGINA
    pagina_df = df.iloc[inicio:fim]

    colunas = [campo for campo in categoria.campos_esperados if campo.id in df.columns]
    linhas = []
    for _, linha in pagina_df.iterrows():
        linhas.append({campo.id: _serializar_valor(linha[campo.id]) for campo in colunas})

    return {
        "colunas": [{"id": campo.id, "nome_exibicao": campo.nome_exibicao} for campo in colunas],
        "linhas": linhas,
        "pagina": pagina,
        "tamanho_pagina": TAMANHO_PAGINA,
        "total_linhas": total_linhas,
        "total_paginas": max(1, -(-total_linhas // TAMANHO_PAGINA)),
    }


def gerar_dashboard(sessao_id: str, versao_id: str, filtros: dict) -> dict:
    df, categoria = _carregar_dados_mapeados(sessao_id)

    versao = next((v for v in categoria.versoes_dashboard if v.id == versao_id), None)
    if versao is None:
        raise VersaoInvalidaError(f"Versão '{versao_id}' não existe para a categoria '{categoria.categoria}'.")

    df_filtrado = _aplicar_filtros(df, filtros, categoria)

    filtros_sem_periodo = {k: v for k, v in filtros.items() if k not in ("periodo_inicio", "periodo_fim")}
    df_dimensoes = _aplicar_filtros(df, filtros_sem_periodo, categoria)

    inicio, fim, inicio_anterior, fim_anterior = _periodo_atual_e_anterior(df_filtrado, filtros)

    df_periodo_anterior = None
    if inicio is not None and "data" in df_dimensoes.columns:
        df_periodo_anterior = df_dimensoes[
            (df_dimensoes["data"] >= inicio_anterior) & (df_dimensoes["data"] <= fim_anterior)
        ]

    kpis = calcular_kpis(df_filtrado, df_periodo_anterior, categoria)

    graficos = {}
    tabela = None

    for grafico_cfg in versao.graficos:
        if grafico_cfg.tipo == "tabela":
            pagina = int(filtros.get("pagina") or 1)
            tabela = tabela_paginada(df_filtrado, categoria, pagina)
            continue

        chave = f"{grafico_cfg.tipo}_{grafico_cfg.campo}" if grafico_cfg.campo else grafico_cfg.tipo

        if grafico_cfg.tipo == "barras_mensais_pareadas":
            dados = grafico_tendencia_periodo(df_filtrado, grafico_cfg.series or [], inicio, fim)
        elif grafico_cfg.tipo == "saldo_mensal":
            dados = grafico_saldo_periodo(df_filtrado, grafico_cfg.campo_valor_a, grafico_cfg.campo_valor_b, inicio, fim)
        elif grafico_cfg.tipo == "ranking":
            valor_filtro_dimensao = filtros.get(grafico_cfg.campo) if grafico_cfg.campo else None
            if valor_filtro_dimensao:
                filtros_sem_esta_dimensao = {k: v for k, v in filtros.items() if k != grafico_cfg.campo}
                df_para_ranking = _aplicar_filtros(df, filtros_sem_esta_dimensao, categoria)
                dados = grafico_ranking(
                    df_para_ranking, grafico_cfg.campo, grafico_cfg.campo_valor,
                    valor_selecionado=valor_filtro_dimensao,
                )
            else:
                dados = grafico_ranking(df_filtrado, grafico_cfg.campo, grafico_cfg.campo_valor)
        elif grafico_cfg.tipo == "composicao":
            dados = grafico_composicao(df_filtrado, grafico_cfg.campo, grafico_cfg.campo_valor)
            dados["formato"] = grafico_cfg.formato
        else:
            continue

        dados["tipo"] = grafico_cfg.tipo
        dados["titulo"] = grafico_cfg.titulo or TITULOS_PADRAO_GRAFICO.get(grafico_cfg.tipo, grafico_cfg.tipo)
        graficos[chave] = dados

    return {
        "categoria_id": categoria.categoria,
        "categoria_nome_exibicao": categoria.nome_exibicao,
        "versao_id": versao.id,
        "versao_nome": versao.nome,
        "kpis": kpis,
        "graficos": graficos,
        "tabela": tabela,
        "filtros_disponiveis": valores_disponiveis_para_filtros(df, categoria),
    }
