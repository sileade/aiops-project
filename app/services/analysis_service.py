"""
Сервис для анализа логов и метрик.

Features:
- Параллельный сбор данных из Elasticsearch и Prometheus
- Circuit Breaker для защиты от сбоев источников данных
- Alertmanager webhooks для push-модели
"""

import uuid
import asyncio
import datetime
from typing import Optional, List, Dict, Any

import aiohttp
from elasticsearch import AsyncElasticsearch

from app.models.schemas import (
    LogAnalysisResult,
    MetricsAnomalyResult,
    RemediationPlan,
    ActionStatus,
    SeverityLevel
)
from app.services import telegram_service, ai_service, automation_service
from app.utils.logger import logger
from app.utils.circuit_breaker import (
    CircuitBreaker, 
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    elasticsearch_breaker,
    prometheus_breaker
)
from .system_service import save_plan_to_db, get_plan_from_db
from config.settings import settings


class DataCollector:
    """Класс для параллельного сбора данных из различных источников."""
    
    def __init__(self):
        self.es_client: Optional[AsyncElasticsearch] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
    
    async def get_es_client(self) -> AsyncElasticsearch:
        """Получает или создает клиент Elasticsearch."""
        if self.es_client is None:
            self.es_client = AsyncElasticsearch(
                hosts=[f"http://{settings.elasticsearch_host}:{settings.elasticsearch_port}"],
                request_timeout=30
            )
        return self.es_client
    
    async def get_http_session(self) -> aiohttp.ClientSession:
        """Получает или создает HTTP сессию для Prometheus."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._http_session
    
    async def close(self):
        """Закрывает соединения."""
        if self.es_client:
            await self.es_client.close()
            self.es_client = None
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None
    
    async def collect_logs_from_elasticsearch(
        self, 
        service_name: str, 
        time_window: str = "15m",
        log_level: str = "error"
    ) -> List[Dict[str, Any]]:
        """
        Собирает логи из Elasticsearch с circuit breaker защитой.
        """
        logger.info(f"Сбор логов из Elasticsearch для {service_name} за {time_window}...")
        
        # Check circuit breaker
        if elasticsearch_breaker.is_open:
            logger.warning("Elasticsearch circuit breaker is OPEN, returning empty logs")
            return []
        
        try:
            return await elasticsearch_breaker.call(
                self._collect_logs_internal,
                service_name, time_window, log_level
            )
        except CircuitBreakerOpenError:
            logger.warning("Elasticsearch circuit breaker triggered")
            return []
        except Exception as e:
            logger.error(f"Ошибка при сборе логов: {e}")
            return []
    
    async def _collect_logs_internal(
        self,
        service_name: str,
        time_window: str,
        log_level: str
    ) -> List[Dict[str, Any]]:
        """Internal method for log collection."""
        es = await self.get_es_client()
        
        # Определяем индекс
        index_patterns = [
            f"{service_name}-*",
            f"logs-{service_name}-*",
            f"filebeat-*"
        ]
        
        # Формируем запрос
        query = {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": f"now-{time_window}",
                                "lt": "now"
                            }
                        }
                    }
                ],
                "should": [
                    {"match": {"log.level": log_level}},
                    {"match": {"level": log_level}},
                    {"match": {"severity": log_level}},
                    {"match_phrase": {"message": "error"}},
                    {"match_phrase": {"message": "ERROR"}},
                    {"match_phrase": {"message": "exception"}},
                    {"match_phrase": {"message": "failed"}}
                ],
                "minimum_should_match": 1
            }
        }
        
        if service_name != "all":
            query["bool"]["must"].append({
                "bool": {
                    "should": [
                        {"match": {"service.name": service_name}},
                        {"match": {"kubernetes.labels.app": service_name}},
                        {"match": {"container.name": service_name}},
                        {"wildcard": {"source": f"*{service_name}*"}}
                    ],
                    "minimum_should_match": 1
                }
            })
        
        logs = []
        for index_pattern in index_patterns:
            try:
                response = await es.search(
                    index=index_pattern,
                    query=query,
                    size=100,
                    sort=[{"@timestamp": {"order": "desc"}}],
                    ignore_unavailable=True
                )
                
                for hit in response["hits"]["hits"]:
                    source = hit["_source"]
                    logs.append({
                        "timestamp": source.get("@timestamp"),
                        "message": source.get("message", ""),
                        "level": source.get("log", {}).get("level") or source.get("level", "unknown"),
                        "service": source.get("service", {}).get("name") or service_name,
                        "source": source.get("source", ""),
                        "raw": source
                    })
                
                if logs:
                    break
                    
            except Exception as e:
                logger.debug(f"Индекс {index_pattern} не найден или ошибка: {e}")
                continue
        
        logger.info(f"Собрано {len(logs)} записей логов для {service_name}")
        return logs
    
    async def collect_metrics_from_prometheus(
        self, 
        service_name: str, 
        time_window: str = "15m"
    ) -> Dict[str, Any]:
        """
        Собирает метрики из Prometheus с circuit breaker защитой.
        """
        logger.info(f"Сбор метрик из Prometheus для {service_name} за {time_window}...")
        
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "error_rate": None,
            "request_latency": None,
            "availability": None
        }
        
        # Check circuit breaker
        if prometheus_breaker.is_open:
            logger.warning("Prometheus circuit breaker is OPEN, returning empty metrics")
            return metrics
        
        try:
            return await prometheus_breaker.call(
                self._collect_metrics_internal,
                service_name, time_window
            )
        except CircuitBreakerOpenError:
            logger.warning("Prometheus circuit breaker triggered")
            return metrics
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик: {e}")
            return metrics
    
    async def _collect_metrics_internal(
        self,
        service_name: str,
        time_window: str
    ) -> Dict[str, Any]:
        """Internal method for metrics collection."""
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "error_rate": None,
            "request_latency": None,
            "availability": None
        }
        
        queries = {
            "cpu_usage": f'avg(rate(container_cpu_usage_seconds_total{{container="{service_name}"}}[{time_window}])) * 100',
            "memory_usage": f'avg(container_memory_usage_bytes{{container="{service_name}"}}) / 1024 / 1024',
            "error_rate": f'sum(rate(http_requests_total{{service="{service_name}",status=~"5.."}}[{time_window}])) / sum(rate(http_requests_total{{service="{service_name}"}}[{time_window}])) * 100',
            "request_latency": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[{time_window}]))',
            "availability": f'avg_over_time(up{{job="{service_name}"}}[{time_window}]) * 100'
        }
        
        session = await self.get_http_session()
        
        # Параллельный сбор всех метрик
        async def fetch_metric(metric_name: str, query: str) -> tuple:
            try:
                url = f"{settings.prometheus_url}/api/v1/query"
                params = {"query": query}
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["status"] == "success" and data["data"]["result"]:
                            value = float(data["data"]["result"][0]["value"][1])
                            return (metric_name, round(value, 2))
            except Exception as e:
                logger.debug(f"Не удалось получить метрику {metric_name}: {e}")
            return (metric_name, None)
        
        # Запускаем все запросы параллельно
        tasks = [fetch_metric(name, query) for name, query in queries.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, tuple):
                metric_name, value = result
                metrics[metric_name] = value
        
        logger.info(f"Собраны метрики для {service_name}: {metrics}")
        return metrics
    
    async def collect_all_data_parallel(
        self,
        service_name: str,
        time_window: str = "15m"
    ) -> Dict[str, Any]:
        """
        Параллельный сбор всех данных (логи + метрики).
        
        Returns:
            Dict с ключами 'logs' и 'metrics'
        """
        logger.info(f"Параллельный сбор данных для {service_name}...")
        
        # Запускаем сбор логов и метрик параллельно
        logs_task = asyncio.create_task(
            self.collect_logs_from_elasticsearch(service_name, time_window)
        )
        metrics_task = asyncio.create_task(
            self.collect_metrics_from_prometheus(service_name, time_window)
        )
        
        # Ждем завершения обоих задач
        logs, metrics = await asyncio.gather(logs_task, metrics_task, return_exceptions=True)
        
        # Обрабатываем возможные исключения
        if isinstance(logs, Exception):
            logger.error(f"Ошибка сбора логов: {logs}")
            logs = []
        if isinstance(metrics, Exception):
            logger.error(f"Ошибка сбора метрик: {metrics}")
            metrics = {}
        
        return {
            "logs": logs,
            "metrics": metrics,
            "collected_at": datetime.datetime.now().isoformat()
        }


# Глобальный экземпляр коллектора данных
data_collector = DataCollector()


# ==================== Alertmanager Webhook Handler ====================

async def handle_alertmanager_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик webhook от Alertmanager (push-модель).
    
    Args:
        payload: JSON payload от Alertmanager
        
    Returns:
        Dict с результатом обработки
    """
    logger.info(f"Получен webhook от Alertmanager: {payload.get('status')}")
    
    alerts = payload.get("alerts", [])
    processed = []
    
    for alert in alerts:
        alert_name = alert.get("labels", {}).get("alertname", "unknown")
        service = alert.get("labels", {}).get("service") or alert.get("labels", {}).get("job", "unknown")
        status = alert.get("status", "unknown")
        severity = alert.get("labels", {}).get("severity", "warning")
        description = alert.get("annotations", {}).get("description", "")
        
        logger.info(f"Обработка алерта: {alert_name} для {service} ({status})")
        
        if status == "firing":
            # Алерт активен - запускаем анализ
            try:
                # Определяем severity
                severity_map = {
                    "critical": SeverityLevel.CRITICAL,
                    "high": SeverityLevel.HIGH,
                    "warning": SeverityLevel.MEDIUM,
                    "info": SeverityLevel.LOW
                }
                sev = severity_map.get(severity.lower(), SeverityLevel.MEDIUM)
                
                # Отправляем уведомление
                await telegram_service.send_message(
                    f"🚨 *Alertmanager*: {alert_name}\n"
                    f"Сервис: {service}\n"
                    f"Severity: {severity}\n"
                    f"Описание: {description[:200]}"
                )
                
                # Для критических алертов запускаем полный анализ
                if sev in [SeverityLevel.CRITICAL, SeverityLevel.HIGH]:
                    asyncio.create_task(trigger_full_analysis(service, "15m"))
                
                processed.append({
                    "alert": alert_name,
                    "service": service,
                    "action": "analysis_triggered" if sev in [SeverityLevel.CRITICAL, SeverityLevel.HIGH] else "notified"
                })
                
            except Exception as e:
                logger.error(f"Ошибка обработки алерта {alert_name}: {e}")
                processed.append({
                    "alert": alert_name,
                    "error": str(e)
                })
        
        elif status == "resolved":
            # Алерт разрешен
            await telegram_service.send_message(
                f"✅ *Resolved*: {alert_name}\n"
                f"Сервис: {service}"
            )
            processed.append({
                "alert": alert_name,
                "service": service,
                "action": "resolved_notified"
            })
    
    return {
        "status": "processed",
        "alerts_count": len(alerts),
        "processed": processed
    }


