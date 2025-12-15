"""
Сервис для управления коммутаторами Ubiquiti UniFi.
"""
from unificontrol import UnifiClient
from app.utils.logger import logger
from config.settings import settings

def get_unifi_connection():
    """Устанавливает соединение с UniFi Controller."""
    try:
        client = UnifiClient(
            host=settings.unifi_host,
            username=settings.unifi_user,
            password=settings.unifi_password,
            port=settings.unifi_port,
            site=settings.unifi_site,
            ssl_verify=False  # Измените на True в production
        )
        return client
    except Exception as e:
        logger.error(f"Ошибка подключения к UniFi: {e}")
        raise

async def get_unifi_devices():
    """Получает список устройств UniFi."""
    client = get_unifi_connection()
    try:
        devices = client.list_devices()
        return devices
    finally:
        client.logout()

async def restart_unifi_device(mac: str):
    """Перезагружает устройство UniFi."""
    client = get_unifi_connection()
    try:
        client.restart_device(mac)
        return {"status": "restarting", "mac": mac}
    finally:
        client.logout()
