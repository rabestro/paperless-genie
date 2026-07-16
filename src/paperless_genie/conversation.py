"""Per-user conversation history for the search agent's prompt context."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class ConversationHistory:
    """Stores the recent conversation turns for a single user.

    Each turn is a (user_message, bot_reply) pair. Older turns are dropped
    once *max_turns* is exceeded so token usage stays bounded.
    """

    MAX_TURNS: ClassVar[int] = 10

    turns: list[tuple[str, str]] = field(default_factory=list)

    def add(self, user_msg: str, bot_reply: str) -> None:
        """Appends a new turn and trims the oldest if needed."""
        self.turns.append((user_msg, bot_reply))
        if len(self.turns) > self.MAX_TURNS:
            self.turns.pop(0)

    def build_context(self, current_user_msg: str) -> str:
        """Returns a prompt string that includes history + the current message.

        Args:
            current_user_msg: The latest message from the user.

        Returns:
            Full prompt text with prior conversation context prepended.
        """
        if not self.turns:
            return f"User: {current_user_msg}"

        lines: list[str] = ["Below is the conversation history (oldest first):"]
        for user, bot in self.turns:
            lines.append(f"User: {user}")
            lines.append(f"Assistant: {bot}")
        lines.append("")
        lines.append(f"User: {current_user_msg}")
        lines.append(
            "Now answer the last User message, taking the conversation history into account."
        )
        return "\n".join(lines)

    def clear(self) -> None:
        """Resets the conversation history."""
        self.turns.clear()
