# app/services/ansible_service.py

import logging
import os
import subprocess
from typing import Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

class AnsibleService:
    def __init__(self):
        self.playbooks_dir = settings.PLAYBOOKS_DIR
        self.inventory_dir = os.path.join(os.path.dirname(self.playbooks_dir), 'inventory')
        os.makedirs(self.inventory_dir, exist_ok=True)

    def run_playbook(self, playbook_path: str, device_type: str, device_host: str) -> Tuple[bool, str]:
        """
        Выполняет указанный Ansible плейбук на целевом устройстве.

        :param playbook_path: Абсолютный путь к файлу плейбука.
        :param device_type: Тип устройства ('mikrotik' или 'unifi').
        :param device_host: IP-адрес или хостнейм устройства.
        :return: Кортеж (успех, вывод).
        """
        if not os.path.exists(playbook_path):
            error_msg = f"Плейбук не найден по пути: {playbook_path}"
            logger.error(error_msg)
            return False, error_msg

        # Создание временного inventory файла
        inventory_content = self._create_inventory(device_type, device_host)
        inventory_path = os.path.join(self.inventory_dir, f"hosts_{device_host}.ini")
        with open(inventory_path, "w") as f:
            f.write(inventory_content)

        command = [
            "ansible-playbook",
            "-i", inventory_path,
            playbook_path,
            "-e", f"ansible_user={settings.MIKROTIK_USER if device_type == 'mikrotik' else settings.UNIFI_USER}",
            "-e", f"ansible_password={settings.MIKROTIK_PASSWORD if device_type == 'mikrotik' else settings.UNIFI_PASSWORD}",
            "-e", f"ansible_network_os=community.routeros.routeros" if device_type == 'mikrotik' else "",
        ]
        # Удаляем пустые строки из команды
        command = [item for item in command if item]

        try:
            logger.info(f"Выполнение плейбука: {' '.join(command)}")
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True, # Выбросит исключение, если команда завершится с ошибкой
                timeout=300 # 5 минут таймаут
            )
            output = process.stdout
            logger.info(f"Плейбук успешно выполнен для {device_host}.\nВывод:\n{output}")
            return True, output

        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout
            logger.error(f"Ошибка выполнения плейбука для {device_host}.\nВывод:\n{error_output}")
            return False, error_output
        except subprocess.TimeoutExpired as e:
            error_msg = f"Таймаут выполнения плейбука для {device_host}."
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Непредвиденная ошибка при выполнении плейбука: {e}"
            logger.error(error_msg)
            return False, error_msg
        finally:
            # Удаление временного inventory файла
            if os.path.exists(inventory_path):
                os.remove(inventory_path)

    def _create_inventory(self, device_type: str, device_host: str) -> str:
        """
        Создает содержимое inventory файла для Ansible.
        """
        if device_type == 'mikrotik':
            return f"[mikrotik_devices]\n{device_host} ansible_host={device_host}"
        elif device_type == 'unifi':
            # Для UniFi модулей часто требуется указывать контроллер, а не само устройство
            return f"[unifi_controllers]\n{settings.UNIFI_HOST} ansible_host={settings.UNIFI_HOST}"
        else:
            raise ValueError("Неподдерживаемый тип устройства")

# Пример использования
if __name__ == '__main__':
    # Предполагается, что плейбук уже сгенерирован
    # Создадим фейковый плейбук для теста
    playbook_content_mikrotik = """
---
- name: Test MikroTik Connection
  hosts: all
  gather_facts: no
  tasks:
    - name: Ping MikroTik device
      community.routeros.command:
        commands: /ping 8.8.8.8 count=1
"""
    playbook_path_test = "/home/ubuntu/aiops_project/data/playbooks/test_playbook.yml"
    with open(playbook_path_test, "w") as f:
        f.write(playbook_content_mikrotik)

    ansible_runner = AnsibleService()
    
    # Замените на реальный хост вашего MikroTik
    mikrotik_host_test = settings.MIKROTIK_HOST

    success, output_result = ansible_runner.run_playbook(playbook_path_test, 'mikrotik', mikrotik_host_test)

    print(f"\n--- Результат выполнения плейбука ---")
    print(f"Успех: {success}")
    print(f"Вывод:\n{output_result}")

    # Очистка
    os.remove(playbook_path_test)
