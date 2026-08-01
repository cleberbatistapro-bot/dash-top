from typing import Literal

from pydantic import BaseModel


class CampoEsperado(BaseModel):
    id: str
    nome_exibicao: str
    tipo: Literal["data", "numero", "texto"]
    obrigatorio: bool = False


class Kpi(BaseModel):
    id: str
    formula: str = ""
    formato: Literal["moeda", "numero", "percentual"] = "moeda"
    polaridade: Literal["alta_positiva", "alta_negativa", "sinal_do_valor"] = "alta_positiva"


class SerieGrafico(BaseModel):
    campo_valor: str
    nome: str
    cor: Literal["acc", "v", "amb", "c4", "c5"] = "acc"
    preenchido: bool = False


class GraficoConfig(BaseModel):
    tipo: str
    campo: str | None = None
    campo_valor: str | None = None
    campo_valor_a: str | None = None
    campo_valor_b: str | None = None
    series: list[SerieGrafico] | None = None
    formato: Literal["moeda", "numero", "percentual"] = "moeda"
    titulo: str | None = None


class VersaoDashboard(BaseModel):
    id: str
    nome: str
    graficos: list[GraficoConfig]


class Categoria(BaseModel):
    categoria: str
    nome_exibicao: str
    icone: str
    campos_esperados: list[CampoEsperado]
    filtros: list[str]
    kpis: list[Kpi]
    versoes_dashboard: list[VersaoDashboard]
