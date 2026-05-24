"""Gemini text-embedding adapter for few-shot retrieval.

Scope
~~~~~
Real-embedding adapter consumed by the FAISS retriever in the governance
repo (``local-dual-bot/active_learning/retriever.py``). Replaces the
deterministic ``hashlib.md5`` mock used in Iter 2 Phase C E2E with the
production ``text-embedding-004`` (768-dim) model.

Protocol
~~~~~~~~
We define the ``Embedder`` Protocol locally (intentionally not imported
from the governance repo — Engine stays self-contained). Any callable
matching ``embed(text: str) -> np.ndarray`` of dtype ``float32`` and
shape ``(dimension,)`` satisfies it.

Cost / quota
~~~~~~~~~~~~
- ``text-embedding-004`` pricing is per character; few-shot retrieval
  embeds at most ~3 query texts per turn at runtime (one per active flag
  variant=treatment user). Annotation-time embedding (batch over the
  golden set) is paid once per refresh.
- Hard 100-string batch limit on the upstream API. ``embed_batch``
  delegates to ``embed_documents`` which chunks transparently.
- This module does NOT cache. Caller (retriever) is responsible for
  caching annotation-time embeddings to disk (FAISS index serialisation
  already does this in the governance repo).

Limitations
~~~~~~~~~~~
- task_type defaults to ``SEMANTIC_SIMILARITY`` because we compare query
  ↔ document directly. If the retriever shifts to asymmetric retrieval
  (``RETRIEVAL_QUERY`` vs ``RETRIEVAL_DOCUMENT``), pass the type via
  ``task_type`` per call.
- No retry policy here. Upstream langchain client handles retries; if
  this proves insufficient (observed in prod), wrap with httpx retry
  in Iter 3+.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

import numpy as np

from engine.log import logger

DEFAULT_EMBEDDING_MODEL: Final[str] = "models/text-embedding-004"
DEFAULT_EMBEDDING_DIMENSION: Final[int] = 768
DEFAULT_TASK_TYPE: Final[str] = "SEMANTIC_SIMILARITY"
ENV_GOOGLE_API_KEY: Final[str] = "GOOGLE_API_KEY"
# langchain_google_genai documents a hard 100-string batch limit on the
# upstream API. Defensive chunking lives in embed_batch so an upstream
# regression that stops auto-chunking won't surface as opaque 4xx.
MAX_BATCH_SIZE: Final[int] = 100


class Embedder(Protocol):
    """Minimal text → embedding contract.

    Implementations must return a 1-D ``float32`` numpy array. Callers
    rely on ``len(vector) == dimension`` matching the FAISS index dim.

    Dual-shape contract: implementations expose both ``embed(text)`` and
    ``__call__(text)`` so they satisfy:
    - The Engine-side Protocol declared here (named method).
    - The governance-repo retriever Protocol (callable form,
      ``local-dual-bot/active_learning/retriever.py``).
    The two protocols diverged historically; ``GeminiEmbedder`` bridges
    them so a single instance plugs into both consumers.
    """

    dimension: int

    def embed(self, text: str) -> np.ndarray:
        ...

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        ...

    def __call__(self, text: str) -> np.ndarray:
        ...


@dataclass(frozen=True)
class GeminiEmbedderConfig:
    """Construction-time options for ``GeminiEmbedder``."""

    model: str = DEFAULT_EMBEDDING_MODEL
    dimension: int = DEFAULT_EMBEDDING_DIMENSION
    task_type: str = DEFAULT_TASK_TYPE
    api_key: str | None = None


class GeminiEmbedderError(Exception):
    """Configuration or upstream failure that prevents embedding."""


class GeminiEmbedder:
    """Gemini ``text-embedding-004`` adapter implementing ``Embedder``.

    Construction lazily defers client instantiation until first use so
    the module can be imported in environments without credentials
    (tests, type-check). Use ``ready`` to check whether the client could
    be built without performing I/O.
    """

    def __init__(
        self,
        config: GeminiEmbedderConfig | None = None,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._config = config or GeminiEmbedderConfig()
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None

    @property
    def dimension(self) -> int:
        return self._config.dimension

    def _default_client_factory(self):
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as exc:
            logger.warning(
                "GeminiEmbedder cannot construct client: "
                "langchain_google_genai not installed"
            )
            raise GeminiEmbedderError(
                "langchain_google_genai is required for GeminiEmbedder"
            ) from exc

        api_key = self._config.api_key or os.getenv(ENV_GOOGLE_API_KEY)
        if not api_key:
            logger.warning(
                "GeminiEmbedder cannot construct client: "
                "GOOGLE_API_KEY env var missing and no config.api_key"
            )
            raise GeminiEmbedderError(
                "GeminiEmbedder requires GOOGLE_API_KEY env var or config.api_key"
            )

        return GoogleGenerativeAIEmbeddings(
            model=self._config.model,
            task_type=self._config.task_type,
            google_api_key=api_key,
        )

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        if self._client is None:
            raise GeminiEmbedderError("client_factory returned None")
        return self._client

    def embed(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            raise GeminiEmbedderError("embed() requires non-empty text")
        client = self._ensure_client()
        vector = client.embed_query(text)
        return self._coerce_vector(vector)

    def __call__(self, text: str) -> np.ndarray:
        """Callable form — satisfies the governance retriever Protocol.

        Same contract as ``embed``; provided so a single ``GeminiEmbedder``
        instance plugs into both Engine-side ``Embedder`` consumers and
        governance-repo retrievers that expect a callable.
        """

        return self.embed(text)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        if any(not text or not text.strip() for text in texts):
            raise GeminiEmbedderError("embed_batch() requires non-empty texts")
        client = self._ensure_client()
        # Defensive chunking. langchain_google_genai docs the 100-string
        # batch limit; if it stops auto-chunking, we still slice safely.
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH_SIZE):
            chunk = texts[start : start + MAX_BATCH_SIZE]
            all_vectors.extend(client.embed_documents(chunk))
        return [self._coerce_vector(vector) for vector in all_vectors]

    def _coerce_vector(self, vector: Any) -> np.ndarray:
        # ``dtype=np.float32`` deliberately copies float64 upstream output
        # to bound memory for FAISS index storage; do not "optimize" it
        # to ``np.asarray(vector)`` without dtype.
        array = np.asarray(vector, dtype=np.float32)
        if array.ndim != 1:
            raise GeminiEmbedderError(
                f"GeminiEmbedder expected 1-D vector, got shape {array.shape}"
            )
        if array.shape[0] != self._config.dimension:
            raise GeminiEmbedderError(
                f"GeminiEmbedder expected dimension {self._config.dimension}, "
                f"got {array.shape[0]}"
            )
        return array
