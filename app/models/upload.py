from pydantic import BaseModel


class EscolhaCategoria(BaseModel):
    categoria_id: str


class CampoMapeamentoEntrada(BaseModel):
    campo_id: str
    coluna: str | None = None


class ConfirmarMapeamento(BaseModel):
    mapeamento: list[CampoMapeamentoEntrada]
