import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from core.cache import cache as _cache
from bots.analise_bots import BotManager

app = FastAPI(title="ERP Hub", version="1.0")
_manager: BotManager | None = None


@app.get("/status")
def status():
    st = _cache.status()
    return {"bots": {name: info for name, info in st.items()}}


@app.get("/dados/{bot_name}")
def dados(bot_name: str):
    data = _cache.load(bot_name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sem dados para '{bot_name}'")
    return JSONResponse(content=data)


def run_hub():
    """Start bots + FastAPI server. Blocks until process is killed."""
    global _manager
    from config.settings import HUB_PORT
    _manager = BotManager(use_hub=False)
    _manager.start_all()

    logging.info("Hub iniciado na porta %s", HUB_PORT)
    uvicorn.run(app, host="0.0.0.0", port=HUB_PORT, log_level="info")
