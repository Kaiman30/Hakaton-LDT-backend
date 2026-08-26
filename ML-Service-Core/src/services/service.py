"""
LLM Service - основной сервис обработки задач с внутренней модульностью.
Использует протоколы для type-safe dependency injection.
"""

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple
from io import BytesIO

from core.base_service import BaseService
from core.base_class.protocols import (
    ILLMConnector,
    IQueueConnector,
    IFileStorageConnector,
    IDBConnector
)
from core.service_factory import register_service
from models.domain_models import TaskStatus  # Updated to use unified domain models
from models.domain_models import PromptService

from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode
from PIL import Image, ImageEnhance


# ============ ВНУТРЕННИЕ КОМПОНЕНТЫ ============

class TaskCoordinator:
    """
    Task coordinator - internal component for managing task lifecycle.

    This class handles the preparation and coordination of tasks received from
    the message queue, including deduplication and metadata extraction.
    """

    def __init__(self, queue: IQueueConnector, dedup_queue):
        """
        Initialize the task coordinator.

        Args:
            queue: Queue connector for message handling
            dedup_queue: Deduplication queue for preventing duplicate processing
        """
        self.queue = queue  # Queue connector for message handling
        self.dedup_queue = dedup_queue  # Deduplication queue for preventing duplicate processing
    
    async def prepare_task_data(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Подготовить данные задачи из Kafka сообщения."""
        task_id = message.get("kafka_key")
        headers = message.get("kafka_headers", {})

        task_data = {
            "task_id": task_id,
            "storage_path": message.get("payload", {}).get("storage_path"),
            "trace_id": headers.get("trace_id", str(uuid.uuid4())),
            "prompt_id": int(headers.get("prompt_id", 3)),
            "original_message": message,
        }

        return task_data
    
    def is_duplicate_task(self, task_id: str) -> bool:
        """Проверить дубликат задачи."""
        return self.dedup_queue.is_duplicate(task_id) if self.dedup_queue else False
    
    def mark_task_processed(self, task_id: str) -> None:
        """Пометить задачу как обрабатываемую."""
        if self.dedup_queue:
            self.dedup_queue.add_task(task_id)


class LLMProcessor:
    """
    LLM processor - internal component for processing tasks with LLM.

    This class handles the interaction with the LLM service, including file
    uploads, chat requests, and response parsing.
    """

    def __init__(self, llm: ILLMConnector, max_retries: int = 2):
        """
        Initialize the LLM processor.

        Args:
            llm: LLM connector for API interactions
            max_retries: Maximum number of retries for failed operations
        """
        self.llm = llm  # LLM connector for API interactions
        self.max_retries = max_retries  # Maximum number of retries for failed operations
    
    async def process(
        self, 
        task_data: Dict[str, Any], 
        file_content: bytes
    ) -> Dict[str, Any]:
        """Обработать задачу с помощью LLM."""
        start_time = time.perf_counter()
        
        try:
            # Загрузить файл в LLM
            filename = task_data["storage_path"].split("/")[-1]
            file_id = await self._upload_file_with_retry(
                file_content, 
                filename, 
                task_data["trace_id"]
            )
            
            # Получить промпт
            prompt = PromptService().get_prompt_by_id(task_data["prompt_id"])
            if not prompt:
                return {"success": False, "error": "Prompt not found"}
            
            # Обработать через LLM
            response = await self.llm.chat(
                prompt=prompt,
                file_ids=[file_id] if file_id else []
            )
            
            # Очистка
            if file_id:
                await self.llm.delete_file(file_id)
            
            # Парсинг результата
            result = self._parse_response(response)
            result["processing_time_ms"] = (time.perf_counter() - start_time) * 1000
            
            return result
            
        except Exception as e:
            return {
                "success": False, 
                "error": str(e),
                "processing_time_ms": (time.perf_counter() - start_time) * 1000
            }
    
    async def _upload_file_with_retry(
        self, 
        file_data: bytes, 
        filename: str, 
        trace_id: str
    ) -> Optional[str]:
        """Загрузить файл с повторными попытками."""
        for attempt in range(self.max_retries + 1):
            try:
                return await self.llm.upload_file(
                    file_data=file_data,
                    filename=filename,
                    timeout=30.0
                )
            except Exception as e:
                if "timeout" in str(e).lower() and attempt < self.max_retries:
                    await self._restart_llm()
                else:
                    raise
    
    async def _restart_llm(self) -> None:
        """Перезапустить LLM коннектор."""
        await self.llm.shutdown()
        await self.llm.initialize()
    
    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Распарсить ответ LLM."""
        content = response.get("response", "")

        if not content.strip():
            return {"success": False, "error": "Empty response"}

        if content.strip().startswith("{"):
            try:
                parsed = json.loads(content)
                status = parsed.get("Статус", parsed.get("status", ""))

                if status.lower() in ["успешно", "success"]:
                    return {"success": True, "result": parsed}
                else:
                    return {"success": False, "error": f"Invalid status: {status}"}
            except json.JSONDecodeError:
                return {"success": False, "error": "Invalid JSON"}

        return {"success": True, "result": {"raw_response": content}}


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТКИ ШТРИХ-КОДОВ ============

def _enhance_barcode_image(
    img: Image.Image,
    brightness: float = 0.8,
    contrast: float = 150,
    binarize: bool = False,
    binarize_threshold: int = 128
) -> Image.Image:
    """
    Улучшает изображение для лучшего распознавания штрих-кода
    """
    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness)

    if contrast != 100:
        contrast_factor = contrast / 100.0
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_factor)

    if binarize:
        if img.mode != 'L':
            img = img.convert('L')
        img = img.point(lambda x: 255 if x > binarize_threshold else 0, '1')
        img = img.convert('RGB')

    return img


