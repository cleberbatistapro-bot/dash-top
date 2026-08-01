import json
import uuid
from pathlib import Path
from typing import Any

SESSOES_DIR = Path(__file__).resolve().parent.parent.parent / "sessoes"
SESSOES_DIR.mkdir(exist_ok=True)


def _caminho(sessao_id: str) -> Path:
    return SESSOES_DIR / f"{sessao_id}.json"


def criar_sessao(nome_arquivo: str, caminho_arquivo: str, total_linhas: int, colunas_detectadas: list[str]) -> str:
    sessao_id = str(uuid.uuid4())
    dados = {
        "sessao_id": sessao_id,
        "nome_arquivo": nome_arquivo,
        "caminho_arquivo": caminho_arquivo,
        "total_linhas": total_linhas,
        "colunas_detectadas": colunas_detectadas,
        "categoria_id": None,
        "mapeamento_sugerido": None,
        "mapeamento_confirmado": None,
    }
    salvar_sessao(sessao_id, dados)
    return sessao_id


def carregar_sessao(sessao_id: str) -> dict[str, Any]:
    caminho = _caminho(sessao_id)
    if not caminho.exists():
        raise FileNotFoundError(f"Sessão '{sessao_id}' não encontrada")

    with caminho.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_sessao(sessao_id: str, dados: dict[str, Any]) -> None:
    with _caminho(sessao_id).open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
