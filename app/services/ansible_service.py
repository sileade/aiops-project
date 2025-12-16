# app/services/ansible_service.py

import contextlib
import logging
import os
import subprocess
import tempfile

from config.settings import settings

logger = logging.getLogger(__name__)


class AnsibleService:
    def __init__(self):
        # Используем безопасные пути с fallback
        self.playbooks_dir = os.getenv("ANSIBLE_PLAYBOOK_DIR", settings.PLAYBOOKS_DIR)

        # Пробуем создать директорию для inventory, если не получается - используем temp
        try:
            self.inventory_dir = os.path.join(os.path.dirname(self.playbooks_dir), "inventory")
            os.makedirs(self.inventory_dir, exist_ok=True)
        except (PermissionError, OSError):
            # Fallback на временную директорию
            self.inventory_dir = tempfile.mkdtemp(prefix="ansible_inventory_")
            logger.warning(f"Используется временная директория для inventory: {self.inventory_dir}")

    def run_playbook(self, playbook_path: str, device_type: str, device_host: str) -> tuple[bool, str]:
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

        try:
            with open(inventory_path, "w") as f:
                f.write(inventory_content)
        except (PermissionError, OSError):
            # Fallback на временный файл
            fd, inventory_path = tempfile.mkstemp(suffix=".ini", prefix="inventory_")
            with os.fdopen(fd, "w") as f:
                f.write(inventory_content)

        # Получаем учетные данные безопасно
        mikrotik_user = getattr(settings, "mikrotik_user", "") or getattr(settings, "MIKROTIK_USER", "admin")
        mikrotik_password = getattr(settings, "mikrotik_password", "") or getattr(settings, "MIKROTIK_PASSWORD", "")
        unifi_user = getattr(settings, "unifi_user", "") or getattr(settings, "UNIFI_USER", "admin")
        unifi_password = getattr(settings, "unifi_password", "") or getattr(settings, "UNIFI_PASSWORD", "")

        command = [
            "ansible-playbook",
            "-i",
            inventory_path,
            playbook_path,
            "-e",
            f"ansible_user={mikrotik_user if device_type == 'mikrotik' else unifi_user}",
            "-e",
            f"ansible_password={mikrotik_password if device_type == 'mikrotik' else unifi_password}",
        ]

        if device_type == "mikrotik":
            command.extend(["-e", "ansible_network_os=community.routeros.routeros"])

        # Удаляем пустые строки из команды
        command = [item for item in command if item]

        try:
            logger.info(f"Выполнение плейбука: {' '.join(command)}")
            process = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=300  # 5 минут таймаут
            )
            output = process.stdout
            logger.info(f"Плейбук успешно выполнен для {device_host}.\nВывод:\n{output}")
            return True, output

        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout
            logger.error(f"Ошибка выполнения плейбука для {device_host}.\nВывод:\n{error_output}")
            return False, error_output
        except subprocess.TimeoutExpired:
            error_msg = f"Таймаут выполнения плейбука для {device_host}."
            logger.error(error_msg)
            return False, error_msg
        except FileNotFoundError:
            error_msg = "Ansible не установлен в системе. Установите: pip install ansible"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Непредвиденная ошибка при выполнении плейбука: {e}"
            logger.error(error_msg)
            return False, error_msg
        finally:
            # Удаление временного inventory файла
            if os.path.exists(inventory_path):
                with contextlib.suppress(OSError):
                    os.remove(inventory_path)

    def _create_inventory(self, device_type: str, device_host: str) -> str:
        """
        Создает содержимое inventory файла для Ansible.
        """
        if device_type == "mikrotik":
            return f"[mikrotik_devices]\n{device_host} ansible_host={device_host}\n"
        elif device_type == "unifi":
            unifi_host = getattr(settings, "unifi_host", "") or getattr(settings, "UNIFI_HOST", device_host)
            return f"[unifi_controllers]\n{unifi_host} ansible_host={unifi_host}\n"
        else:
            # Общий случай
            return f"[all]\n{device_host} ansible_host={device_host}\n"
