"""
Task Deduplication Queue - отслеживает последние 50 задач для предотвращения дубликатов
"""

import threading
import time
from collections import OrderedDict
from typing import Optional


class TaskDeduplicationQueue:
    """
    Очередь для отслеживания последних 50 задач с возможностью пропуска дубликатов.

    Использует OrderedDict для эффективного отслеживания порядка и ограничения размера.
    """

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._queue = OrderedDict()
        self._lock = threading.Lock()

    def add_task(self, task_id: str) -> bool:
        """
        Добавить задачу в очередь.

        Args:
            task_id: ID задачи

        Returns:
            True если задача новая, False если дубликат
        """
        with self._lock:
            if task_id in self._queue:
                # Задача уже существует - обновляем время и возвращаем False
                self._queue[task_id] = time.time()
                return False

            # Добавляем новую задачу
            self._queue[task_id] = time.time()

            # Удаляем старые задачи, если превышен лимит
            if len(self._queue) > self.max_size:
                # Удаляем самую старую задачу
                self._queue.popitem(last=False)

            return True

    def is_duplicate(self, task_id: str) -> bool:
        """
        Проверить, является ли задача дубликатом.

        Args:
            task_id: ID задачи

        Returns:
            True если задача дубликат, False если новая
        """
        with self._lock:
            return task_id in self._queue

    def remove_task(self, task_id: str) -> bool:
        """
        Удалить задачу из очереди.

        Args:
            task_id: ID задачи

        Returns:
            True если задача была удалена, False если не найдена
        """
        with self._lock:
            if task_id in self._queue:
                del self._queue[task_id]
                return True
            return False

    def get_recent_tasks(self) -> list:
        """
        Получить список последних задач.

        Returns:
            Список ID последних задач в порядке добавления
        """
        with self._lock:
            return list(self._queue.keys())

    def clear(self) -> None:
        """Очистить очередь"""
        with self._lock:
            self._queue.clear()

    def size(self) -> int:
        """Получить количество задач в очереди"""
        with self._lock:
            return len(self._queue)
