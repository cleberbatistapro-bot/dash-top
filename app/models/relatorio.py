from pydantic import BaseModel


class GraficoRelatorio(BaseModel):
    titulo: str
    imagem: str


class RelatorioRequest(BaseModel):
    filtros: dict[str, str | None] = {}
    graficos: dict[str, GraficoRelatorio] = {}