# ==================== Analysis Functions ====================

async def analyze_logs(service_name: str, time_window: str) -> LogAnalysisResult:
    """
    Анализ логов для сервиса с использованием реальных данных.
    """
    logger.info(f"Анализ логов для {service_name} за {time_window}...")
    
    logs = await data_collector.collect_logs_from_elasticsearch(service_name, time_window)
    
    if not logs:
        logger.info(f"Логи для {service_name} не найдены")
        return LogAnalysisResult(
            summary="Логи не найдены",
            root_cause="Нет данных для анализа",
            severity=SeverityLevel.LOW,
            relevant_logs=[]
        )
    
    logs_text = "\n".join([
        f"[{log.get('timestamp', 'N/A')}] [{log.get('level', 'N/A')}] {log.get('message', '')}"
        for log in logs[:50]
    ])
    
    analysis_result = await ai_service.analyze_logs_with_llm(logs_text)
    logger.info(f"Результат анализа логов: {analysis_result.summary}")
    
    return analysis_result


async def analyze_metrics(service_name: str, time_window: str) -> MetricsAnomalyResult:
    """
    Анализ метрик для сервиса с использованием реальных данных.
    """
    logger.info(f"Анализ метрик для {service_name} за {time_window}...")
    
    metrics = await data_collector.collect_metrics_from_prometheus(service_name, time_window)
    
    anomaly_score = 0.0
    anomaly_description = []
    primary_metric = "system"
    primary_value = 0.0
    
    # Проверка CPU
    if metrics["cpu_usage"] is not None:
        if metrics["cpu_usage"] > 90:
            anomaly_score = max(anomaly_score, 0.95)
            anomaly_description.append(f"Критическая загрузка CPU: {metrics['cpu_usage']}%")
            primary_metric = "cpu_usage"
            primary_value = metrics["cpu_usage"]
        elif metrics["cpu_usage"] > 80:
            anomaly_score = max(anomaly_score, 0.8)
            anomaly_description.append(f"Высокая загрузка CPU: {metrics['cpu_usage']}%")
    
    # Проверка памяти
    if metrics["memory_usage"] is not None:
        if metrics["memory_usage"] > 90:
            anomaly_score = max(anomaly_score, 0.95)
            anomaly_description.append(f"Критическое использование памяти: {metrics['memory_usage']}%")
            if primary_metric == "system":
                primary_metric = "memory_usage"
                primary_value = metrics["memory_usage"]
        elif metrics["memory_usage"] > 80:
            anomaly_score = max(anomaly_score, 0.75)
            anomaly_description.append(f"Высокое использование памяти: {metrics['memory_usage']}%")
    
    # Проверка error rate
    if metrics["error_rate"] is not None:
        if metrics["error_rate"] > 10:
            anomaly_score = max(anomaly_score, 0.98)
            anomaly_description.append(f"Высокий уровень ошибок: {metrics['error_rate']}%")
            primary_metric = "error_rate"
            primary_value = metrics["error_rate"]
        elif metrics["error_rate"] > 5:
            anomaly_score = max(anomaly_score, 0.85)
            anomaly_description.append(f"Повышенный уровень ошибок: {metrics['error_rate']}%")
    
    # Проверка доступности
    if metrics["availability"] is not None and metrics["availability"] < 99:
        anomaly_score = max(anomaly_score, 0.9)
        anomaly_description.append(f"Низкая доступность: {metrics['availability']}%")
    
    if all(v is None for v in metrics.values()):
        logger.warning(f"Метрики для {service_name} не найдены")
        anomaly_score = 0.1
        anomaly_description = ["Метрики недоступны"]
    
    description = "; ".join(anomaly_description) if anomaly_description else "Аномалий не обнаружено"
    
    return MetricsAnomalyResult(
        metric_name=primary_metric,
        current_value=primary_value,
        expected_range=(0, 80),
        anomaly_score=anomaly_score,
        description=description,
        timestamp=datetime.datetime.now()
    )


