"""Snapshot persistence helpers; callers authorize the case before reading."""
from sqlmodel import Session

from banking_transaction.models.conversation import CaseConversation
from banking_transaction.models.conversation_record import CaseConversationSnapshot


def read_conversation(session: Session, case_id: str) -> CaseConversation:
    snapshot = session.get(CaseConversationSnapshot, case_id)
    return CaseConversation(messages=snapshot.messages if snapshot is not None else [])


def append_conversation(session: Session, case_id: str, history: CaseConversation) -> None:
    session.add(CaseConversationSnapshot(
        case_id=case_id, messages=[message.model_dump() for message in history.messages],
    ))
