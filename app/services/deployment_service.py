import os
import subprocess

class DeploymentService:
    """Сервис для автоматического развертывания и обновления"""

    def __init__(self):
        self.project_dir = "/home/ubuntu/aiops_project"

    def pull_latest_changes(self) -> str:
        """Загружает последние изменения из Git"""
        command = ["git", "pull"]
        result = subprocess.run(command, cwd=self.project_dir, capture_output=True, text=True)
        return result.stdout

    def restart_services(self) -> str:
        """Перезапускает сервисы через Docker Compose"""
        command = ["docker-compose", "up", "-d", "--build"]
        result = subprocess.run(command, cwd=self.project_dir, capture_output=True, text=True)
        return result.stdout

    def run_deployment_cycle(self) -> dict:
        """Запускает полный цикл развертывания"""
        pull_result = self.pull_latest_changes()
        restart_result = self.restart_services()
        return {
            "pull_result": pull_result,
            "restart_result": restart_result
        }