async def generate_remediation_plan(
    log_result: LogAnalysisResult,
    metrics_result: MetricsAnomalyResult
) -> RemediationPlan:
    """
    Генерация плана исправления на основе результатов анализа.
    """
    logger.info("Генерация плана исправления...")
    
    context = f"""
Обнаружена проблема в IT-инфраструктуре:

## Анализ метрик:
- Метрика: {metrics_result.metric_name}
- Текущее значение: {metrics_result.current_value}
- Ожидаемый диапазон: {metrics_result.expected_range}
- Описание: {metrics_result.description}

## Анализ логов:
- Краткое описание: {log_result.summary}
- Первопричина: {log_result.root_cause}
- Уровень критичности: {log_result.severity}
- Релевантные логи:
{chr(10).join(log_result.relevant_logs[:5]) if log_result.relevant_logs else 'Нет данных'}
"""
    
    playbook_yaml = await ai_service.generate_remediation_plan(context)
    
    plan = RemediationPlan(
        plan_id=str(uuid.uuid4()),
        title=f"Исправление: {log_result.summary[:50]}",
        description=context,
        severity=log_result.severity,
        playbook_yaml=playbook_yaml,
        estimated_duration=60,
        created_at=datetime.datetime.now()
    )
    
    await save_plan_to_db(plan)
    logger.info(f"Создан план исправления: {plan.plan_id}")
    return plan


