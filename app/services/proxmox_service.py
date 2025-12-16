'''
Сервисный модуль для взаимодействия с Proxmox VE API.

Этот модуль предоставляет функции для:
- Подключения к Proxmox.
- Получения статуса кластера, нод и виртуальных машин.
- Управления виртуальными машинами (старт, стоп, перезагрузка).
'''

import logging
from typing import Optional, Dict, List, Any

from config.settings import settings

logger = logging.getLogger(__name__)

# Ленивый импорт proxmoxer
ProxmoxAPI = None


def _get_proxmox_api():
    """Ленивая загрузка ProxmoxAPI."""
    global ProxmoxAPI
    if ProxmoxAPI is None:
        try:
            from proxmoxer import ProxmoxAPI as _ProxmoxAPI
            ProxmoxAPI = _ProxmoxAPI
        except ImportError:
            logger.warning("proxmoxer не установлен. Proxmox интеграция недоступна.")
            return None
    return ProxmoxAPI


class ProxmoxService:
    def __init__(self):
        self.proxmox = None
        
        # Получаем ProxmoxAPI
        api_class = _get_proxmox_api()
        if api_class is None:
            logger.warning("ProxmoxAPI недоступен - proxmoxer не установлен")
            return
        
        # Получаем настройки (поддержка обоих форматов)
        host = getattr(settings, 'proxmox_host', '') or getattr(settings, 'PROXMOX_HOST', '')
        user = getattr(settings, 'proxmox_user', '') or getattr(settings, 'PROXMOX_USER', 'root@pam')
        token_name = getattr(settings, 'proxmox_token_name', '') or getattr(settings, 'PROXMOX_TOKEN_NAME', '')
        token_value = getattr(settings, 'proxmox_token_value', '') or getattr(settings, 'PROXMOX_TOKEN_VALUE', '')
        verify_ssl = getattr(settings, 'proxmox_verify_ssl', False)
        
        if not host:
            logger.info("Proxmox хост не настроен - интеграция отключена")
            return
        
        if not token_name or not token_value:
            logger.warning("Proxmox токен не настроен - интеграция отключена")
            return
            
        try:
            self.proxmox = api_class(
                host,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=verify_ssl
            )
            # Проверка соединения
            self.proxmox.version.get()
            logger.info("Успешное подключение к Proxmox API.")
        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox API: {e}")
            self.proxmox = None

    def get_cluster_status(self) -> Dict[str, Any]:
        '''Возвращает статус всего кластера.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.cluster.status.get()
        except Exception as e:
            logger.error(f"Ошибка получения статуса кластера Proxmox: {e}")
            return {'error': str(e)}

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        '''Возвращает список всех нод в кластере.'''
        if not self.proxmox:
            return []
        try:
            return self.proxmox.nodes.get()
        except Exception as e:
            logger.error(f"Ошибка получения списка нод Proxmox: {e}")
            return []

    def get_all_vms(self) -> List[Dict[str, Any]]:
        '''Возвращает список всех VM и контейнеров в кластере.'''
        if not self.proxmox:
            return []
        try:
            return self.proxmox.cluster.resources.get(type='vm')
        except Exception as e:
            logger.error(f"Ошибка получения списка VM/контейнеров: {e}")
            return []

    def get_vm_status(self, node: str, vmid: int) -> Dict[str, Any]:
        '''Возвращает статус конкретной VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.current.get()
        except Exception as e:
            logger.error(f"Ошибка получения статуса VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def start_vm(self, node: str, vmid: int) -> Dict[str, Any]:
        '''Запускает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.start.post()
        except Exception as e:
            logger.error(f"Ошибка запуска VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def stop_vm(self, node: str, vmid: int) -> Dict[str, Any]:
        '''Останавливает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.stop.post()
        except Exception as e:
            logger.error(f"Ошибка остановки VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def reboot_vm(self, node: str, vmid: int) -> Dict[str, Any]:
        '''Перезагружает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.reboot.post()
        except Exception as e:
            logger.error(f"Ошибка перезагрузки VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}
