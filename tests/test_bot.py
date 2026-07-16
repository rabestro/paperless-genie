from paperless_genie import bot as bot_module


def test_extract_doc_ids_deduplicates_preserving_order() -> None:
    text = "First [#42] then [#7] then [#42] again and [#7]."
    assert bot_module._extract_doc_ids(text) == [42, 7]


def test_extract_doc_ids_returns_empty_when_no_markers() -> None:
    assert bot_module._extract_doc_ids("no markers here") == []


def test_chunk_text_returns_single_chunk_at_or_under_limit() -> None:
    assert bot_module._chunk_text("", limit=10) == [""]
    assert bot_module._chunk_text("exactly10!", limit=10) == ["exactly10!"]


def test_chunk_text_splits_past_the_limit() -> None:
    assert bot_module._chunk_text("abcdefghijk", limit=10) == ["abcdefghij", "k"]
    assert bot_module._chunk_text("a" * 25, limit=10) == ["a" * 10, "a" * 10, "a" * 5]


def test_build_doc_keyboard_none_when_empty() -> None:
    assert bot_module._build_doc_keyboard([]) is None


def test_build_doc_keyboard_has_one_button_per_id() -> None:
    keyboard = bot_module._build_doc_keyboard([42, 7])
    assert keyboard is not None
    buttons = [button for row in keyboard.keyboard for button in row]
    assert [b.callback_data for b in buttons] == ["get_doc:42", "get_doc:7"]
