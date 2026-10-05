"""Bounded customer-provided visible conversation, never execution evidence."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

MAX_CONVERSATION_MESSAGES = 100
MAX_CONVERSATION_CHARACTERS = 100_000


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: StrictStr = Field(min_length=1, max_length=MAX_CONVERSATION_CHARACTERS)


class CaseConversation(BaseModel):
    source: Literal["CUSTOMER_PROVIDED"] = "CUSTOMER_PROVIDED"
    messages: list[ConversationMessage] = Field(
        default_factory=list, max_length=MAX_CONVERSATION_MESSAGES,
    )

    @model_validator(mode="after")
    def validate_character_limit(self) -> CaseConversation:
        if sum(len(message.text) for message in self.messages) > MAX_CONVERSATION_CHARACTERS:
            raise ValueError("Conversation history exceeds 100000 characters")
        return self
