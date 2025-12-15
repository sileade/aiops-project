
import datetime
from elasticsearch import AsyncElasticsearch
import redis.asyncio as redis
import aiohttp

from app.models.schemas import SystemStatus, RemediationPlan, ActionStatus
from app.utils.logger import logger
from config.settings import settings

# Подключение к сервисам
es_client = AsyncElasticsearch(
    f"http://{settings.elasticsearch_host}:{settings.elasticsearch_port}"
)
redis_client = redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}", decode_responses=True)

async def get_elasticsearch_status() -> str:
    """Проверка статуса Elasticsearch."""
    try:
        if await es_client.ping():
            return "ok"
        return "unavailable"
    except Exception as e:
        logger.error(f"Ошибка подключения к Elasticsearch: {e}")
        return "error"

async def get_prometheus_status() -> str:
    """Проверка статуса Prometheus."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.prometheus_url}/-/healthy") as response:
                if response.status == 200:
                    return "ok"
                return f"unavailable (status: {response.status})"
    except Exception as e:
        logger.error(f"Ошибка подключения к Prometheus: {e}")
        return "error"

async def get_redis_status() -> str:
    """Проверка статуса Redis."""
    try:
        if await redis_client.ping():
            return "ok"
        return "unavailable"
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        return "error"

async def get_full_system_status() -> SystemStatus:
    """Собирает полный статус всех компонентов системы."""
    logger.info("Сбор полного статуса системы...")
    
    es_status, prom_status, redis_status = await asyncio.gather(
        get_elasticsearch_status(),
        get_prometheus_status(),
        get_redis_status()
    )
    
    # Заглушки для количества действий и аномалий
    pending_actions = await redis_client.scard("pending_plans")
    recent_anomalies = await redis_client.zcard("anomalies", min=datetime.datetime.now().timestamp() - 3600, max="+inf")

    return SystemStatus(
        api_status="ok",
        elasticsearch_status=es_status,
        prometheus_status=prom_status,
        redis_status=redis_status,
        pending_actions=pending_actions,
        recent_anomalies=recent_anomalies,
        timestamp=datetime.datetime.now()
    )

async def get_plan_from_db(plan_id: str) -> RemediationPlan:
    """Получение плана из Redis (заглушка)."""
    plan_data = await redis_client.hgetall(f"plan:{plan_id}")
    if not plan_data:
        raise ValueError(f"План с ID {plan_id} не найден.")
    
    return RemediationPlan(**plan_data)

async def save_plan_to_db(plan: RemediationPlan):
    """Сохранение плана в Redis."""
    await redis_client.hset(f"plan:{plan.plan_id}", mapping=plan.dict())
    if plan.status == ActionStatus.PENDING:
        await redis_client.sadd("pending_plans", plan.plan_id)
