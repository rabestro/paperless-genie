import httpx
import pytest
import respx

from paperless_genie.paperless import (
    DuplicateDocumentError,
    PaperlessClient,
    PaperlessTask,
    _extract_document_id,
    _extract_duplicate_id,
    _normalize_tasks,
    _parse_task_id,
)

BASE = "http://paperless.test"


def _client() -> PaperlessClient:
    return PaperlessClient(BASE, "user-token")


def _response(json_body: object) -> httpx.Response:
    return httpx.Response(200, json=json_body)


# --- pure parsers -----------------------------------------------------------


def test_parse_task_id_from_dict() -> None:
    assert _parse_task_id(_response({"task_id": "abc"})) == "abc"


def test_parse_task_id_from_bare_string() -> None:
    assert _parse_task_id(_response("abc")) == "abc"


def test_parse_task_id_from_json_null_is_empty() -> None:
    # Regression: a JSON null must not become the truthy string "None".
    assert _parse_task_id(_response(None)) == ""


def test_parse_task_id_from_dict_without_key_is_empty() -> None:
    assert _parse_task_id(_response({"other": "x"})) == ""


def test_parse_task_id_falls_back_to_quoted_text() -> None:
    resp = httpx.Response(200, text='"quoted-uuid"', headers={"content-type": "text/plain"})
    assert _parse_task_id(resp) == "quoted-uuid"


def test_normalize_tasks_handles_list_dict_and_junk() -> None:
    assert _normalize_tasks([{"a": 1}]) == [{"a": 1}]
    assert _normalize_tasks({"results": [{"a": 1}]}) == [{"a": 1}]
    assert _normalize_tasks({"results": "nope"}) == []
    assert _normalize_tasks("garbage") == []


def test_extract_document_id_prefers_related_document() -> None:
    task = PaperlessTask(status="SUCCESS", related_document=416)
    assert _extract_document_id(task) == 416


def test_extract_document_id_falls_back_to_result_text() -> None:
    task = PaperlessTask(status="SUCCESS", result="document id 42 created")
    assert _extract_document_id(task) == 42


def test_extract_document_id_none_when_unavailable() -> None:
    assert _extract_document_id(PaperlessTask(status="SUCCESS", result="done")) is None


def test_extract_duplicate_id_hash_pattern() -> None:
    assert _extract_duplicate_id("It is a duplicate of #416.") == 416


def test_extract_duplicate_id_id_pattern() -> None:
    assert _extract_duplicate_id("duplicate, see id 99") == 99


def test_extract_duplicate_id_none_when_not_duplicate() -> None:
    assert _extract_duplicate_id("some other failure") is None


def test_related_document_coerces_string_id() -> None:
    # Paperless sometimes sends the id as a string; pydantic coerces it.
    assert PaperlessTask.model_validate({"related_document": "416"}).related_document == 416


# --- fetch_document_info ----------------------------------------------------


@respx.mock
async def test_fetch_document_info_returns_model() -> None:
    respx.get(f"{BASE}/api/documents/5/").mock(
        return_value=_response({"title": "Passport", "original_file_name": "p.pdf", "extra": "x"})
    )
    info = await _client().fetch_document_info(5)
    assert info is not None
    assert info.title == "Passport"
    assert info.original_file_name == "p.pdf"


@respx.mock
async def test_fetch_document_info_none_on_404() -> None:
    respx.get(f"{BASE}/api/documents/5/").mock(return_value=httpx.Response(404))
    assert await _client().fetch_document_info(5) is None


# --- download_pdf -----------------------------------------------------------


@respx.mock
async def test_download_pdf_returns_bytes() -> None:
    respx.get(f"{BASE}/api/documents/5/download/").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.7 ...")
    )
    assert await _client().download_pdf(5) == b"%PDF-1.7 ..."


# --- upload_and_wait_for_ocr ------------------------------------------------


@respx.mock
async def test_upload_success_returns_document_id() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        return_value=_response([{"status": "SUCCESS", "related_document": 123}])
    )
    statuses: list[str] = []

    async def record(status: str) -> None:
        statuses.append(status)

    doc_id = await _client().upload_and_wait_for_ocr(
        file_bytes=b"x",
        file_name="scan.pdf",
        on_status=record,
        poll_interval=0.01,
    )
    assert doc_id == 123
    # Both progress messages were reported, in order.
    assert statuses[0].startswith("📤")
    assert statuses[1].startswith("⚙️")


@respx.mock
async def test_upload_duplicate_raises_with_existing_id() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        return_value=_response(
            [{"status": "FAILURE", "result": "Not consuming x.pdf: It is a duplicate of #416."}]
        )
    )
    with pytest.raises(DuplicateDocumentError) as exc:
        await _client().upload_and_wait_for_ocr(
            file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
        )
    assert exc.value.doc_id == 416


@respx.mock
async def test_upload_empty_task_id_raises() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response(None))
    with pytest.raises(ValueError, match="Failed to retrieve task ID"):
        await _client().upload_and_wait_for_ocr(
            file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
        )


@respx.mock
async def test_upload_processing_failure_raises() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        return_value=_response([{"status": "FAILURE", "result": "OCR engine exploded"}])
    )
    with pytest.raises(ValueError, match="Document processing failed"):
        await _client().upload_and_wait_for_ocr(
            file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
        )


@respx.mock
async def test_upload_transient_errors_recover() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            _response([{"status": "SUCCESS", "related_document": 7}]),
        ]
    )
    doc_id = await _client().upload_and_wait_for_ocr(
        file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
    )
    assert doc_id == 7


@respx.mock
async def test_upload_recovers_from_malformed_task_record() -> None:
    # A task record that fails validation (non-coercible related_document) is a
    # transient failure, not a crash: the loop retries and succeeds next poll.
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        side_effect=[
            _response([{"status": "STARTED", "related_document": "not-an-int"}]),
            _response([{"status": "SUCCESS", "related_document": 7}]),
        ]
    )
    doc_id = await _client().upload_and_wait_for_ocr(
        file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
    )
    assert doc_id == 7


@respx.mock
async def test_upload_gives_up_after_five_consecutive_failures() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(return_value=httpx.Response(503))
    with pytest.raises(ValueError, match="after 5 attempts"):
        await _client().upload_and_wait_for_ocr(
            file_bytes=b"x", file_name="x.pdf", poll_interval=0.01
        )


@respx.mock
async def test_upload_times_out_when_never_ready() -> None:
    respx.post(f"{BASE}/api/documents/post_document/").mock(return_value=_response("task-1"))
    # Task registered but perpetually pending → the wall-clock budget expires.
    respx.get(url__startswith=f"{BASE}/api/tasks/").mock(
        return_value=_response([{"status": "STARTED"}])
    )
    with pytest.raises(TimeoutError):
        await _client().upload_and_wait_for_ocr(
            file_bytes=b"x", file_name="x.pdf", max_wait=0.05, poll_interval=0.01
        )
