import os
from app.services.ai_service import AIService

class CodeAnalysisService:
    """Сервис для анализа и исправления ошибок в коде"""

    def __init__(self):
        self.ai_service = AIService()

    def analyze_code(self, file_path: str) -> dict:
        """Анализирует код на наличие ошибок и уязвимостей"""
        with open(file_path, 'r') as f:
            code = f.read()

        prompt = f"""Проанализируй следующий код на наличие ошибок, уязвимостей и проблем с производительностью. Предоставь подробный отчет в формате JSON.

Код:
```python
{code}
```

Отчет в формате JSON:
"""
        response = self.ai_service.generate_text(prompt)
        return response

    def fix_code(self, file_path: str, issues: list) -> str:
        """Исправляет ошибки в коде на основе отчета"""
        with open(file_path, 'r') as f:
            code = f.read()

        prompt = f"""Исправь следующие ошибки в коде. Верни только исправленный код, без комментариев.

Код:
```python
{code}
```

Ошибки:
{issues}

Исправленный код:
"""
        fixed_code = self.ai_service.generate_text(prompt)
        with open(file_path, 'w') as f:
            f.write(fixed_code)
        return fixed_code
