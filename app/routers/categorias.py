from fastapi import APIRouter, HTTPException

from app.core.config_loader import carregar_categoria

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


@router.get("/{categoria_id}")
def obter_categoria(categoria_id: str):
    try:
        categoria = carregar_categoria(categoria_id)
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail=str(erro))

    return categoria
