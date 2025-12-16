"""
Сервис для выполнения Ansible плейбуков.
"""

import asyncio
import datetime
import os
import subprocess
import tempfile
from typing import Any

from app.models.schemas import ActionStatus, RemediationPlan
from app.utils.logger import logger
from config.settings import settings

from .system_service import save_plan_to_db
from .telegram_service import send_message

# Ленивый импорт ansible_runner (может быть не установлен)
ansible_runner = None


def _get_ansible_runner():
    """Ленивая загрузка ansible_runner."""
    global ansible_runner
    if ansible_runner is None:
        try:
            import ansible_runner as ar

            ansible_runner = ar
        except ImportError:
            logger.warning("ansible_runner не установлен. Будет использован subprocess fallback.")
    return ansible_runner


async def run_playbook_async(plan: RemediationPlan):
    """Асинхронно запускает Ansible плейбук в отдельном потоке."""
    loop = asyncio.get_running_loop()

    plan.status = ActionStatus.EXECUTING
    plan.executed_at = datetime.datetime.now()
    await save_plan_to_db(plan)

    try:
        # Запускаем синхронную функцию в отдельном потоке
        result = await loop.run_in_executor(
            None, run_ansible_playbook, plan.playbook_yaml, settings.ansible_inventory_path
        )

        if result["rc"] == 0:
            plan.status = ActionStatus.COMPLETED
            plan.execution_result = result["stdout"]
            await save_plan_to_db(plan)
            await send_message(f"✅ План *{plan.title}* успешно выполнен!")
            logger.info(f"Плейбук для плана {plan.plan_id} успешно выполнен.")
        else:
            raise Exception(f"Ansible вернул код ошибки: {result['rc']}\n{result['stdout']}")

    except Exception as e:
        logger.error(f"Ошибка выполнения плейбука для плана {plan.plan_id}: {e}")
        plan.status = ActionStatus.FAILED
        plan.execution_result = str(e)
        await save_plan_to_db(plan)
        await send_message(f"❌ Ошибка выполнения плана *{plan.title}*:\n`{e}`")


def run_ansible_playbook(playbook_content: str, inventory_path: str) -> dict[str, Any]:
    """
    Синхронная функция для запуска Ansible плейбука.
    Поддерживает два режима: через ansible_runner или через subprocess.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "project")
        os.makedirs(project_dir)

        playbook_path = os.path.join(project_dir, "playbook.yml")

        with open(playbook_path, "w") as f:
            f.write(playbook_content)

        # Проверяем/создаем inventory файл
        if not os.path.exists(inventory_path):
            logger.warning(f"Файл инвентаря не найден: {inventory_path}. Создаю локальный.")
            inventory_path = os.path.join(tmpdir, "inventory")
            with open(inventory_path, "w") as f:
                f.write("[all]\nlocalhost ansible_connection=local\n")

        logger.info(f"Запуск плейбука: {playbook_path} с инвентарем: {inventory_path}")

        # Пробуем использовать ansible_runner
        runner = _get_ansible_runner()

        if runner is not None:
            return _run_with_ansible_runner(runner, tmpdir, inventory_path)
        else:
            return _run_with_subprocess(playbook_path, inventory_path)


def _run_with_ansible_runner(runner, tmpdir: str, inventory_path: str) -> dict[str, Any]:
    """Запуск через ansible_runner."""
    result = runner.run(private_data_dir=tmpdir, playbook="playbook.yml", inventory=inventory_path)

    stdout = ""
    if hasattr(result, "stdout") and result.stdout:
        stdout = result.stdout.read() if hasattr(result.stdout, "read") else str(result.stdout)

    return {
        "status": result.status,
        "rc": result.rc if result.rc is not None else 1,
        "stdout": stdout,
    }


def _run_with_subprocess(playbook_path: str, inventory_path: str) -> dict[str, Any]:
    """Fallback: запуск через subprocess."""
    try:
        result = subprocess.run(
            ["ansible-playbook", "-i", inventory_path, playbook_path],
            capture_output=True,
            text=True,
            timeout=300,  # 5 минут таймаут
        )

        return {
            "status": "successful" if result.returncode == 0 else "failed",
            "rc": result.returncode,
            "stdout": result.stdout + result.stderr,
        }
    except FileNotFoundError:
        return {
            "status": "failed",
            "rc": 1,
            "stdout": "Ansible не установлен в системе. Установите: pip install ansible",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "rc": 1,
            "stdout": "Таймаут выполнения плейбука (5 минут)",
        }
