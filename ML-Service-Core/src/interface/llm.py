"""
LLM Interface - Strategy pattern implementation for LLM connectors.

Allows switching between different LLM providers (GigaChat, OpenAI, etc.)
while maintaining the same API.
"""

from typing import Any, AsyncIterator, Dict, List, Optional, Union

from core.base_class.base_interface import BaseInterface
from core.base_class.protocols import ILLMConnector
from utils.observer import EventPublisher
from core.registry import register_interface


@register_interface("LLM")
class LLMInterface(BaseInterface, ILLMConnector):
    """
    High-level interface for LLM operations.

    Implements Strategy pattern - can switch between different LLM providers
    (GigaChat, OpenAI, etc.) transparently.
    """

    def __init__(
        self,
        worker: ILLMConnector,
        name: Optional[str] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize LLM interface.

        Args:
            worker: LLM connector instance (e.g., GigaChatConnector)
            name: Interface name (defaults to worker name)
            event_publisher: Optional event publisher for observability
        """
        super().__init__(worker, name, event_publisher)

    @property
    def worker(self) -> ILLMConnector:
        """Get underlying LLM connector"""
        return self._worker

    # ============ ILLMConnector protocol implementation ============

    async def chat(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        stream: bool = False,
    ) -> Union[Dict[str, Any], AsyncIterator[str]]:
        """
        Chat with LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            file_ids: Optional list of file IDs to attach
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            timeout: Request timeout
            stream: If True, return streaming response

        Returns:
            Response dict if stream=False, AsyncIterator if stream=True
        """
        result = await self._execute_with_tracking(
            "chat",
            self._worker.chat,
            prompt,
            system_prompt=system_prompt,
            file_ids=file_ids,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=stream,
            metadata={
                "prompt_length": len(prompt),
                "has_system_prompt": system_prompt is not None,
                "file_count": len(file_ids) if file_ids else 0,
                "temperature": temperature,
                "stream": stream,
            },
        )
        return result

    async def upload_file(
        self,
        file_data: Any,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """
        Upload file and return file ID.

        Args:
            file_data: File data (bytes or file-like object)
            filename: Optional filename
            mime_type: Optional MIME type
            timeout: Upload timeout

        Returns:
            File ID or None if upload failed
        """
        result = await self._execute_with_tracking(
            "upload_file",
            self._worker.upload_file,
            file_data,
            filename=filename,
            mime_type=mime_type,
            timeout=timeout,
            metadata={
                "filename": filename or "unknown",
                "mime_type": mime_type or "unknown",
                "has_timeout": timeout is not None,
            },
        )
        return result

    async def upload_files_concurrent(
        self,
        files: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[str]:
        """
        Upload multiple files concurrently.

        Args:
            files: List of file dictionaries with 'data', 'filename', 'mime_type'
            timeout: Upload timeout

        Returns:
            List of uploaded file IDs
        """
        result = await self._execute_with_tracking(
            "upload_files_concurrent",
            self._worker.upload_files_concurrent,
            files,
            timeout=timeout,
            metadata={
                "file_count": len(files),
                "has_timeout": timeout is not None,
                "operation": "concurrent_upload",
            },
        )
        return result

    async def delete_file(
        self,
        file_id: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Delete file from LLM service.

        Args:
            file_id: File ID to delete
            timeout: Delete timeout

        Returns:
            True if deletion successful
        """
        result = await self._execute_with_tracking(
            "delete_file",
            self._worker.delete_file,
            file_id,
            timeout=timeout,
            metadata={
                "file_id": file_id,
                "has_timeout": timeout is not None,
            },
        )
        return result

    async def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """
        Get file information.

        Args:
            file_id: File ID

        Returns:
            File information dictionary
        """
        result = await self._execute_with_tracking(
            "get_file_info",
            self._worker.get_file_info,
            file_id,
            metadata={"file_id": file_id},
        )
        return result

    async def list_files(self) -> List[Dict[str, Any]]:
        """
        List uploaded files.

        Returns:
            List of file information dictionaries
        """
        result = await self._execute_with_tracking(
            "list_files",
            self._worker.list_files,
            metadata={"operation": "list_files"},
        )
        return result

    async def delete_files_concurrent(self, file_ids: List[str]) -> Dict[str, Any]:
        """
        Delete multiple files concurrently.

        Args:
            file_ids: List of file IDs to delete

        Returns:
            Dictionary with deletion results
        """
        result = await self._execute_with_tracking(
            "delete_files_concurrent",
            self._worker.delete_files_concurrent,
            file_ids,
            metadata={
                "file_count": len(file_ids),
                "operation": "concurrent_delete",
            },
        )
        return result

    async def batch_chat(
        self,
        payload: Dict[str, Optional[List[str]]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> tuple[List[Dict[str, Any]]]:
        """
        Batch chat processing.

        Args:
            payload: Dictionary mapping prompts to optional file IDs
            system_prompt: Optional system prompt for all requests
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            timeout: Request timeout

        Returns:
            Tuple of response dictionaries
        """
        result = await self._execute_with_tracking(
            "batch_chat",
            self._worker.batch_chat,
            payload,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            metadata={
                "request_count": len(payload),
                "has_system_prompt": system_prompt is not None,
                "temperature": temperature,
                "operation": "batch_chat",
            },
        )
        return result

    # ============ Convenience methods (not part of protocol) ============

    async def stream_chat(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat response (convenience method).

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            file_ids: Optional list of file IDs
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            timeout: Request timeout

        Yields:
            Chunks of response text
        """
        result = await self.chat(
            prompt,
            system_prompt=system_prompt,
            file_ids=file_ids,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=True,
        )
        return result  # type: ignore  # stream=True гарантирует AsyncIterator

    async def upload_files(
        self,
        files: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[str]:
        """Alias for upload_files_concurrent - for backward compatibility"""
        return await self.upload_files_concurrent(files, timeout=timeout)

    # ============ Protocol required methods ============

    @property
    def name(self) -> str:
        """Get connector name - required by ILLMConnector protocol"""
        return self._name

    async def health_check(self) -> bool:
        """Check LLM connectivity - required by protocol"""
        return await self._execute_with_tracking(
            "health_check",
            self._worker.health_check,
            metadata={"check_type": "llm_connectivity"},
        )

    def is_healthy(self) -> bool:
        """Get cached health status - required by protocol"""
        return self._worker.is_healthy()
    