async def trigger_full_analysis(service_name: str, time_window: str = "15m"):
    """
    Запускает полный цикл анализа для сервиса с параллельным сбором данных.
    """
    try:
        # Параллельный сбор всех данных
        all_data = await data_collector.collect_all_data_parallel(service_name, time_window)
        
        # Анализ метрик
        metrics_anomaly = await analyze_metrics(service_name, time_window)
        
        if metrics_anomaly.anomaly_score > 0.7:
            await telegram_service.send_message(
                f"⚠️ Обнаружена аномалия в метриках *{service_name}*:\n{metrics_anomaly.description}"
            )
            
            # Анализ логов
            log_analysis = await analyze_logs(service_name, time_window)
            
            # Генерация плана
            if log_analysis.severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]:
                remediation_plan = await generate_remediation_plan(log_analysis, metrics_anomaly)
                await telegram_service.send_approval_request(remediation_plan)
            else:
                await telegram_service.send_message(
                    f"ℹ️ Проблема в *{service_name}* не требует немедленного вмешательства.\n"
                    f"Уровень: {log_analysis.severity.value}\n"
                    f"Описание: {log_analysis.summary}"
                )
        elif metrics_anomaly.anomaly_score > 0.5:
            await telegram_service.send_message(
                f"📊 Обнаружены отклонения в метриках *{service_name}*:\n{metrics_anomaly.description}\n\n"
                f"Рекомендуется мониторинг ситуации."
            )
        else:
            await telegram_service.send_message(
                f"✅ Анализ для *{service_name}* завершен.\nАномалий не обнаружено."
            )
            
    except Exception as e:
        logger.error(f"Ошибка при полном анализе сервиса {service_name}: {e}", exc_info=True)
        await telegram_service.send_message(
            f"❌ Ошибка при анализе сервиса *{service_name}*:\n`{str(e)[:200]}`"
        )


