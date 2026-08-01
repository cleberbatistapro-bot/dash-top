from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import categorias, dashboard, logotipo, relatorio, upload
from app.routers.logotipo import LOGOS_DIR

app = FastAPI(title="Dash Top")

app.include_router(categorias.router)
app.include_router(upload.router)
app.include_router(dashboard.router)
app.include_router(logotipo.router)
app.include_router(relatorio.router)

app.mount("/logos", StaticFiles(directory=LOGOS_DIR), name="logos")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
