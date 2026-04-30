import tiktoken
import pytest

from rag.chunker import TextChunker, _CHUNK_SIZE, _OVERLAP, _ENCODING

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def chunker() -> TextChunker:
    return TextChunker()


def _text_of_tokens(n: int) -> str:
    """Return a string that encodes to exactly n tokens using cl100k_base."""
    # "hello" encodes to 1 token in cl100k_base; build a sentence of n words
    word = "hello"
    tokens_per_word = len(_ENCODING.encode(word + " ")) - len(_ENCODING.encode(" "))
    words = [word] * n
    text = " ".join(words)
    # Trim or pad to hit exactly n tokens
    toks = _ENCODING.encode(text)
    if len(toks) > n:
        text = _ENCODING.decode(toks[:n])
    return text


# ── Basic chunking ────────────────────────────────────────────────────────────

def test_chunk_returns_list(chunker: TextChunker) -> None:
    chunks = chunker.chunk("Hello world", "doc.txt")
    assert isinstance(chunks, list)


def test_empty_text_returns_empty_list(chunker: TextChunker) -> None:
    assert chunker.chunk("", "doc.txt") == []


def test_short_text_produces_single_chunk(chunker: TextChunker) -> None:
    text = "This is a short paragraph."
    chunks = chunker.chunk(text, "doc.txt")
    assert len(chunks) == 1


def test_chunk_dict_has_required_keys(chunker: TextChunker) -> None:
    chunks = chunker.chunk("Some text here.", "notes.txt")
    chunk = chunks[0]
    assert set(chunk.keys()) == {"text", "source_doc", "chunk_index", "metadata"}


def test_source_doc_propagated(chunker: TextChunker) -> None:
    chunks = chunker.chunk("hello world", "my_document.pdf")
    assert all(c["source_doc"] == "my_document.pdf" for c in chunks)


def test_chunk_indices_are_sequential(chunker: TextChunker) -> None:
    # Generate enough text to produce multiple chunks
    long_text = " ".join(["word"] * 2000)
    chunks = chunker.chunk(long_text, "big.txt")
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


# ── Token size verification ───────────────────────────────────────────────────

def test_each_chunk_fits_within_chunk_size(chunker: TextChunker) -> None:
    long_text = " ".join(["keyword"] * 2000)
    chunks = chunker.chunk(long_text, "large.txt")
    for chunk in chunks:
        token_count = len(_ENCODING.encode(chunk["text"]))
        assert token_count <= _CHUNK_SIZE, (
            f"Chunk {chunk['chunk_index']} has {token_count} tokens, "
            f"exceeds limit of {_CHUNK_SIZE}"
        )


def test_metadata_token_count_is_accurate(chunker: TextChunker) -> None:
    text = " ".join(["word"] * 600)
    chunks = chunker.chunk(text, "doc.txt")
    for chunk in chunks:
        actual_tokens = len(_ENCODING.encode(chunk["text"]))
        assert chunk["metadata"]["token_count"] == actual_tokens


def test_chunk_count_matches_expected_formula(chunker: TextChunker) -> None:
    # 1000-token text with 512 chunk size and 50 overlap:
    # stride = 512 - 50 = 462
    # chunks = ceil((1000 - 50) / 462) + 1 ≈ 3
    total_tokens = 1000
    text = " ".join(["a"] * total_tokens)
    actual_total = len(_ENCODING.encode(text))

    chunks = chunker.chunk(text, "doc.txt")

    stride = _CHUNK_SIZE - _OVERLAP
    import math
    expected_min = math.ceil(actual_total / _CHUNK_SIZE)
    expected_max = math.ceil(actual_total / stride) + 1
    assert expected_min <= len(chunks) <= expected_max


# ── Overlap verification ──────────────────────────────────────────────────────

def test_consecutive_chunks_share_overlapping_tokens(chunker: TextChunker) -> None:
    long_text = " ".join(["overlap"] * 2000)
    chunks = chunker.chunk(long_text, "doc.txt")

    assert len(chunks) >= 2, "Need at least 2 chunks to verify overlap"

    tokens_0 = _ENCODING.encode(chunks[0]["text"])
    tokens_1 = _ENCODING.encode(chunks[1]["text"])

    # The tail of chunk 0 and the head of chunk 1 must share _OVERLAP tokens
    tail = tokens_0[-_OVERLAP:]
    head = tokens_1[:_OVERLAP]
    assert tail == head, "Expected overlapping tokens between consecutive chunks"


# ── Strategy validation ───────────────────────────────────────────────────────

def test_unknown_strategy_raises_value_error(chunker: TextChunker) -> None:
    with pytest.raises(ValueError, match="Unknown chunking strategy"):
        chunker.chunk("text", "doc.txt", strategy="sliding_sentence")


def test_fixed_is_default_strategy(chunker: TextChunker) -> None:
    chunks_default = chunker.chunk("hello world", "doc.txt")
    chunks_explicit = chunker.chunk("hello world", "doc.txt", strategy="fixed")
    assert chunks_default == chunks_explicit
