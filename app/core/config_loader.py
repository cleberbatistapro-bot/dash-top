from pathlib import Path

import yaml

from app.models.categoria import Categoria

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "categorias"


def carregar_categoria(categoria_id: str) -> Categoria:
    caminho = CONFIG_DIR / f"{categoria_id}.yaml"
    if not caminho.exists():
        raise FileNotFoundError(f"Categoria '{categoria_id}' não encontrada em {caminho}")

    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)

    return Categoria(**dados)


def listar_categorias() -> list[Categoria]:
    return [
        carregar_categoria(caminho.stem)
        for caminho in sorted(CONFIG_DIR.glob("*.yaml"))
    ]
