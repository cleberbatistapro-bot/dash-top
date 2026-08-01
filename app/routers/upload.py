import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.core import sessions
from app.core.category_matcher import coluna_correspondente, sugerir_categoria
from app.core.config_loader import carregar_categoria
from app.core.planilha import ler_planilha
from app.models.upload import ConfirmarMapeamento, EscolhaCategoria

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

EXTENSOES_PERMITIDAS = {".xlsx", ".xls", ".csv"}


@router.post("")
def enviar_planilha(arquivo: UploadFile):
    extensao = Path(arquivo.filename).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{extensao}' não suportado. Envie .xlsx, .xls ou .csv",
        )

    nome_salvo = f"{uuid.uuid4()}{extensao}"
    caminho_destino = UPLOADS_DIR / nome_salvo

    with caminho_destino.open("wb") as destino:
        destino.write(arquivo.file.read())

    try:
        df = ler_planilha(caminho_destino)
    except Exception:
        caminho_destino.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível ler o arquivo. Verifique se ele não está corrompido e se o formato é válido.",
        )

    colunas_detectadas = [str(coluna) for coluna in df.columns]
    sessao_id = sessions.criar_sessao(
        nome_arquivo=arquivo.filename,
        caminho_arquivo=str(caminho_destino),
        total_linhas=len(df),
        colunas_detectadas=colunas_detectadas,
    )

    return {
        "sessao_id": sessao_id,
        "nome_arquivo": arquivo.filename,
        "total_linhas": len(df),
        "colunas_detectadas": colunas_detectadas,
    }


def _obter_sessao_ou_404(sessao_id: str) -> dict:
    try:
        return sessions.carregar_sessao(sessao_id)
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail=str(erro))


@router.get("/{sessao_id}/sugestao-categoria")
def sugestao_categoria(sessao_id: str):
    sessao = _obter_sessao_ou_404(sessao_id)
    return sugerir_categoria(sessao["colunas_detectadas"])


@router.post("/{sessao_id}/mapeamento")
def gerar_mapeamento(sessao_id: str, escolha: EscolhaCategoria):
    sessao = _obter_sessao_ou_404(sessao_id)

    try:
        categoria = carregar_categoria(escolha.categoria_id)
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail=str(erro))

    colunas = sessao["colunas_detectadas"]
    campos = []
    mapeamento_sugerido = []
    for campo in categoria.campos_esperados:
        coluna_sugerida = coluna_correspondente(campo, categoria.categoria, colunas)
        campos.append({
            "id": campo.id,
            "nome_exibicao": campo.nome_exibicao,
            "coluna_sugerida": coluna_sugerida,
            "obrigatorio": campo.obrigatorio,
            "confirmado": False,
        })
        mapeamento_sugerido.append({"campo_id": campo.id, "coluna": coluna_sugerida})

    sessao["categoria_id"] = categoria.categoria
    sessao["mapeamento_sugerido"] = mapeamento_sugerido
    sessions.salvar_sessao(sessao_id, sessao)

    return {
        "categoria_id": categoria.categoria,
        "colunas_detectadas": colunas,
        "campos": campos,
    }


@router.put("/{sessao_id}/mapeamento")
def confirmar_mapeamento(sessao_id: str, corpo: ConfirmarMapeamento):
    sessao = _obter_sessao_ou_404(sessao_id)

    if not sessao.get("categoria_id"):
        raise HTTPException(
            status_code=400,
            detail="Nenhuma categoria foi escolhida para esta sessão ainda.",
        )

    categoria = carregar_categoria(sessao["categoria_id"])
    coluna_por_campo = {item.campo_id: item.coluna for item in corpo.mapeamento}

    faltando = [
        campo.nome_exibicao
        for campo in categoria.campos_esperados
        if campo.obrigatorio and not coluna_por_campo.get(campo.id)
    ]

    if faltando:
        raise HTTPException(
            status_code=400,
            detail=f"Campos obrigatórios sem coluna associada: {', '.join(faltando)}",
        )

    sessao["mapeamento_confirmado"] = [item.model_dump() for item in corpo.mapeamento]
    sessions.salvar_sessao(sessao_id, sessao)

    return {"sucesso": True, "mensagem": "Mapeamento confirmado com sucesso."}
