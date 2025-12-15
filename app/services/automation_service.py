"""
Сервис для выполнения Ansible плейбуков.
"""
import ansible_runner
import tempfile
import os
import asyncio

from app.models.schemas import RemediationPlan, ActionStatus
from app.utils.logger import logger
from config.settings import settings
from .system_service import save_plan_to_db
from .telegram_service import send_message

async def run_playbook_async(plan: RemediationPlan):
    """Асинхронно запускает Ansible плейбук в отдельном потоке."""
    loop = asyncio.get_running_loop()
    
    plan.status = ActionStatus.EXECUTING
    plan.executed_at = datetime.datetime.now()
    await save_plan_to_db(plan)
    
    try:
        # Запускаем синхронную функцию в отдельном потоке, чтобы не блокировать asyncio event loop
        result = await loop.run_in_executor(
            None, 
            run_ansible_playbook, 
            plan.playbook_yaml, 
            settings.ansible_inventory_path
        )
        
        if result["rc"] == 0:
            plan.status = ActionStatus.COMPLETED
            plan.execution_result = result["stdout"]
            await save_plan_to_db(plan)
            await send_message(f"✅ План *{plan.title}* успешно выполнен!")
            logger.info(f"Плейбук для плана {plan.plan_id} успешно выполнен.")
        else:
            raise ansible_runner.RunnerError(result["stdout"])
            
    except Exception as e:
        logger.error(f"Ошибка выполнения плейбука для плана {plan.plan_id}: {e}")
        plan.status = ActionStatus.FAILED
        plan.execution_result = str(e)
        await save_plan_to_db(plan)
        await send_message(f"❌ Ошибка выполнения плана *{plan.title}*:\n`{e}`")

def run_ansible_playbook(playbook_content: str, inventory_path: str):
    """
    Синхронная функция для запуска Ansible плейбука.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "project")
        os.makedirs(project_dir)

        playbook_path = os.path.join(project_dir, "playbook.yml")
        
        with open(playbook_path, "w") as f:
            f.write(playbook_content)
        
        # Проверяем, существует ли inventory файл
        if not os.path.exists(inventory_path):
            logger.warning(f"Файл инвентаря не найден по пути: {inventory_path}. Создаю пустой.")
            with open(inventory_path, "w") as f:
                f.write("[all]\nlocalhost ansible_connection=local")

        logger.info(f"Запуск плейбука: {playbook_path} с инвентарем: {inventory_path}")
        
        runner = ansible_runner.run(
            private_data_dir=tmpdir,
            playbook="playbook.yml",
            inventory=inventory_path
        )

        return {
            "status": runner.status,
            "rc": runner.rc,
            "stdout": runner.stdout.read(),
        }
