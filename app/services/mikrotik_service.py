"""
Сервис для управления маршрутизаторами MikroTik.
"""
from typing import Optional, Dict, Any
from app.utils.logger import logger
from config.settings import settings

# Ленивый импорт routeros_api
routeros_api = None


def _get_routeros_api():
    """Ленивая загрузка routeros_api."""
    global routeros_api
    if routeros_api is None:
        try:
            import routeros_api as _routeros_api
            routeros_api = _routeros_api
        except ImportError:
            logger.warning("routeros_api не установлен. MikroTik интеграция недоступна.")
            return None
    return routeros_api


def get_mikrotik_connection():
    """Устанавливает соединение с MikroTik."""
    api_module = _get_routeros_api()
    if api_module is None:
        raise ImportError("routeros_api не установлен. Установите: pip install routeros-api")
    
    host = getattr(settings, 'mikrotik_host', '') or ''
    user = getattr(settings, 'mikrotik_user', 'admin')
    password = getattr(settings, 'mikrotik_password', '')
    port = getattr(settings, 'mikrotik_port', 8728)
    
    if not host:
        raise ValueError("MikroTik хост не настроен")
    
    try:
        connection = api_module.RouterOsApiPool(
            host,
            username=user,
            password=password,
            port=port,
            plaintext_login=True
        )
        return connection.get_api()
    except Exception as e:
        logger.error(f"Ошибка подключения к MikroTik: {e}")
        raise


async def get_mikrotik_system_info() -> Dict[str, Any]:
    """Получает системную информацию с MikroTik."""
    api_module = _get_routeros_api()
    if api_module is None:
        return {"error": "routeros_api не установлен"}
    
    host = getattr(settings, 'mikrotik_host', '')
    if not host:
        return {"error": "MikroTik хост не настроен"}
    
    try:
        api = get_mikrotik_connection()
        try:
            info = api.get_resource("/system/resource").get()
            return info[0] if info else {}
        finally:
            try:
                api.disconnect()
            except:
                pass
    except Exception as e:
        logger.error(f"Ошибка получения информации MikroTik: {e}")
        return {"error": str(e)}


async def reboot_mikrotik() -> Dict[str, str]:
    """Перезагружает MikroTik."""
    api_module = _get_routeros_api()
    if api_module is None:
        return {"error": "routeros_api не установлен"}
    
    host = getattr(settings, 'mikrotik_host', '')
    if not host:
        return {"error": "MikroTik хост не настроен"}
    
    try:
        api = get_mikrotik_connection()
        try:
            api.get_resource("/system/reboot").call()
            return {"status": "rebooting"}
        finally:
            try:
                api.disconnect()
            except:
                pass
    except Exception as e:
        logger.error(f"Ошибка перезагрузки MikroTik: {e}")
        return {"error": str(e)}
