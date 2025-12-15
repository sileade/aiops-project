'''
Сервисный модуль для взаимодействия с Proxmox VE API.

Этот модуль предоставляет функции для:
- Подключения к Proxmox.
- Получения статуса кластера, нод и виртуальных машин.
- Управления виртуальными машинами (старт, стоп, перезагрузка).
'''

import logging
from proxmoxer import ProxmoxAPI

from config.settings import settings

logger = logging.getLogger(__name__)

class ProxmoxService:
    def __init__(self):
        self.proxmox = None
        try:
            # Proxmoxer поддерживает аутентификацию по токену (предпочтительно) или по паролю
            self.proxmox = ProxmoxAPI(
                settings.PROXMOX_HOST,
                user=settings.PROXMOX_USER,
                token_name=settings.PROXMOX_TOKEN_NAME, # Имя токена API
                token_value=settings.PROXMOX_TOKEN_VALUE, # Значение токена API
                verify_ssl=False # Установите True, если у вас валидный SSL сертификат
            )
            # Проверка соединения
            self.proxmox.version.get()
            logger.info("Успешное подключение к Proxmox API.")
        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox API: {e}")

    def get_cluster_status(self) -> dict:
        '''Возвращает статус всего кластера.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.cluster.status.get()
        except Exception as e:
            logger.error(f"Ошибка получения статуса кластера Proxmox: {e}")
            return {'error': str(e)}

    def get_all_nodes(self) -> list:
        '''Возвращает список всех нод в кластере.'''
        if not self.proxmox:
            return []
        try:
            return self.proxmox.nodes.get()
        except Exception as e:
            logger.error(f"Ошибка получения списка нод Proxmox: {e}")
            return []

    def get_all_vms(self) -> list:
        '''Возвращает список всех VM и контейнеров в кластере.'''
        if not self.proxmox:
            return []
        try:
            return self.proxmox.cluster.resources.get(type='vm')
        except Exception as e:
            logger.error(f"Ошибка получения списка VM/контейнеров: {e}")
            return []

    def get_vm_status(self, node: str, vmid: int) -> dict:
        '''Возвращает статус конкретной VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.current.get()
        except Exception as e:
            logger.error(f"Ошибка получения статуса VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def start_vm(self, node: str, vmid: int) -> dict:
        '''Запускает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.start.post()
        except Exception as e:
            logger.error(f"Ошибка запуска VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def stop_vm(self, node: str, vmid: int) -> dict:
        '''Останавливает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.stop.post()
        except Exception as e:
            logger.error(f"Ошибка остановки VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

    def reboot_vm(self, node: str, vmid: int) -> dict:
        '''Перезагружает VM.'''
        if not self.proxmox:
            return {'error': 'Нет подключения к Proxmox'}
        try:
            return self.proxmox.nodes(node).qemu(vmid).status.reboot.post()
        except Exception as e:
            logger.error(f"Ошибка перезагрузки VM {vmid} на ноде {node}: {e}")
            return {'error': str(e)}

# Пример использования
if __name__ == '__main__':
    # Для этого теста убедитесь, что переменные окружения для Proxmox установлены
    proxmox_service = ProxmoxService()

    if proxmox_service.proxmox:
        print("--- Статус Кластера ---")
        cluster_status = proxmox_service.get_cluster_status()
        print(cluster_status)

        print("\n--- Список Нод ---")
        nodes = proxmox_service.get_all_nodes()
        if nodes:
            for node in nodes:
                print(f"- Нода: {node['node']}, Статус: {node['status']})")

        print("\n--- Список VM ---")
        vms = proxmox_service.get_all_vms()
        if vms:
            for vm in vms:
                print(f"- VM ID: {vm['vmid']}, Имя: {vm['name']}, Нода: {vm['node']}, Статус: {vm['status']})")

            # Пример управления первой VM в списке
            if vms:
                test_vm = vms[0]
                test_node = test_vm['node']
                test_vmid = test_vm['vmid']
                print(f"\n--- Тестирование управления VM {test_vmid} на ноде {test_node} ---")
                vm_status = proxmox_service.get_vm_status(test_node, test_vmid)
                print(f"Текущий статус: {vm_status.get('status')}")

                # # Осторожно: эти команды реально управляют VM
                # print("Попытка остановки VM...")
                # stop_result = proxmox_service.stop_vm(test_node, test_vmid)
                # print(stop_result)
                #
                # import time
                # time.sleep(10) # Ждем
                #
                # print("Попытка запуска VM...")
                # start_result = proxmox_service.start_vm(test_node, test_vmid)
                # print(start_result)
