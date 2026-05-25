"""Async resolution stage for Active Learning few-shot injection (Option 3).

Scope
~~~~~
This is the **resolution stage** of the sync/async bridge documented in
``hook.py``. The async query handler calls ``ActiveLearningResolver.resolve``
*before* invoking the LangGraph runtime, then passes the result into
``config["configurable"]["active_learning_assignment"]`` and
``["active_learning_examples"]`` for the sync ``_inject_active_learning_few_shot``
hook to consume.

Why a Protocol retriever instead of a concrete FAISS one?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Where the kNN search runs is an open architectural decision (Engine
container vs external service vs Gateway). Coupling ``faiss-cpu`` into the
production Engine image (Vertex AI agent-engines) adds non-trivial weight
for a flag-gated experiment. So this module depends only on a
``FewShotRetriever`` Protocol — the concrete implementation (FAISS-backed,
service-backed, etc.) is injected once the placement decision lands.

``NullRetriever`` is the default: it returns no examples, so the resolver
degrades to "control behaviour" until a real retriever and a populated
index exist (gated on the 200-annotation OPS session, task #208).

Failure model
~~~~~~~~~~~~~
- Flag service unavailable → ``FlagClient.assign`` returns ``None`` →
  resolver returns ``(None, [])`` → hook is a no-op (control behaviour).
- Retriever raises → caught, logged, treated as empty examples. The
  experiment layer must never break a citizen turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from engine.active_learning.fewshot_injector import FewShotExample
from engine.active_learning.flag_client import FlagAssignment, FlagClient
from engine.active_learning.hook import TREATMENT_VARIANT
from engine.log import logger

DEFAULT_TOP_K: Final[int] = 3


class FewShotRetriever(Protocol):
    """Retrieve the top-K annotated examples most similar to a query.

    Implementations own the embedding + index lookup. The resolver does
    not assume FAISS, sentence-transformers, or any particular backend.
    """

    async def retrieve(self, query: str, k: int) -> list[FewShotExample]:
        ...


class NullRetriever:
    """Default retriever: always returns no examples.

    Used until a real retriever and a populated golden index exist
    (gated on task #208). With this retriever the resolver always
    produces control behaviour even for treatment-variant users.
    """

    async def retrieve(self, query: str, k: int) -> list[FewShotExample]:  # noqa: ARG002
        return []


@dataclass(frozen=True)
class ResolvedActiveLearning:
    """Result of the resolution stage, ready to pass into config.

    Attributes:
        assignment: The resolved variant, or ``None`` if the flag service
            was unavailable / the flag is not configured.
        examples: Retrieved few-shot examples. Empty for control variant,
            for retriever failures, or when no index is populated.
    """

    assignment: FlagAssignment | None
    examples: list[FewShotExample]

    def as_config_overrides(self) -> dict[str, object]:
        """Render the keys the sync hook reads from config["configurable"]."""

        return {
            "active_learning_assignment": self.assignment,
            "active_learning_examples": self.examples,
        }


class ActiveLearningResolver:
    """Orchestrates flag assignment + few-shot retrieval (async stage).

    Construction is cheap (no I/O). ``resolve`` is the only
    network-touching method, and it never raises on degraded paths —
    the experiment layer must not break a citizen turn.
    """

    def __init__(
        self,
        flag_client: FlagClient,
        retriever: FewShotRetriever | None = None,
        flag_name: str = "active_learning_v1",
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._flag_client = flag_client
        self._retriever = retriever or NullRetriever()
        self._flag_name = flag_name
        self._top_k = top_k

    async def resolve(self, user_id: str, query: str) -> ResolvedActiveLearning:
        """Resolve variant + examples for ``user_id`` given the turn ``query``.

        Returns:
            ``ResolvedActiveLearning`` with assignment + examples. On any
            degraded path (flag unavailable, control variant, retriever
            failure), examples is empty and the downstream hook is a no-op.
        """

        assignment = await self._flag_client.assign(self._flag_name, user_id)
        if assignment is None or assignment.variant != TREATMENT_VARIANT:
            return ResolvedActiveLearning(assignment=assignment, examples=[])

        try:
            examples = await self._retriever.retrieve(query, self._top_k)
        except Exception as exc:  # noqa: BLE001 — experiment layer must not break turn
            logger.warning(
                f"[Active Learning] retriever failed for user={user_id}: {exc}; "
                "degrading to control behaviour"
            )
            return ResolvedActiveLearning(assignment=assignment, examples=[])

        return ResolvedActiveLearning(assignment=assignment, examples=examples)
