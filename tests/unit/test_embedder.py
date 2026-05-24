"""Unit tests for ``engine.active_learning.embedder``.

Coverage targets:
- ``ready`` reflects API key presence without performing I/O.
- ``embed`` rejects empty / whitespace input.
- ``embed`` returns float32 array of declared dimension.
- ``embed_batch`` handles empty list and rejects empty entries.
- ``embed_batch`` returns one vector per input in order.
- Dimension / shape mismatch from upstream raises ``GeminiEmbedderError``.
- Missing API key raises a config error (not a runtime crash).
- ``GeminiEmbedder`` satisfies the ``Embedder`` Protocol structurally.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.active_learning.embedder import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    MAX_BATCH_SIZE,
    Embedder,
    GeminiEmbedder,
    GeminiEmbedderConfig,
    GeminiEmbedderError,
)


class _FakeClient:
    """Stand-in for langchain GoogleGenerativeAIEmbeddings."""

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIMENSION):
        self._dimension = dimension
        self.embed_query_calls: list[str] = []
        self.embed_documents_calls: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls.append(text)
        # Deterministic-ish vector; values irrelevant for these tests.
        return [float(i) / self._dimension for i in range(self._dimension)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embed_documents_calls.append(list(texts))
        return [self.embed_query(text) for text in texts]


def _embedder_with_fake(client: _FakeClient) -> GeminiEmbedder:
    return GeminiEmbedder(client_factory=lambda: client)


def test_default_config_uses_documented_constants():
    config = GeminiEmbedderConfig()
    assert config.model == DEFAULT_EMBEDDING_MODEL
    assert config.dimension == DEFAULT_EMBEDDING_DIMENSION


def test_embed_returns_float32_array_of_declared_dimension():
    client = _FakeClient()
    embedder = _embedder_with_fake(client)
    vector = embedder.embed("hello")
    assert isinstance(vector, np.ndarray)
    assert vector.dtype == np.float32
    assert vector.shape == (DEFAULT_EMBEDDING_DIMENSION,)
    assert client.embed_query_calls == ["hello"]


@pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
def test_embed_rejects_empty_text(bad):
    embedder = _embedder_with_fake(_FakeClient())
    with pytest.raises(GeminiEmbedderError, match="non-empty"):
        embedder.embed(bad)


def test_embed_batch_empty_list_returns_empty():
    embedder = _embedder_with_fake(_FakeClient())
    assert embedder.embed_batch([]) == []


def test_embed_batch_rejects_empty_entry():
    embedder = _embedder_with_fake(_FakeClient())
    with pytest.raises(GeminiEmbedderError, match="non-empty"):
        embedder.embed_batch(["valid", "", "also valid"])


def test_embed_batch_returns_vectors_in_input_order():
    client = _FakeClient()
    embedder = _embedder_with_fake(client)
    vectors = embedder.embed_batch(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(v.shape == (DEFAULT_EMBEDDING_DIMENSION,) for v in vectors)
    assert client.embed_documents_calls == [["a", "b", "c"]]


def test_dimension_mismatch_raises_specific_error():
    client = _FakeClient(dimension=512)  # upstream returns wrong dim
    embedder = _embedder_with_fake(client)
    with pytest.raises(GeminiEmbedderError, match="dimension"):
        embedder.embed("hi")


def test_missing_api_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # Use default factory (no fake) so it tries to read env.
    embedder = GeminiEmbedder()
    with pytest.raises(GeminiEmbedderError, match="GOOGLE_API_KEY"):
        embedder.embed("hi")


def test_gemini_embedder_exposes_protocol_attributes():
    """Pyright assignability is checked at type-check time; here we only
    verify the runtime attribute surface so a future refactor that drops
    one method is caught immediately."""

    embedder = _embedder_with_fake(_FakeClient())
    assert hasattr(embedder, "dimension")
    assert hasattr(embedder, "embed")
    assert hasattr(embedder, "embed_batch")
    assert hasattr(embedder, "__call__")
    _typed: Embedder = embedder
    assert _typed.dimension == DEFAULT_EMBEDDING_DIMENSION


def test_callable_form_matches_embed_output():
    """Governance-repo retriever calls embedder as ``embedder(query)``."""

    embedder = _embedder_with_fake(_FakeClient())
    via_method = embedder.embed("hello")
    via_call = embedder("hello")
    assert np.array_equal(via_method, via_call)
    assert via_call.dtype == np.float32
    assert via_call.shape == (DEFAULT_EMBEDDING_DIMENSION,)


def test_coerce_rejects_2d_shape():
    """Upstream returning a batched 2-D shape must surface as an error,
    not a silent shape mismatch that crashes FAISS deeper."""

    class _Batched2DClient:
        def embed_query(self, text: str) -> list[list[float]]:
            return [[0.0] * DEFAULT_EMBEDDING_DIMENSION]

        def embed_documents(self, texts):
            return [[0.0] * DEFAULT_EMBEDDING_DIMENSION for _ in texts]

    embedder = GeminiEmbedder(client_factory=lambda: _Batched2DClient())
    with pytest.raises(GeminiEmbedderError, match="1-D"):
        embedder.embed("hi")


def test_coerce_widens_float64_to_float32():
    """Upstream sometimes returns float64; we cast down for FAISS memory."""

    class _Float64Client:
        def embed_query(self, text: str) -> np.ndarray:
            return np.zeros(DEFAULT_EMBEDDING_DIMENSION, dtype=np.float64)

        def embed_documents(self, texts):
            return [np.zeros(DEFAULT_EMBEDDING_DIMENSION, dtype=np.float64) for _ in texts]

    embedder = GeminiEmbedder(client_factory=lambda: _Float64Client())
    vector = embedder.embed("hi")
    assert vector.dtype == np.float32


def test_embed_batch_chunks_at_max_batch_size():
    """Defensive chunking: if upstream stops auto-chunking, we still
    slice safely to MAX_BATCH_SIZE."""

    class _ChunkAwareClient:
        def __init__(self):
            self.batches: list[int] = []

        def embed_query(self, text: str) -> list[float]:
            return [0.0] * DEFAULT_EMBEDDING_DIMENSION

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.batches.append(len(texts))
            return [[0.0] * DEFAULT_EMBEDDING_DIMENSION for _ in texts]

    client = _ChunkAwareClient()
    embedder = GeminiEmbedder(client_factory=lambda: client)
    # Force 2 chunks: MAX_BATCH_SIZE + 5.
    vectors = embedder.embed_batch(["x"] * (MAX_BATCH_SIZE + 5))
    assert len(vectors) == MAX_BATCH_SIZE + 5
    assert client.batches == [MAX_BATCH_SIZE, 5]


def test_client_factory_called_lazily():
    factory_calls: list[int] = []

    def factory():
        factory_calls.append(1)
        return _FakeClient()

    embedder = GeminiEmbedder(client_factory=factory)
    assert factory_calls == []  # no I/O on construction
    embedder.embed("hi")
    assert factory_calls == [1]
    embedder.embed("again")
    assert factory_calls == [1]  # cached after first build
