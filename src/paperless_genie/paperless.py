"""Async client for the Paperless-ngx REST API.

This module owns every HTTP interaction with Paperless-ngx and the
upload/OCR polling state machine. It has no Telegram dependency: progress is
reported through an optional async callback so the caller (a bot handler)
decides how to surface it.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Give up polling the tasks API after this many consecutive failures.
_MAX_CONSECUTIVE_POLL_FAILURES = 5
# Default overall wait and per-iteration delay for OCR polling (seconds).
_DEFAULT_MAX_WAIT = 180.0
_DEFAULT_POLL_INTERVAL = 3.0

StatusCallback = Callable[[str], Awaitable[None]]


class DuplicateDocumentError(Exception):
    """Raised when a document being uploaded is identified as a duplicate."""

    def __init__(self, doc_id: int) -> None:
        super().__init__(f"Duplicate of document #{doc_id}")
        self.doc_id = doc_id


class PaperlessDocument(BaseModel):
    """A subset of a Paperless-ngx document's metadata.

    Tolerant by design: unknown fields are ignored and everything is optional,
    because the exact shape varies across Paperless-ngx versions.
    """

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    original_file_name: str | None = None
    created: str | None = None
    created_date: str | None = None


class PaperlessTask(BaseModel):
    """A subset of a Paperless-ngx task record from the /api/tasks/ endpoint."""

    model_config = ConfigDict(extra="ignore")

    status: str = ""
    related_document: int | None = None
    result: str | None = None


def _parse_task_id(response: httpx.Response) -> str:
    """Extracts the task ID from a post_document response.

    Paperless-ngx returns this in several shapes across versions: a JSON
    object ``{"task_id": "..."}``, a bare JSON string, or a quoted raw body.

    Args:
        response: The HTTP response from post_document.

    Returns:
        The task ID, or an empty string if none could be extracted.
    """
    try:
        data = response.json()
    except ValueError:
        # Body isn't JSON (json.JSONDecodeError is a ValueError) — some
        # Paperless versions return the task ID as a quoted raw string.
        return response.text.strip().strip('"')
    if isinstance(data, dict):
        task_id = data.get("task_id")
        return str(task_id) if task_id else ""
    # `data or ""` keeps a JSON null falsy instead of str(None) -> "None".
    return str(data or "")


def _normalize_tasks(task_data: object) -> list[dict[str, object]]:
    """Normalizes the /api/tasks/ payload to a list of task dicts.

    The endpoint returns either a bare list or ``{"results": [...]}``.

    Args:
        task_data: The parsed JSON body.

    Returns:
        A list of task dicts (empty if the shape is unrecognized).
    """
    if isinstance(task_data, dict) and "results" in task_data:
        results = task_data["results"]
        return results if isinstance(results, list) else []
    if isinstance(task_data, list):
        return task_data
    return []


def _extract_document_id(task: PaperlessTask) -> int | None:
    """Returns the created document ID from a succeeded task, or None.

    Prefers the structured ``related_document`` field and falls back to
    parsing it out of the free-text result.

    Args:
        task: A task whose status is SUCCESS.

    Returns:
        The document ID, or None if it cannot be determined.
    """
    if task.related_document is not None:
        return task.related_document
    match = re.search(r"document id (\d+) created", task.result or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_duplicate_id(result_text: str) -> int | None:
    """Returns the existing document ID referenced by a duplicate failure.

    Args:
        result_text: The task's free-text result.

    Returns:
        The referenced document ID, or None if the failure is not a duplicate
        or no ID is present.
    """
    if "duplicate" not in result_text.lower():
        return None
    # e.g. "... is a duplicate of #416"
    match = re.search(r"#(\d+)", result_text)
    if match:
        return int(match.group(1))
    # Fallback pattern, e.g. "... id 416"
    match = re.search(r"id\s+(\d+)", result_text, re.IGNORECASE)
    return int(match.group(1)) if match else None


async def _notify(on_status: StatusCallback | None, message: str) -> None:
    """Invokes the progress callback if one was supplied."""
    if on_status is not None:
        await on_status(message)


class PaperlessClient:
    """Talks to one Paperless-ngx instance on behalf of one user.

    Args:
        base_url: The Paperless-ngx base URL.
        token: The user's Paperless API token.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Token {token}"}

    async def fetch_document_info(self, doc_id: int) -> PaperlessDocument | None:
        """Fetches document metadata.

        Args:
            doc_id: The Paperless document ID.

        Returns:
            The document metadata, or None if the document was not found.
        """
        url = f"{self._base_url}/api/documents/{doc_id}/"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers)
            if resp.status_code == httpx.codes.NOT_FOUND:
                return None
            resp.raise_for_status()
            return PaperlessDocument.model_validate(resp.json())

    async def download_pdf(self, doc_id: int) -> bytes:
        """Downloads the original PDF of a document.

        Args:
            doc_id: The Paperless document ID.

        Returns:
            Raw PDF bytes.

        Raises:
            httpx.HTTPStatusError: If the download request fails.
        """
        url = f"{self._base_url}/api/documents/{doc_id}/download/"
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            return resp.content

    async def upload_and_wait_for_ocr(
        self,
        *,
        file_bytes: bytes,
        file_name: str,
        on_status: StatusCallback | None = None,
        max_wait: float = _DEFAULT_MAX_WAIT,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> int:
        """Uploads a document and polls until OCR/processing completes.

        Args:
            file_bytes: Raw bytes of the file to upload.
            file_name: Original filename.
            on_status: Optional async callback for human-readable progress.
            max_wait: Maximum seconds to wait for processing.
            poll_interval: Seconds between task-status polls.

        Returns:
            The created document ID.

        Raises:
            DuplicateDocumentError: If the document is a duplicate.
            ValueError: On other processing failures or an unusable response.
            TimeoutError: If processing does not finish within max_wait.
        """
        upload_url = f"{self._base_url}/api/documents/post_document/"
        files = {"document": (file_name, file_bytes)}

        async with httpx.AsyncClient(timeout=30) as client:
            await _notify(on_status, "📤 Uploading document to Paperless-ngx...")
            response = await client.post(upload_url, headers=self._headers, files=files)
            response.raise_for_status()

            task_id = _parse_task_id(response)
            if not task_id:
                raise ValueError(f"Failed to retrieve task ID. Response: {response.text}")

            tasks_url = f"{self._base_url}/api/tasks/?task_id={task_id}"
            await _notify(on_status, "⚙️ Document queued. Waiting for OCR & processing...")

            start_time = datetime.now(UTC)
            consecutive_failures = 0
            while (datetime.now(UTC) - start_time).total_seconds() < max_wait:
                await asyncio.sleep(poll_interval)
                # Fetch, decode, and validate the task record inside the
                # transient-error guard. A malformed record mid-processing
                # (pydantic.ValidationError is a ValueError) is treated as a
                # transient failure and retried, exactly like an HTTP or JSON
                # error — it must not crash the whole upload.
                try:
                    task_response = await client.get(tasks_url, headers=self._headers)
                    task_response.raise_for_status()
                    tasks = _normalize_tasks(task_response.json())
                    task = PaperlessTask.model_validate(tasks[0]) if tasks else None
                    consecutive_failures = 0  # reset on a well-formed response
                except (httpx.HTTPError, ValueError) as err:
                    consecutive_failures += 1
                    logger.warning(
                        "Transient error polling tasks API (failure %d): %s",
                        consecutive_failures,
                        err,
                    )
                    if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                        raise ValueError(
                            f"Failed to poll task status after "
                            f"{_MAX_CONSECUTIVE_POLL_FAILURES} attempts: {err}"
                        ) from err
                    continue

                if task is None:
                    continue  # task not registered yet

                # Terminal-state handling stays OUTSIDE the try: the ValueErrors
                # and DuplicateDocumentError raised below are deliberate, fatal
                # signals and must propagate, not be swallowed as transient.
                status = task.status.upper()

                if status == "SUCCESS":
                    doc_id = _extract_document_id(task)
                    if doc_id is not None:
                        return doc_id
                    raise ValueError(
                        f"Task succeeded but related_document ID not found. "
                        f"Result: {task.result or ''}"
                    )

                if status in ("FAILED", "FAILURE"):
                    result_text = task.result or ""
                    duplicate_id = _extract_duplicate_id(result_text)
                    if duplicate_id is not None:
                        raise DuplicateDocumentError(doc_id=duplicate_id)
                    raise ValueError(f"Document processing failed: {result_text}")

            raise TimeoutError("Timed out waiting for document processing / OCR to complete.")
