
import uuid
import datetime

from app.models.schemas import (
    LogAnalysisResult,
    MetricsAnomalyResult,
    RemediationPlan,
    ActionStatus,
    SeverityLevel
)
from app.services import telegram_service, ai_service, automation_service
from app.utils.logger import logger
from .system_service import save_plan_to_db, get_plan_from_db

async def analyze_logs(service_name: str, time_window: str) -> LogAnalysisResult:
    """Анализ логов для сервиса."""
    logger.info(f"Анализ логов для {service_name} за {time_window}...")
    # Здесь будет логика получения логов из Elasticsearch
    logs_data = "ERROR: Connection refused\nWARNING: High CPU usage"
    
    # Вызов AI для анализа
    analysis_result = await ai_service.analyze_logs_with_llm(logs_data)
    logger.info(f"Результат анализа логов: {analysis_result.summary}")
    return analysis_result

async def analyze_metrics(service_name: str, time_window: str) -> MetricsAnomalyResult:
    """Анализ метрик для сервиса."""
    logger.info(f"Анализ метрик для {service_name} за {time_window}...")
    # Здесь будет логика получения метрик из Prometheus
    # и вызова модели Chronos
    await asyncio.sleep(2) # Имитация работы
    return MetricsAnomalyResult(
        metric_name="cpu_usage",
        current_value=95.5,
        expected_range=(0, 80),
        anomaly_score=0.98,
        description="Аномально высокая загрузка CPU",
        timestamp=datetime.datetime.now()
    )

async def generate_remediation_plan(
    log_result: LogAnalysisResult,
    metrics_result: MetricsAnomalyResult
) -> RemediationPlan:
    """Генерация плана исправления."""
    logger.info("Генерация плана исправления...")
    context = f"""
    Обнаружена проблема:
    - Анализ метрик: {metrics_result.description} (значение: {metrics_result.current_value})
    - Анализ логов: {log_result.summary} (причина: {log_result.root_cause})
    """
    
    playbook_yaml = await ai_service.generate_remediation_plan(context)
    
    plan = RemediationPlan(
        plan_id=str(uuid.uuid4()),
        title=f"Исправление проблемы: {log_result.summary}",
        description=context,
        severity=log_result.severity,
        playbook_yaml=playbook_yaml,
        estimated_duration=60,
        created_at=datetime.datetime.now()
    )
    
    await save_plan_to_db(plan)
    logger.info(f"Создан план исправления: {plan.plan_id}")
    return plan

async def trigger_full_analysis(service_name: str, time_window: str):
    """Запускает полный цикл анализа."""
    try:
        # Шаг 1: Анализ метрик
        metrics_anomaly = await analyze_metrics(service_name, time_window)
        
        if metrics_anomaly.anomaly_score > 0.9:
            await telegram_service.send_message(
                f"⚠️ Обнаружена аномалия в метриках *{service_name}*: {metrics_anomaly.description}"
            )
            
            # Шаг 2: Анализ логов
            log_analysis = await analyze_logs(service_name, time_window)
            
            # Шаг 3: Генерация плана
            if log_analysis.severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]:
                remediation_plan = await generate_remediation_plan(log_analysis, metrics_anomaly)
                
                # Шаг 4: Отправка на утверждение
                await telegram_service.send_approval_request(remediation_plan)
            else:
                await telegram_service.send_message(
                    f"ℹ️ Проблема в *{service_name}* не требует немедленного вмешательства (уровень: {log_analysis.severity})."
                )
        else:
            await telegram_service.send_message(f"✅ Анализ для *{service_name}* завершен. Аномалий не найдено.")
            
    except Exception as e:
        logger.error(f"Ошибка при полном анализе сервиса {service_name}: {e}", exc_info=True)
        await telegram_service.send_message(f"❌ Ошибка при анализе сервиса *{service_name}*: {e}")

async def process_approval(plan_id: str, approved: bool, reason: str = None):
    """Обработка утверждения или отклонения плана."""
    plan = await get_plan_from_db(plan_id)
    
    if plan.status != ActionStatus.PENDING:
        return f"Действие по плану {plan_id} уже было выполнено."

    if approved:
        plan.status = ActionStatus.APPROVED
        plan.approved_at = datetime.datetime.now()
        await save_plan_to_db(plan)
        
        await telegram_service.send_message(f"🚀 План *{plan.title}* утвержден. Начинаю выполнение... ")
        
        # Запуск Ansible плейбука
        await automation_service.run_playbook_async(plan)
        return f"План {plan_id} утвержден и передан на выполнение."
    else:
        plan.status = ActionStatus.REJECTED
        await save_plan_to_db(plan)
        rejection_message = f"План *{plan.title}* отклонен."
        if reason:
            rejection_message += f" Причина: {reason}"
        await telegram_service.send_message(rejection_message)
        return f"План {plan_id} отклонен."
