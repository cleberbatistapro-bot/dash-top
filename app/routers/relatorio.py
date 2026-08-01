from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core import sessions
from app.core.dashboard_engine import SessaoIncompletaError
from app.core.relatorio_pdf import gerar_pdf_relatorio
from app.models.relatorio import RelatorioRequest

router = APIRouter(prefix="/api/relatorio", tags=["relatorio"])


@router.post("/{sessao_id}")
def relatorio(sessao_id: str, corpo: RelatorioRequest):
    try:
        sessao = sessions.carregar_sessao(sessao_id)
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail=str(erro))

    try:
        pdf_bytes = gerar_pdf_relatorio(sessao_id, corpo.filtros, corpo.graficos)
    except SessaoIncompletaError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    categoria_id = sessao.get("categoria_id") or "dashboard"
    data_formatada = datetime.now().strftime("%Y-%m-%d")
    nome_arquivo = f"relatorio-dashtop-{categoria_id}-{data_formatada}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
