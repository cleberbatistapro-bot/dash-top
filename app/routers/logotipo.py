from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

router = APIRouter(prefix="/api/logotipo", tags=["logotipo"])

LOGOS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "logos"
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

EXTENSOES_PERMITIDAS = {".png", ".svg"}
TAMANHO_MAXIMO_BYTES = 2 * 1024 * 1024


def _logo_existente() -> Path | None:
    for extensao in EXTENSOES_PERMITIDAS:
        caminho = LOGOS_DIR / f"logotipo{extensao}"
        if caminho.exists():
            return caminho
    return None


@router.get("")
def obter_logotipo():
    caminho = _logo_existente()
    if not caminho:
        return {"configurado": False, "url": None}
    return {"configurado": True, "url": f"/logos/{caminho.name}"}


@router.post("")
def enviar_logotipo(arquivo: UploadFile):
    extensao = Path(arquivo.filename).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=400, detail="Envie uma imagem PNG ou SVG.")

    conteudo = arquivo.file.read()
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise HTTPException(status_code=400, detail="O arquivo excede o limite de 2MB.")

    for antiga in EXTENSOES_PERMITIDAS:
        (LOGOS_DIR / f"logotipo{antiga}").unlink(missing_ok=True)

    caminho_destino = LOGOS_DIR / f"logotipo{extensao}"
    with caminho_destino.open("wb") as destino:
        destino.write(conteudo)

    return {"configurado": True, "url": f"/logos/{caminho_destino.name}"}