def _extract_barcode_image(
    img: Image.Image,
    rect: Tuple[int, int, int, int],
    margin: int = 80
) -> Image.Image:
    """
    Вырезает область со штрих-кодом с отступами
    """
    left, top, width, height = rect
    img_width, img_height = img.size

    crop_left = max(0, left - margin)
    crop_top = max(0, top - margin)
    crop_right = min(img_width, left + width + margin)
    crop_bottom = min(img_height, top + height + margin)

    return img.crop((crop_left, crop_top, crop_right, crop_bottom))


def _find_barcodes_in_pdf_bytes(
    pdf_bytes: bytes,
    brightness: float = 0.8,
    contrast: float = 150,
    binarize: bool = False,
    binarize_threshold: int = 128,
    margin: int = 80,
    allowed_types: List[str] = None,
    rotate: bool = True
) -> List[Dict[str, Any]]:
    """
    Ищет штрих-коды в PDF данных
    """
    if allowed_types is None:
        allowed_types = ['I25']

    angles_to_check = [0, 90, 180, 270] if rotate else [0]

    images = convert_from_bytes(pdf_bytes, dpi=200)

    found_barcodes = []
    seen_codes = set()

    for page_num, img in enumerate(images):
        enhanced_img = _enhance_barcode_image(
            img, brightness, contrast, binarize, binarize_threshold
        )

        for angle in angles_to_check:
            if angle:
                rotated_img = enhanced_img.rotate(angle, expand=True)
            else:
                rotated_img = enhanced_img

            codes = decode(rotated_img)

            for code in codes:
                if code.type not in allowed_types:
                    continue

                data = code.data.decode('utf-8')

                if data in seen_codes:
                    continue
                seen_codes.add(data)

                rect = (code.rect.left, code.rect.top, code.rect.width, code.rect.height)
                barcode_img = _extract_barcode_image(rotated_img, rect, margin)

                found_barcodes.append({
                    'data': data,
                    'type': code.type,
                    'angle': angle,
                    'page': page_num + 1,
                    'rect': rect,
                    'image': barcode_img,
                })

    return found_barcodes


