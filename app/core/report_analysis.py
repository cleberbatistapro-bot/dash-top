"""Geração de texto analítico para o relatório em PDF.

Cada análise segue o mesmo padrão: uma função `calcular_*` que só extrai
números dos dados filtrados (sem nenhum texto), e uma função `texto_*` que
preenche um template com esses números. Nenhuma frase é gerada sem um
valor calculado por trás dela.
"""

import pandas as pd

from app.core.dashboard_engine import (
    _grade_e_chave_temporal,
    _rotulos_temporais,
    _serie_numerica,
)
from app.models.categoria import Categoria, VersaoDashboard


def _formatar_numero_br(valor: float, casas: int = 1) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _formatar_valor(valor: float, formato: str) -> str:
    if formato == "numero":
        return _formatar_numero_br(valor, 0)
    if formato == "percentual":
        return f"{_formatar_numero_br(valor, 1)}%"
    return f"R$ {_formatar_numero_br(valor, 2)}"


def _formato_efetivo(campo_valor: str, formato_configurado: str) -> str:
    return "numero" if campo_valor == "contagem" else formato_configurado


def _rotulo_campo(categoria: Categoria, campo_id: str | None) -> str:
    if campo_id is None:
        return ""
    for campo in categoria.campos_esperados:
        if campo.id == campo_id:
            return campo.nome_exibicao
    return campo_id.replace("_", " ").capitalize()


def _agrupar_por_dimensao(df: pd.DataFrame, campo: str, campo_valor: str) -> pd.Series | None:
    if campo not in df.columns:
        return None
    trabalho = df.dropna(subset=[campo])
    if trabalho.empty:
        return None

    if campo_valor == "contagem":
        agrupado = trabalho.groupby(campo).size()
    else:
        serie_valor = _serie_numerica(trabalho, campo_valor)
        if serie_valor is None:
            return None
        agrupado = trabalho.assign(_valor=serie_valor).groupby(campo)["_valor"].sum()

    return agrupado.sort_values(ascending=False)


def calcular_analise_dimensao(df: pd.DataFrame, campo: str, campo_valor: str) -> dict | None:
    agrupado = _agrupar_por_dimensao(df, campo, campo_valor)
    if agrupado is None or len(agrupado) < 2:
        return None

    total = float(agrupado.sum())
    if total == 0:
        return None

    nomes = [str(n) for n in agrupado.index.tolist()]
    valores = [float(v) for v in agrupado.tolist()]

    melhor_nome, melhor_valor = nomes[0], valores[0]
    pior_nome, pior_valor = nomes[-1], valores[-1]

    diferenca_percentual = None
    if pior_valor > 0:
        diferenca_percentual = ((melhor_valor - pior_valor) / pior_valor) * 100

    top2_nomes = nomes[:2]
    top2_pct = (sum(valores[:2]) / total) * 100

    return {
        "quantidade_grupos": len(valores),
        "melhor_nome": melhor_nome,
        "melhor_valor": melhor_valor,
        "pior_nome": pior_nome,
        "pior_valor": pior_valor,
        "diferenca_percentual": diferenca_percentual,
        "concentracao_top1_pct": (melhor_valor / total) * 100,
        "concentracao_top2_pct": top2_pct,
        "concentracao_top2_nomes": top2_nomes,
        "total": total,
    }


def texto_analise_dimensao(stats: dict | None, rotulo_campo: str, formato: str) -> list[str]:
    if stats is None:
        return []

    melhor_fmt = _formatar_valor(stats["melhor_valor"], formato)
    pior_fmt = _formatar_valor(stats["pior_valor"], formato)

    paragrafo_1 = (
        f"Entre os {stats['quantidade_grupos']} valores de {rotulo_campo.lower()} registrados no período, "
        f"{stats['melhor_nome']} teve o melhor resultado, com {melhor_fmt}, enquanto {stats['pior_nome']} "
        f"teve o menor, com {pior_fmt}."
    )
    if stats["diferenca_percentual"] is not None:
        paragrafo_1 += (
            f" {stats['melhor_nome']} superou {stats['pior_nome']} em "
            f"{_formatar_numero_br(stats['diferenca_percentual'], 1)}%."
        )

    nomes_top2 = " e ".join(stats["concentracao_top2_nomes"])
    partes_2 = [
        f"{nomes_top2} juntos respondem por {_formatar_numero_br(stats['concentracao_top2_pct'], 1)}% do total."
    ]
    if stats["concentracao_top1_pct"] > 40:
        partes_2.append(
            f"{stats['melhor_nome']} concentra sozinho "
            f"{_formatar_numero_br(stats['concentracao_top1_pct'], 1)}% do total, "
            "o que indica concentração de risco nessa dimensão."
        )
    else:
        partes_2.append(
            "A distribuição entre os grupos é relativamente equilibrada, sem concentração excessiva "
            "em um único grupo."
        )

    return [paragrafo_1, " ".join(partes_2)]


