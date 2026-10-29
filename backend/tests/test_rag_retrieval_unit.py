import uuid

import pytest

from app.llm.base import LLMError, LLMResult
from app.rag.reranking import LLMReranker
from app.rag.retrieval import keyword_query, reciprocal_rank_fusion


def test_keyword_query_ors_terms_and_keeps_identifiers():
    assert keyword_query("What caused INC-204?") == "What or caused or INC-204"
    assert keyword_query("  ?! ") == ""


def test_keyword_query_neutralizes_websearch_operators():
    # Quotes and leading minus would change websearch semantics; they are stripped.
    assert keyword_query('"exact" -excluded') == "exact or excluded"


def test_rrf_rewards_agreement_between_rankings():
    a, b, c = (uuid.uuid4() for _ in range(3))
    scores = reciprocal_rank_fusion([[a, b, c], [b, a]], k=60)
    assert scores[a] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[b] == scores[a]
    assert scores[c] == pytest.approx(1 / 63)
    assert max(scores, key=scores.get) in {a, b}


class ScriptedLLM:
    provider, model = "stub", "stub"

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def complete(self, messages):
        self.prompts.append(messages[-1].content)
        if isinstance(self.reply, Exception):
            raise self.reply
        return LLMResult(content=self.reply, model="stub")


async def test_llm_reranker_parses_scores():
    llm = ScriptedLLM('Sure: {"scores": [2, 9.5, 0]}')
    scores = await LLMReranker(llm).score("q", ["p1", "p2", "p3"])
    assert scores == [2.0, 9.5, 0.0]
    assert "[2] p2" in llm.prompts[0]


@pytest.mark.parametrize(
    "reply",
    [
        '{"scores": [1, 2]}',
        "not json",
        '{"other": []}',
        '{"scores": ["a", "b", "c"]}',
        LLMError("x"),
    ],
)
async def test_llm_reranker_falls_back_to_none_on_bad_output(reply):
    assert await LLMReranker(ScriptedLLM(reply)).score("q", ["a", "b", "c"]) is None
