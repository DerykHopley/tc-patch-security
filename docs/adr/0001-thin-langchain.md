# Thin LangChain: the model client only

The course brief lists "Use LangChain with OpenRouter" as a core requirement, but the prototype hand-writes every RAG stage so each one can be shown and explained. We use LangChain only at the `LLM` seam: `ChatOpenAI` from `langchain-openai`, pointed at OpenRouter or a local OpenAI-compatible server, with tools declared through `@tool` and `bind_tools`. The agent loop, retrieval, filter validation, RRF and the per-document cap stay our own code. Decided 2026-10-14.

## Considered options

- **No LangChain:** risks marks on a core line of the brief.
- **Full LangChain (LangGraph agent, `SelfQueryRetriever`, `EnsembleRetriever`):** `SelfQueryRetriever` hands the LLM's filters straight to the store, skipping the server-side check that keeps a question inside the data. It also hides the steps the search playground shows.

## Consequences

- Don't "upgrade" retrieval to LangChain retrievers without moving the filter check in front of them.
- FakeLLM is our own class above the seam, so tests need no key and no network.
