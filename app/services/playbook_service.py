# app/services/playbook_service.py

import logging
import os
import uuid
from datetime import datetime

from config.settings import settings
from app.services.qwen_service import QwenService

logger = logging.getLogger(__name__)

class PlaybookService:
    def __init__(self):
        self.ai_service = QwenService()
        self.playbooks_dir = settings.PLAYBOOKS_DIR
        os.makedirs(self.playbooks_dir, exist_ok=True)

    def generate_playbook(self, problem_description: str, device_type: str) -> str | None:
        """
        Генерирует Ansible плейбук на основе описания проблемы.

        :param problem_description: Детальное описание проблемы, полученное от AI.
        :param device_type: Тип устройства ('mikrotik' или 'unifi').
        :return: Путь к сгенерированному файлу плейбука или None.
        """
        prompt = self._create_playbook_generation_prompt(problem_description, device_type)

        try:
            logger.info(f"Запрос на генерацию плейбука для {device_type}...")
            playbook_content = self.ai_service.interpret_command(prompt)

            if not playbook_content or not playbook_content.strip().startswith("---"):
                logger.warning("AI не смог сгенерировать корректный плейбук.")
                return None

            # Сохранение плейбука в файл
            playbook_filename = f"playbook_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.yml"
            playbook_path = os.path.join(self.playbooks_dir, playbook_filename)

            with open(playbook_path, "w", encoding="utf-8") as f:
                f.write(playbook_content)

            logger.info(f"Плейбук успешно сгенерирован и сохранен: {playbook_path}")
            return playbook_path

        except Exception as e:
            logger.error(f"Ошибка при генерации или сохранении плейбука: {e}")
            return None

    def _create_playbook_generation_prompt(self, problem_description: str, device_type: str) -> str:
        """
        Создает промпт для модели Qwen для генерации плейбука.
        """
        if device_type == 'mikrotik':
            modules = "community.routeros.command, community.routeros.api"
            example_task = "- name: Перезагрузить маршрутизатор\n  community.routeros.command:\n    commands: /system reboot"
        elif device_type == 'unifi':
            modules = "community.unifi.unifi_device"
            example_task = "- name: Перезапустить точку доступа\n  community.unifi.unifi_device:\n    mac: '{{ device_mac }}'\n    state: restart"
        else:
            raise ValueError("Неподдерживаемый тип устройства")

        prompt = f"""
        **Задача:** Создай Ansible плейбук для решения следующей проблемы на устройстве типа '{device_type}'.

        **Описание Проблемы:**
        {problem_description}

        **Требования к Плейбуку:**
        1.  Плейбук должен быть в формате YAML и начинаться с `---`.
        2.  Используй только официальные Ansible модули для `{device_type}` (например, `{modules}`).
        3.  Плейбук должен быть максимально простым и решать только указанную проблему.
        4.  Включи `hosts: all` и `gather_facts: no`.
        5.  Добавь осмысленные имена для задач (`- name: ...`).
        6.  Не включай в ответ ничего, кроме самого кода плейбука.

        **Пример Задачи:**
        ```yaml
        {example_task}
        ```

        **Сгенерируй плейбук для решения проблемы:**
        "
        """
        return prompt.strip()

# Пример использования
if __name__ == '__main__':
    playbook_gen = PlaybookService()
    
    # Пример 1: Проблема с MikroTik
    problem_mikrotik = "Пользователи жалуются на высокий пинг. Анализ показал, что firewall filter заблокировал легитимный трафик на порту 443. Нужно удалить правило, блокирующее порт 443."
    playbook_path_mikrotik = playbook_gen.generate_playbook(problem_mikrotik, 'mikrotik')
    if playbook_path_mikrotik:
        print(f"\n--- Плейбук для MikroTik ---\nПуть: {playbook_path_mikrotik}")
        with open(playbook_path_mikrotik, 'r') as f:
            print(f.read())

    # Пример 2: Проблема с UniFi
    problem_unifi = "Точка доступа 'AP-Lobby' зависла и не пропускает клиентов. Требуется ее перезагрузить. MAC-адрес точки: 'B4:FB:E4:XX:XX:XX'."
    playbook_path_unifi = playbook_gen.generate_playbook(problem_unifi, 'unifi')
    if playbook_path_unifi:
        print(f"\n--- Плейбук для UniFi ---\nПуть: {playbook_path_unifi}")
        with open(playbook_path_unifi, 'r') as f:
            print(f.read())

