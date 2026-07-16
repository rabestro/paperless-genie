from paperless_genie.conversation import ConversationHistory


def test_add_appends_turns_in_order() -> None:
    history = ConversationHistory()
    history.add("q1", "a1")
    history.add("q2", "a2")
    assert history.turns == [("q1", "a1"), ("q2", "a2")]


def test_add_drops_oldest_turns_beyond_max() -> None:
    history = ConversationHistory()
    total = ConversationHistory.MAX_TURNS + 3
    for i in range(total):
        history.add(f"q{i}", f"a{i}")
    assert len(history.turns) == ConversationHistory.MAX_TURNS
    assert history.turns[0] == ("q3", "a3")
    assert history.turns[-1] == (f"q{total - 1}", f"a{total - 1}")


def test_build_context_without_history_is_bare_prompt() -> None:
    history = ConversationHistory()
    assert history.build_context("hello") == "User: hello"


def test_build_context_includes_history_and_final_instruction() -> None:
    history = ConversationHistory()
    history.add("q1", "a1")
    context = history.build_context("q2")
    assert context.startswith("Below is the conversation history (oldest first):")
    assert "User: q1" in context
    assert "Assistant: a1" in context
    assert "User: q2" in context
    assert context.endswith("taking the conversation history into account.")
    # The current message comes after the history it should be answered against.
    assert context.index("Assistant: a1") < context.index("User: q2")


def test_clear_resets_history() -> None:
    history = ConversationHistory()
    history.add("q", "a")
    history.clear()
    assert history.turns == []
    assert history.build_context("next") == "User: next"
