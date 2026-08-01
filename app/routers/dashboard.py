import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.dashboard_engine import SessaoIncompletaError, VersaoInvalidaError, gerar_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.get("/{sessao_id}/{versao_id}")
def obter_dashboard(sessao_id: str, versao_id: str, request: Request):
    filtros = dict(request.query_params)

    try:
        return gerar_dashboard(sessao_id, versao_id, filtros)
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except SessaoIncompletaError as erro:
        raise HTTPException(status_code=400, detail=str(erro))
    except VersaoInvalidaError as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except Exception:
        logger.exception(
            "Erro inesperado ao gerar o dashboard (sessao=%s, versao=%s, filtros=%s)",
            sessao_id, versao_id, filtros,
        )
        raise HTTPException(status_code=500, detail="Não foi possível carregar os dados. Tente novamente.")
