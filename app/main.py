
from fastapi import FastAPI, BackgroundTasks, HTTPException
from typing import List

from app.models.schemas import (
    AnalysisRequest,
    ApprovalRequest,
    SystemStatus,
    RemediationPlan
)
from app.services import analysis_service, system_service, telegram_service
from app.utils.logger import logger
from config.settings import settings

app = FastAPI(
    title="AIOps Core API",
    description="Центральный API для управления AIOps системой",
    version="1.0.0",
    debug=settings.api_debug,
)

@app.on_event("startup")
async def startup_event():
    logger.info("AIOps Core API запускается...")
    await telegram_service.send_startup_message()

@app.get("/", tags=["General"])
async def read_root():
    """Проверка работоспособности API."""
    return {"status": "AIOps Core API is running"}

@app.get("/status", response_model=SystemStatus, tags=["System"])
async def get_system_status():
    """Получение полного статуса системы."""
    return await system_service.get_full_system_status()

@app.post("/analyze", tags=["Analysis"])
async def analyze_service_endpoint(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Запускает асинхронный анализ для указанного сервиса.
    """
    logger.info(f"Получен запрос на анализ для сервиса: {request.service_name}")
    await telegram_service.send_message(f"▶️ Начинаю анализ для сервиса: *{request.service_name}*")
    background_tasks.add_task(
        analysis_service.trigger_full_analysis,
        service_name=request.service_name,
        time_window=request.time_window
    )
    return {"status": "Analysis started in the background."}

@app.post("/approve", tags=["Actions"])
async def approve_remediation_plan(request: ApprovalRequest):
    """
    Утверждает или отклоняет план исправления.
    Вызывается из Telegram бота.
    """
    logger.info(f"Получено решение по плану {request.plan_id}: {'Утверждено' if request.approved else 'Отклонено'}")
    try:
        result = await analysis_service.process_approval(request.plan_id, request.approved, request.reason)
        return {"status": "success", "message": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/plans/{plan_id}", response_model=RemediationPlan, tags=["Actions"])
async def get_plan_by_id(plan_id: str):
    """Получение информации о плане по его ID."""
    try:
        plan = await system_service.get_plan_from_db(plan_id)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