def _unidade_temporal(grade: list, mensal: bool) -> str:
    if mensal:
        return "mês"
    diferenca_dias = (grade[1] - grade[0]).days
    return "dia" if diferenca_dias == 1 else "semana"


def _plural_unidade(unidade: str) -> str:
    if unidade == "mês":
        return "meses"
    return f"{unidade}s"


def _excluir_periodo_parcial_final(
    valores: list[float], labels: list[str], grade: list, mensal: bool, fim: pd.Timestamp | None
) -> tuple[list[float], list[str]]:
    """Remove o último período da lista se ele ainda não tiver se encerrado até `fim`.

    Evita apontar um mês/semana em andamento como "o pior" só porque tem menos
    dias de dados que os períodos anteriores, já fechados.
    """
    if len(valores) < 3:
        return valores, labels

    referencia = fim if fim is not None else pd.Timestamp.now()

    if mensal:
        fim_do_ultimo_periodo = grade[-1].end_time
    else:
        diferenca_dias = (grade[1] - grade[0]).days
        if diferenca_dias == 1:
            return valores, labels
        fim_do_ultimo_periodo = grade[-1] + pd.Timedelta(days=diferenca_dias - 1)

    if fim_do_ultimo_periodo.normalize() > referencia.normalize():
        return valores[:-1], labels[:-1]
    return valores, labels


