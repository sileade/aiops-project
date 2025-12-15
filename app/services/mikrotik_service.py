"""
Сервис для управления маршрутизаторами MikroTik.
"""
import routeros_api
from app.utils.logger import logger
from config.settings import settings

def get_mikrotik_connection():
    """Устанавливает соединение с MikroTik."""
    try:
        connection = routeros_api.RouterOsApiPool(
            settings.mikrotik_host,
            username=settings.mikrotik_user,
            password=settings.mikrotik_password,
            port=settings.mikrotik_port,
            plaintext_login=True
        )
        return connection.get_api()
    except Exception as e:
        logger.error(f"Ошибка подключения к MikroTik: {e}")
        raise

async def get_mikrotik_system_info():
    """Получает системную информацию с MikroTik."""
    api = get_mikrotik_connection()
    try:
        info = api.get_resource("/system/resource").get()
        return info[0]
    finally:
        api.disconnect()

async def reboot_mikrotik():
    """Перезагружает MikroTik."""
    api = get_mikrotik_connection()
    try:
        api.get_resource("/system/reboot").call()
        return {"status": "rebooting"}
    finally:
        api.disconnect()