async def process_approval(plan_id: str, approved: bool, reason: str = None) -> str:
    """
    Обработка утверждения или отклонения плана.
    """
    plan = await get_plan_from_db(plan_id)
    
    if plan.status != ActionStatus.PENDING:
        return f"Действие по плану {plan_id} уже было выполнено."

    if approved:
        plan.status = ActionStatus.APPROVED
        plan.approved_at = datetime.datetime.now()
        await save_plan_to_db(plan)
        
        await telegram_service.send_message(
            f"🚀 План *{plan.title}* утвержден.\nНачинаю выполнение..."
        )
        
        await automation_service.run_playbook_async(plan)
        return f"План {plan_id} утвержден и передан на выполнение."
    else:
        plan.status = ActionStatus.REJECTED
        await save_plan_to_db(plan)
        
        rejection_message = f"❌ План *{plan.title}* отклонен."
        if reason:
            rejection_message += f"\nПричина: {reason}"
        await telegram_service.send_message(rejection_message)
        
        return f"План {plan_id} отклонен."


# ==================== Health Check ====================

async def get_data_sources_status() -> Dict[str, Any]:
    """Get status of all data sources."""
    return {
        "elasticsearch": elasticsearch_breaker.get_status(),
        "prometheus": prometheus_breaker.get_status(),
    }