def calcular_analise_temporal(
    df: pd.DataFrame, campo_valor: str, inicio: pd.Timestamp | None, fim: pd.Timestamp | None
) -> dict | None:
    if "data" not in df.columns:
        return None

    validos = df.dropna(subset=["data"])
    if validos.empty:
        return None

    chave_por_linha, grade, mensal = _grade_e_chave_temporal(validos["data"], inicio, fim)
    if len(grade) < 2:
        return None

    if campo_valor == "contagem":
        agrupado = validos.assign(_chave=chave_por_linha).groupby("_chave").size()
    else:
        serie_valor = _serie_numerica(validos, campo_valor)
        if serie_valor is None:
            return None
        agrupado = validos.assign(_chave=chave_por_linha, _valor=serie_valor).groupby("_chave")["_valor"].sum()

    agrupado = agrupado.reindex(grade, fill_value=0)
    valores = [float(v) for v in agrupado.tolist()]
    labels = _rotulos_temporais(grade, mensal)
    valores, labels = _excluir_periodo_parcial_final(valores, labels, grade, mensal, fim)

    if len(valores) < 2:
        return None

    indice_melhor = max(range(len(valores)), key=lambda i: valores[i])
    indice_pior = min(range(len(valores)), key=lambda i: valores[i])

    terco = max(1, len(valores) // 3)
    media_inicio = sum(valores[:terco]) / terco
    media_fim = sum(valores[-terco:]) / terco

    variacao_direcao_pct = None
    if media_inicio != 0:
        variacao_direcao_pct = ((media_fim - media_inicio) / abs(media_inicio)) * 100

    media_geral = sum(valores) / len(valores)
    desvio_padrao = (sum((v - media_geral) ** 2 for v in valores) / len(valores)) ** 0.5
    coeficiente_variacao = (desvio_padrao / abs(media_geral)) if media_geral != 0 else None

    return {
        "unidade": _unidade_temporal(grade, mensal),
        "quantidade_periodos": len(valores),
        "melhor_label": labels[indice_melhor],
        "melhor_valor": valores[indice_melhor],
        "pior_label": labels[indice_pior],
        "pior_valor": valores[indice_pior],
        "variacao_direcao_pct": variacao_direcao_pct,
        "coeficiente_variacao": coeficiente_variacao,
    }


def texto_analise_temporal(stats: dict | None, rotulo_serie: str, formato: str) -> list[str]:
    if stats is None:
        return []

    melhor_fmt = _formatar_valor(stats["melhor_valor"], formato)
    pior_fmt = _formatar_valor(stats["pior_valor"], formato)
    unidade = stats["unidade"]

    variacao = stats["variacao_direcao_pct"]
    if variacao is None:
        direcao_texto = f"{rotulo_serie} não apresentou uma direção clara ao longo do período."
    elif variacao > 8:
        direcao_texto = (
            f"{rotulo_serie} cresceu ao longo do período: a média do último terço do período ficou "
            f"{_formatar_numero_br(variacao, 1)}% acima da média do primeiro terço."
        )
    elif variacao < -8:
        direcao_texto = (
            f"{rotulo_serie} caiu ao longo do período: a média do último terço ficou "
            f"{_formatar_numero_br(abs(variacao), 1)}% abaixo da média do primeiro terço."
        )
    else:
        direcao_texto = (
            f"{rotulo_serie} se manteve relativamente estável ao longo do período, "
            "sem uma tendência clara de alta ou queda."
        )

    paragrafo_1 = (
        f"{direcao_texto} O melhor {unidade} do período foi {stats['melhor_label']}, com {melhor_fmt}. "
        f"O pior foi {stats['pior_label']}, com {pior_fmt}."
    )

    paragrafos = [paragrafo_1]

    coeficiente = stats["coeficiente_variacao"]
    if coeficiente is not None:
        if coeficiente > 0.5:
            paragrafos.append(
                "Os valores oscilaram bastante ao longo do período, sem um padrão constante entre "
                f"cada {unidade}."
            )
        else:
            paragrafos.append(
                f"Os valores se mantiveram relativamente consistentes entre os {_plural_unidade(unidade)} "
                "do período, com poucas oscilações bruscas."
            )

    return paragrafos


def calcular_analise_saldo(
    df: pd.DataFrame,
    campo_valor_a: str,
    campo_valor_b: str,
    inicio: pd.Timestamp | None,
    fim: pd.Timestamp | None,
) -> dict | None:
    if "data" not in df.columns:
        return None

    validos = df.dropna(subset=["data"])
    if validos.empty:
        return None

    serie_a = _serie_numerica(validos, campo_valor_a)
    serie_b = _serie_numerica(validos, campo_valor_b)
    if serie_a is None or serie_b is None:
        return None

    chave_por_linha, grade, mensal = _grade_e_chave_temporal(validos["data"], inicio, fim)
    if len(grade) < 2:
        return None

    diferenca = serie_a - serie_b
    agrupado = validos.assign(_chave=chave_por_linha, _dif=diferenca).groupby("_chave")["_dif"].sum()
    agrupado = agrupado.reindex(grade, fill_value=0)
    valores = [float(v) for v in agrupado.tolist()]
    labels = _rotulos_temporais(grade, mensal)
    valores, labels = _excluir_periodo_parcial_final(valores, labels, grade, mensal, fim)

    if len(valores) < 2:
        return None

    positivos = sum(1 for v in valores if v > 0)
    negativos = sum(1 for v in valores if v < 0)

    indice_melhor = max(range(len(valores)), key=lambda i: valores[i])
    indice_pior = min(range(len(valores)), key=lambda i: valores[i])

    return {
        "unidade": _unidade_temporal(grade, mensal),
        "total_periodos": len(valores),
        "positivos": positivos,
        "negativos": negativos,
        "melhor_label": labels[indice_melhor],
        "melhor_valor": valores[indice_melhor],
        "pior_label": labels[indice_pior],
        "pior_valor": valores[indice_pior],
    }


def texto_analise_saldo(stats: dict | None) -> list[str]:
    if stats is None:
        return []

    unidade_plural = _plural_unidade(stats["unidade"])
    paragrafo_1 = (
        f"Dos {stats['total_periodos']} {unidade_plural} analisados, {stats['positivos']} fecharam com saldo "
        f"positivo e {stats['negativos']} com saldo negativo."
    )
    paragrafo_2 = (
        f"O melhor resultado foi em {stats['melhor_label']}, com {_formatar_valor(stats['melhor_valor'], 'moeda')}. "
        f"O pior foi em {stats['pior_label']}, com {_formatar_valor(stats['pior_valor'], 'moeda')}."
    )
    return [paragrafo_1, paragrafo_2]


def calcular_analise_composicao(df: pd.DataFrame, campo: str, campo_valor: str) -> dict | None:
    agrupado = _agrupar_por_dimensao(df, campo, campo_valor)
    if agrupado is None or agrupado.empty:
        return None

    total = float(agrupado.sum())
    if total == 0:
        return None

    nomes = [str(n) for n in agrupado.index.tolist()]
    valores = [float(v) for v in agrupado.tolist()]

    dominante_pct = (valores[0] / total) * 100
    segundo_pct = (valores[1] / total) * 100 if len(valores) >= 2 else 0.0
    concentrado = dominante_pct >= 40 or (dominante_pct + segundo_pct) >= 65

    return {
        "quantidade_categorias": len(valores),
        "dominante_nome": nomes[0],
        "dominante_pct": dominante_pct,
        "concentrado": concentrado,
    }


def texto_analise_composicao(stats: dict | None, rotulo_campo: str) -> list[str]:
    if stats is None:
        return []

    paragrafo_1 = (
        f"{stats['dominante_nome']} é a categoria dominante em {rotulo_campo.lower()}, representando "
        f"{_formatar_numero_br(stats['dominante_pct'], 1)}% do total, distribuído entre "
        f"{stats['quantidade_categorias']} categorias."
    )

    if stats["concentrado"]:
        paragrafo_2 = (
            "A composição é concentrada: poucas categorias respondem pela maior parte do total."
        )
    else:
        paragrafo_2 = "A composição é distribuída, sem uma categoria isolada dominando o total."

    return [paragrafo_1, paragrafo_2]


def gerar_secoes_analise(
    df_filtrado: pd.DataFrame,
    categoria: Categoria,
    versao: VersaoDashboard,
    inicio: pd.Timestamp | None,
    fim: pd.Timestamp | None,
) -> list[dict]:
    """Monta as seções de análise (título + parágrafos + gráficos ilustrativos)."""

    graficos_por_tipo = {g.tipo: g for g in versao.graficos}
    secoes = []

    cfg_ranking = graficos_por_tipo.get("ranking")
    if cfg_ranking:
        stats = calcular_analise_dimensao(df_filtrado, cfg_ranking.campo, cfg_ranking.campo_valor)
        rotulo = _rotulo_campo(categoria, cfg_ranking.campo)
        formato = _formato_efetivo(cfg_ranking.campo_valor, cfg_ranking.formato)
        paragrafos = texto_analise_dimensao(stats, rotulo, formato)
        if paragrafos:
            secoes.append({
                "titulo": f"Desempenho por {rotulo}",
                "paragrafos": paragrafos,
                "tipos_grafico": ["ranking"],
            })

    cfg_tendencia = graficos_por_tipo.get("barras_mensais_pareadas")
    if cfg_tendencia and cfg_tendencia.series:
        serie_primaria = cfg_tendencia.series[0]
        stats = calcular_analise_temporal(df_filtrado, serie_primaria.campo_valor, inicio, fim)
        formato = _formato_efetivo(serie_primaria.campo_valor, cfg_tendencia.formato)
        paragrafos = texto_analise_temporal(stats, serie_primaria.nome, formato)
        tipos_grafico = ["barras_mensais_pareadas"] if paragrafos else []

        cfg_saldo = graficos_por_tipo.get("saldo_mensal")
        if cfg_saldo:
            stats_saldo = calcular_analise_saldo(
                df_filtrado, cfg_saldo.campo_valor_a, cfg_saldo.campo_valor_b, inicio, fim
            )
            paragrafos_saldo = texto_analise_saldo(stats_saldo)
            if paragrafos_saldo:
                paragrafos += paragrafos_saldo
                tipos_grafico.append("saldo_mensal")

        if paragrafos:
            secoes.append({
                "titulo": "Evolução no período",
                "paragrafos": paragrafos,
                "tipos_grafico": tipos_grafico,
            })

    cfg_composicao = graficos_por_tipo.get("composicao")
    if cfg_composicao:
        stats = calcular_analise_composicao(df_filtrado, cfg_composicao.campo, cfg_composicao.campo_valor)
        rotulo = _rotulo_campo(categoria, cfg_composicao.campo)
        paragrafos = texto_analise_composicao(stats, rotulo)
        if paragrafos:
            secoes.append({
                "titulo": "Composição",
                "paragrafos": paragrafos,
                "tipos_grafico": ["composicao"],
            })

    return secoes
