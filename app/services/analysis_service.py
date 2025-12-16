"""
Сервис для анализа логов и метрик.
Включает реальную интеграцию с Elasticsearch и Prometheus.
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
from .system_service import save_plan_to_db, get_plan_from_db
from config.settings import settings


class DataCollector:
    """Класс для сбора данных из различных источников."""
    
    def __init__(self):
        self.es_client: Optional[AsyncElasticsearch] = None
    
    async def get_es_client(self) -> AsyncElasticsearch:
        """Получает или создает клиент Elasticsearch."""
        if self.es_client is None:
            self.es_client = AsyncElasticsearch(
                hosts=[f"http://{settings.elasticsearch_host}:{settings.elasticsearch_port}"],
                request_timeout=30
            )
        return self.es_client
    
    async def close(self):
        """Закрывает соединения."""
        if self.es_client:
            await self.es_client.close()
            self.es_client = None
    
    async def collect_logs_from_elasticsearch(
        self, 
        service_name: str, 
        time_window: str = "15m",
        log_level: str = "error"
    ) -> List[Dict[str, Any]]:
        """
        Собирает логи из Elasticsearch для указанного сервиса.
        
        Args:
            service_name: Имя сервиса (используется как часть индекса)
            time_window: Временное окно (например, "15m", "1h", "24h")
            log_level: Уровень логов для фильтрации (error, warning, info)
            
        Returns:
            Список записей логов
        """
        logger.info(f"Сбор логов из Elasticsearch для {service_name} за {time_window}...")
        
        try:
            es = await self.get_es_client()
            
            # Определяем индекс (поддерживаем разные форматы)
            index_patterns = [
                f"{service_name}-*",
                f"logs-{service_name}-*",
                f"filebeat-*"  # Fallback на общий индекс filebeat
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
            
            # Если указан конкретный сервис, добавляем фильтр
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
                        break  # Нашли логи, выходим
                        
                except Exception as e:
                    logger.debug(f"Индекс {index_pattern} не найден или ошибка: {e}")
                    continue
            
            logger.info(f"Собрано {len(logs)} записей логов для {service_name}")
            return logs
            
        except Exception as e:
            logger.error(f"Ошибка при сборе логов из Elasticsearch: {e}")
            return []
    
    async def collect_metrics_from_prometheus(
        self, 
        service_name: str, 
        time_window: str = "15m"
    ) -> Dict[str, Any]:
        """
        Собирает метрики из Prometheus для указанного сервиса.
        
        Args:
            service_name: Имя сервиса
            time_window: Временное окно
            
        Returns:
            Словарь с метриками
        """
        logger.info(f"Сбор метрик из Prometheus для {service_name} за {time_window}...")
        
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "error_rate": None,
            "request_latency": None,
            "availability": None
        }
        
        # Запросы PromQL для различных метрик
        queries = {
            "cpu_usage": f'avg(rate(container_cpu_usage_seconds_total{{container="{service_name}"}}[{time_window}])) * 100',
            "memory_usage": f'avg(container_memory_usage_bytes{{container="{service_name}"}}) / 1024 / 1024',
            "error_rate": f'sum(rate(http_requests_total{{service="{service_name}",status=~"5.."}}[{time_window}])) / sum(rate(http_requests_total{{service="{service_name}"}}[{time_window}])) * 100',
            "request_latency": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[{time_window}]))',
            "availability": f'avg_over_time(up{{job="{service_name}"}}[{time_window}]) * 100'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                for metric_name, query in queries.items():
                    try:
                        url = f"{settings.prometheus_url}/api/v1/query"
                        params = {"query": query}
                        
                        async with session.get(url, params=params, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data["status"] == "success" and data["data"]["result"]:
                                    value = float(data["data"]["result"][0]["value"][1])
                                    metrics[metric_name] = round(value, 2)
                                    
                    except Exception as e:
                        logger.debug(f"Не удалось получить метрику {metric_name}: {e}")
                        continue
            
            logger.info(f"Собраны метрики для {service_name}: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик из Prometheus: {e}")
            return metrics


# Глобальный экземпляр коллектора данных
data_collector = DataCollector()


async def analyze_logs(service_name: str, time_window: str) -> LogAnalysisResult:
    """
    Анализ логов для сервиса с использованием реальных данных.
    
    Args:
        service_name: Имя сервиса для анализа
        time_window: Временное окно
        
    Returns:
        LogAnalysisResult с результатами анализа
    """
    logger.info(f"Анализ логов для {service_name} за {time_window}...")
    
    # Собираем реальные логи из Elasticsearch
    logs = await data_collector.collect_logs_from_elasticsearch(service_name, time_window)
    
    if not logs:
        logger.info(f"Логи для {service_name} не найдены, возвращаем пустой результат")
        return LogAnalysisResult(
            summary="Логи не найдены",
            root_cause="Нет данных для анализа",
            severity=SeverityLevel.LOW,
            relevant_logs=[]
        )
    
    # Форматируем логи для анализа AI
    logs_text = "\n".join([
        f"[{log.get('timestamp', 'N/A')}] [{log.get('level', 'N/A')}] {log.get('message', '')}"
        for log in logs[:50]  # Ограничиваем количество для AI
    ])
    
    # Вызов AI для анализа
    analysis_result = await ai_service.analyze_logs_with_llm(logs_text)
    logger.info(f"Результат анализа логов: {analysis_result.summary}")
    
    return analysis_result


async def analyze_metrics(service_name: str, time_window: str) -> MetricsAnomalyResult:
    """
    Анализ метрик для сервиса с использованием реальных данных.
    
    Args:
        service_name: Имя сервиса для анализа
        time_window: Временное окно
        
    Returns:
        MetricsAnomalyResult с результатами анализа
    """
    logger.info(f"Анализ метрик для {service_name} за {time_window}...")
    
    # Собираем реальные метрики из Prometheus
    metrics = await data_collector.collect_metrics_from_prometheus(service_name, time_window)
    
    # Определяем аномалии на основе пороговых значений
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
    
    # Если нет данных метрик, устанавливаем низкий anomaly_score
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
    
    Args:
        log_result: Результат анализа логов
        metrics_result: Результат анализа метрик
        
    Returns:
        RemediationPlan с планом исправления
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
    Запускает полный цикл анализа для сервиса.
    
    Args:
        service_name: Имя сервиса для анализа
        time_window: Временное окно для анализа
    """
    try:
        # Шаг 1: Анализ метрик
        metrics_anomaly = await analyze_metrics(service_name, time_window)
        
        if metrics_anomaly.anomaly_score > 0.7:
            await telegram_service.send_message(
                f"⚠️ Обнаружена аномалия в метриках *{service_name}*:\n{metrics_anomaly.description}"
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
                    f"ℹ️ Проблема в *{service_name}* не требует немедленного вмешательства.\n"
                    f"Уровень: {log_analysis.severity.value}\n"
                    f"Описание: {log_analysis.summary}"
                )
        elif metrics_anomaly.anomaly_score > 0.5:
            # Средний уровень - только уведомление
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
    
    Args:
        plan_id: ID плана
        approved: Утвержден ли план
        reason: Причина отклонения (опционально)
        
    Returns:
        Сообщение о результате
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
        
        # Запуск Ansible плейбука
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