class BarcodeProcessor:
    """
    Процессор для обработки штрих-кодов.

    Принимает callable-функции для работы с LLM, что делает его независимым
    от конкретной реализации коннектора.
    """

    def __init__(
        self,
        upload_file_fn: Callable[[bytes, str], Awaitable[Optional[str]]],
        chat_fn: Callable[[str, List[str]], Awaitable[Dict[str, Any]]],
        delete_file_fn: Callable[[str], Awaitable[None]],
        get_prompt_fn: Callable[[int], Optional[str]],
        logger=None,
        executor: Optional[ThreadPoolExecutor] = None
    ):
        """
        Инициализировать процессор штрих-кодов.

        Args:
            upload_file_fn: Функция для загрузки файла (file_data, filename) -> file_id
            chat_fn: Функция для чата с LLM (prompt, file_ids) -> response dict
            delete_file_fn: Функция для удаления файла (file_id) -> None
            get_prompt_fn: Функция для получения промпта по ID (prompt_id) -> prompt text
            logger: Логгер для вывода сообщений
            executor: ThreadPoolExecutor для блокирующих операций
        """
        self._upload_file = upload_file_fn
        self._chat = chat_fn
        self._delete_file = delete_file_fn
        self._get_prompt = get_prompt_fn
        self._logger = logger
        self._executor = executor or ThreadPoolExecutor(max_workers=2)

    async def process_barcodes(
        self,
        pdf_bytes: bytes,
        llm_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Обработать штрих-коды в PDF и обновить результат LLM.

        Логика:
        1. Найти все штрих-коды I25 в PDF
        2. Для каждого штрих-кода проверить наличие надписи "ПОЧТА РОССИИ" через LLM
        3. Если 0 штрих-кодов с надписью - вернуть исходный результат
        4. Если 1 штрих-код с надписью - вставить его данные в "НомерКонверта"
        5. Если >1 штрих-кодов с надписью - вернуть ошибку

        Args:
            pdf_bytes: PDF файл в виде байтов
            llm_result: Результат обработки LLM (словарь с "success", "result" и т.д.)

        Returns:
            Обновленный результат с "НомерКонверта" или ошибкой
        """
        # Найти все штрих-коды (блокирующая операция -> executor)
        loop = asyncio.get_running_loop()

        def _find_barcodes() -> List[Dict[str, Any]]:
            return _find_barcodes_in_pdf_bytes(
                pdf_bytes,
                brightness=0.8,
                contrast=150,
                binarize=False,
                margin=80,
                allowed_types=['I25'],
                rotate=True
            )

        barcodes = await loop.run_in_executor(self._executor, _find_barcodes)

        if not barcodes:
            return llm_result

        if self._logger:
            self._logger.info(f"Найдено штрих-кодов I25: {len(barcodes)}")

        # Проверить каждый штрих-код на наличие надписи "ПОЧТА РОССИИ"
        pr_barcodes = []

        for barcode in barcodes:
            is_pr = await self._check_barcode_is_pr(barcode['image'])
            if is_pr:
                pr_barcodes.append(barcode)
                if self._logger:
                    self._logger.info(f"Штрих-код распознан как ПОЧТА РОССИИ: {barcode['data']}")

        if len(pr_barcodes) == 0:
            return llm_result

        if len(pr_barcodes) > 1:
            return {
                "success": True,
                "result":{
                "НомерКонверта": " "
                },
                "processing_time_ms": llm_result.get("processing_time_ms", 0)
            }

        # Один штрих-код с надписью "ПОЧТА РОССИИ" - вставить в НомерКонверта
        barcode_data = pr_barcodes[0]['data']

        if self._logger:
            self._logger.info(f"Вставка НомерКонверта: {barcode_data}")

        if llm_result.get("success") and "result" in llm_result:
            llm_result["result"]["НомерКонверта"] = barcode_data

        return llm_result

    async def _check_barcode_is_pr(self, barcode_image: Image.Image) -> bool:
        """
        Проверить штрих-код на наличие надписи "ПОЧТА РОССИИ".
        """
        # Блокирующая операция - сохранение изображения -> executor
        loop = asyncio.get_running_loop()

        def _save_image() -> bytes:
            img_bytes = BytesIO()
            barcode_image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            return img_bytes.getvalue()

        image_data = await loop.run_in_executor(self._executor, _save_image)

        if self._logger:
            self._logger.debug(
                f"Отправка изображения штрих-кода в LLM: "
                f"{barcode_image.size[0]}x{barcode_image.size[1]} px, "
                f"{len(image_data)} байт"
            )

        prompt = self._get_prompt(1)  # check_barcode_is_PR
        if not prompt:
            return False

        file_id = None
        try:
            file_id = await self._upload_file(image_data, "barcode.png")
            response = await self._chat(prompt, file_ids=[file_id] if file_id else [])
            result_text = response.get("response", "").strip().lower()

            if self._logger:
                self._logger.debug(f"Ответ LLM: {result_text}")

            return result_text == "true"
        except Exception as e:
            if self._logger:
                self._logger.warning(f"Ошибка проверки штрих-кода: {e}")
            return False
        finally:
            if file_id:
                await self._delete_file(file_id)


class FileHandler:
    """
    File handler - internal component for file operations.

    This class handles file downloads from storage and validation.
    """

    def __init__(self, storage: IFileStorageConnector):
        """
        Initialize the file handler.

        Args:
            storage: File storage connector for file operations
        """
        self.storage = storage  # File storage connector for file operations
    
    async def get_file(self, storage_path: str) -> bytes:
        """Получить файл из хранилища."""
        if not storage_path:
            raise ValueError("No storage_path provided")
        return await self.storage.download_bytes(storage_path)
    
    async def validate_file(self, storage_path: str) -> bool:
        """Проверить существование файла."""
        try:
            await self.storage.download_bytes(storage_path, offset=0, length=1)
            return True
        except Exception:
            return False


class WorkerManager:
    """
    Worker manager - internal component for managing worker lifecycle.

    This class handles the creation, management, and lifecycle of worker tasks
    that process incoming tasks concurrently.
    """

    def __init__(self, max_workers: int):
        """
        Initialize the worker manager.

        Args:
            max_workers: Maximum number of concurrent worker tasks
        """
        self.max_workers = max_workers  # Maximum number of concurrent worker tasks
        self.processing_queue = asyncio.Queue()  # Queue for incoming tasks
        self.worker_semaphore = asyncio.Semaphore(max_workers)  # Semaphore to limit concurrent workers
        self.worker_tasks: List[asyncio.Task] = []  # List of active worker tasks
    
    async def start_workers(self, process_callback) -> None:
        """Запустить воркеры."""
        self.worker_tasks = [
            asyncio.create_task(self._worker_loop(i, process_callback))
            for i in range(self.max_workers)
        ]
    
    async def _worker_loop(self, worker_id: int, process_callback) -> None:
        """Цикл работы воркера."""
        worker_name = f"Worker_{worker_id + 1}"
        
        while True:
            try:
                task_data = await asyncio.wait_for(
                    self.processing_queue.get(), 
                    timeout=1.0
                )
                
                async with self.worker_semaphore:
                    await process_callback(task_data, worker_name)
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {worker_name} error: {e}")
    
    async def add_task(self, task_data: Dict[str, Any]) -> None:
        """Добавить задачу в очередь."""
        await self.processing_queue.put(task_data)
    
    async def shutdown(self) -> None:
        """Остановить всех воркеров."""
        for task in self.worker_tasks:
            task.cancel()
        
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)


# ============ ОСНОВНОЙ СЕРВИС ============

@register_service('llm')
class LLMService(BaseService):
    """
    Main LLM service with internal modularity.

    This service coordinates the processing of tasks through various internal
    components including task coordination, LLM processing, file handling,
    and worker management. It integrates with external services like Kafka,
    MinIO, and GigaChat through their respective connectors.
    """

    def __init__(self, config=None):
        """
        Initialize the LLM service.

        Args:
            config: Optional configuration object, will use default if not provided
        """
        super().__init__(name="LLMService", config=config)

        # External service interfaces (injected via container)
        self.llm: Optional[ILLMConnector] = None  # LLM connector interface
        self.queue: Optional[IQueueConnector] = None  # Queue connector interface
        self.storage: Optional[IFileStorageConnector] = None  # Storage connector interface

        # Internal components (initialized later)
        self.task_coordinator: Optional[TaskCoordinator] = None  # Task coordination component
        self.llm_processor: Optional[LLMProcessor] = None  # LLM processing component
        self.file_handler: Optional[FileHandler] = None  # File handling component
        self.barcode_processor: Optional[BarcodeProcessor] = None  # Barcode processing component
        self.worker_manager: Optional[WorkerManager] = None  # Worker management component
    
    async def _initialize_service(self) -> bool:
        """Инициализировать сервис."""
        try:
            # Получить интерфейсы из контейнера
            try:
                self.llm = self.container.get_llm()  # Использует "LLM" по умолчанию
                self._logger.info("LLM interface initialized")
            except Exception as e:
                self._logger.error(f"Failed to get LLM interface: {e}")
                # Не падаем, если LLM недоступен - возможно, он не нужен сейчас

            try:
                self.queue = self.container.get_queue()  # Использует "Queue" по умолчанию
                self._logger.info("Queue interface initialized")
            except Exception as e:
                self._logger.error(f"Failed to get Queue interface: {e}")
                # Продолжаем без Kafka

            try:
                self.storage = self.container.get_storage()  # Использует "Storage" по умолчанию
                self._logger.info("Storage interface initialized")
            except Exception as e:
                self._logger.error(f"Failed to get Storage interface: {e}")
                # Продолжаем без MinIO
            
            # Создать внутренние компоненты (даже если некоторые интерфейсы отсутствуют)
            self.task_coordinator = TaskCoordinator(
                self.queue,
                self.container.get_task_deduplication_queue()
            )

            if self.llm:
                self.llm_processor = LLMProcessor(self.llm)

            if self.storage:
                self.file_handler = FileHandler(self.storage)

            # BarcodeProcessor создается только если есть LLM
            self.barcode_processor = None
            if self.llm:
                self._barcode_executor = ThreadPoolExecutor(max_workers=2)
                self.barcode_processor = BarcodeProcessor(
                    upload_file_fn=self.llm.upload_file,
                    chat_fn=self.llm.chat,
                    delete_file_fn=self.llm.delete_file,
                    get_prompt_fn=PromptService().get_prompt_by_id,
                    logger=self._logger,
                    executor=self._barcode_executor
                )

            # WorkerManager создается всегда
            self.worker_manager = WorkerManager(
                self.config.worker_max_concurrent_tasks
            )

            self._logger.info("Service components initialized")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to initialize service: {e}", exc_info=True)
            return False
    
    async def _startup_impl(self) -> None:
        """Запустить сервис."""
        # Сначала инициализировать сервис
        if not await self._initialize_service():
            self._logger.error("Failed to initialize LLMService")
            raise RuntimeError("LLMService initialization failed")
        
        # Проверить, что worker_manager инициализирован
        if not self.worker_manager:
            self._logger.error("WorkerManager not initialized")
            raise RuntimeError("WorkerManager not initialized")
        
        self._logger.info(f"Starting LLM Service with {self.worker_manager.max_workers} workers")
        
        # Проверить минимальные зависимости
        if not self.queue:
            self._logger.error("Queue interface required but not available")
            raise RuntimeError("Queue interface not available")
        
        # Запустить воркеров
        await self.worker_manager.start_workers(self._process_task)
        
        # Начать потребление задач
        group_id = f"{self.config.kafka.group_id}_llm_service_{int(time.time())}"
        await self.queue.subscribe(
            topics=["tasks_llm"],
            group_id=group_id,
            auto_offset_reset="latest",
        )
        
        self._logger.info("LLM Service started successfully")
        
        # Основной цикл потребления
        while not self.get_shutdown_event().is_set():
            try:
                message = await asyncio.wait_for(self.queue.consume(), timeout=1.0)
                await self._handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(1)  # Пауза при ошибке
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Обработать сообщение из Kafka."""
        # Пропустить если не PENDING
        if message.get("kafka_headers", {}).get("status") != TaskStatus.PENDING.value:
            await self.queue.commit(message)
            return
        
        # Подготовить данные задачи
        task_data = await self.task_coordinator.prepare_task_data(message)
        
        # Проверить дубликат
        if self.task_coordinator.is_duplicate_task(task_data["task_id"]):
            await self.queue.commit(message)
            return
        
        # Пометить как обрабатываемую
        self.task_coordinator.mark_task_processed(task_data["task_id"])
        
        # Добавить в очередь воркеров
        await self.worker_manager.add_task(task_data)
    
    async def _process_task(self, task_data: Dict[str, Any], worker_id: str) -> None:
        """Обработать задачу воркером."""
        task_id = task_data["task_id"]
        trace_id = task_data["trace_id"]

        try:
            # Проверить необходимые компоненты
            if not self.llm_processor:
                raise RuntimeError("LLM processor not available")

            if not self.file_handler:
                raise RuntimeError("File handler not available")

            # Отправить статус PROCESSING
            await self._send_status(task_id, trace_id, TaskStatus.PROCESSING, worker_id)

            # Получить файл
            file_content = await self.file_handler.get_file(task_data["storage_path"])

            # Обработать через LLM
            result = await self.llm_processor.process(task_data, file_content)

            # После успешной обработки LLM - проверить штрих-коды
            if result.get("success") and self.barcode_processor:
                result = await self.barcode_processor.process_barcodes(
                    pdf_bytes=file_content,
                    llm_result=result
                )

                # Логирование результата обработки штрих-кодов
                if result.get("success") and result.get("result", {}).get("НомерКонверта"):
                    self._logger.info(f"Штрих-код обработан: НомерКонверта={result['result']['НомерКонверта']}")

            # Отправить результат
            await self._send_result(task_id, trace_id, result, worker_id)

            # Зафиксировать сообщение
            await self.queue.commit(task_data["original_message"])

        except Exception as e:
            self._logger.error(f"[{trace_id}] Task {task_id} failed: {e}")
            await self._send_error(task_id, trace_id, str(e), worker_id)
    
    async def _send_status(
        self,
        task_id: str,
        trace_id: str,
        status: TaskStatus,
        worker_id: str
    ) -> None:
        """Отправить статус в Kafka."""
        await self.queue.publish(
            topic="tasks_llm",
            datagram_id=str(uuid.uuid4()),
            key=task_id,
            data={},
            headers={
                "status": status.value,
                "trace_id": trace_id,
                "worker_id": worker_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    
    async def _send_result(
        self,
        task_id: str,
        trace_id: str,
        result: Dict[str, Any],
        worker_id: str
    ) -> None:
        """Отправить результат в Kafka."""
        status = TaskStatus.SUCCESS if result["success"] else TaskStatus.FAILED
        data = {"result": json.dumps(result["result"], ensure_ascii=False)} if result["success"] else {"error": result["error"]}

        if self._logger:
            self._logger.info(f"Отправка результата в Kafka: {json.dumps(data, ensure_ascii=False, indent=2)}")

        await self.queue.publish(
            topic="tasks_llm",
            datagram_id=str(uuid.uuid4()),
            key=task_id,
            data=data,
            headers={
                "status": status.value,
                "trace_id": trace_id,
                "worker_id": worker_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    
    async def _send_error(
        self,
        task_id: str,
        trace_id: str,
        error: str,
        worker_id: str
    ) -> None:
        """Отправить ошибку в Kafka."""
        await self.queue.publish(
            topic="tasks_llm",
            datagram_id=str(uuid.uuid4()),
            key=task_id,
            data={"error": error},
            headers={
                "status": TaskStatus.FAILED.value,
                "trace_id": trace_id,
                "worker_id": worker_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    
    async def _shutdown_impl(self) -> None:
        """Остановить сервис."""
        self._logger.info("Shutting down LLM Service...")

        if self.worker_manager:
            await self.worker_manager.shutdown()

        # Очистить executor barcode processor
        if hasattr(self, '_barcode_executor') and self._barcode_executor:
            self._barcode_executor.shutdown(wait=True)

        self._logger.info("LLM Service shutdown complete")
        