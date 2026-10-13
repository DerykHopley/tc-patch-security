# Overlap with ai-digest

> **Background.** Written 2026-10-12, when the domain was still AI news; the domain is now LLM security. The techniques still carry over to ai-digest.

This course project is separate from [ai-digest](../../ai-digest/), but it's a chance to research and try many of the ideas collected in [ai-digest/research/ideas.md](../../ai-digest/research/ideas.md). This file maps each requirement to those ideas and lists what could be brought back.

Written 2026-10-12. Nothing here is decided yet.

## The difference in shape

- ai-digest is mostly a pipeline that runs every evening and pushes a digest to me.
- This project is a chatbot I ask questions.
- The chatbot is the "ask a question" flow from ai-digest's [Architecture](../../ai-digest/research/ideas.md#architecture-how-the-parts-talk-to-each-other) idea: front end → retrieval → LLM → answer with citations.

## Requirements mapped to ai-digest ideas

| Requirement | Overlap | ai-digest idea or earlier work | What to bring back |
| --- | --- | --- | --- |
| Knowledge base, embeddings, chunking, similarity search | Strong | Retrieval approaches, Chunking large files, rag-langchain in tc-ai-experiments | Chunking that works on newsletters and transcripts, not only short profiles |
| Query translation | Gap | Not in the ideas yet | Which technique (multi-query, RAG-Fusion, decomposition, step-back, HyDE) actually improves retrieval, measured |
| Structured retrieval | Strong | The "facts in metadata filters, meaning in vectors" finding | A metadata schema for sources (type, date, author, topic) |
| At least 3 tool calls | Weak | `search_wiki` and `related_items` as MCP tools in tech-stack.md §4.1, agent-tools-mcp in tc-ai-experiments | Tools ai-digest would reuse |
| Domain and security measures | Strong | Guardrails, Security checklist: OWASP Top 10, Privacy, Local store for passwords and API keys | Guardrail checks as reusable code |
| LangChain + OpenRouter (suggested, optional) | Strong | Findings from the RAG experiments (LangChain.js friction) | Evidence for the TypeScript vs Python decision |
| Error handling, input validation | Strong | Guardrails (file size, URLs, schema), OWASP A10 | The same |
| UI (Streamlit or Next.js suggested), sources, tool results, progress | Medium | Web, desktop and mobile versions, Source citations, Visual elements | A tested answer for the web front end |

## Optional tasks mapped to ai-digest ideas

| Task | Level | ai-digest idea |
| --- | --- | --- |
| Visualisation of RAG process | Easy | Already done once: the rag-langchain walkthrough page |
| Source citations | Easy | Source citations everywhere |
| Conversation history and export | Easy | Not covered (loosely: Memory: Mem0) |
| Multi-model support | Medium | Nearly free through OpenRouter |
| Real-time data updates | Medium | The ingest flow in Architecture |
| Protect against prompt injection | Medium | Guardrails |
| User authentication | Medium | OWASP Top 10, Web, desktop and mobile versions |
| Token usage and costs | Medium | Usage statistics |
| Rate limiting and API key management | Medium | Local store for passwords and API keys |
| Logging and monitoring | Medium | Usage statistics (observability tools in tech-stack.md §5) |
| Remote MCP server tools | Medium | Touched in tech-stack.md §4.1 |
| Hybrid search | Hard | Retrieval approaches |
| A/B testing RAG strategies | Hard | Chunking eval question, embedding-model-comparison |
| Automated knowledge base updates | Hard | The evening routine itself |
| Multi-language support | Hard | Not covered |
| Analytics dashboard | Hard | Usage statistics |
| Tools as MCP servers | Hard | tech-stack.md §4.1 |
| RAG evaluation (RAGAs) | Hard | ragas-evaluation in tc-ai-experiments, Source citations, the Jev notebook |

Candidates for the bonus (2 medium, 1 hard) that also serve ai-digest: prompt injection and token usage and costs (medium), and automated knowledge base updates or hybrid search (hard).

## Gaps to fill here

- **Query translation:** a core requirement that doesn't appear in the ai-digest research.
- **Tools:** possible domain tools:
  - Fetch and summarise a URL.
  - Get a YouTube transcript with timestamps.
  - Compare model prices using OpenRouter's models API.
  - Add an item to the inbox.
  - Query usage statistics.
- **Chat features:** conversation history, memory and export.

## Rules for keeping the projects apart

- **Public data only.** No Scenarios, `interests.md` or Gmail content. Use public newsletters, articles and transcripts.
- **No course material** in anything published, including [REQUIREMENTS.md](./REQUIREMENTS.md).
- **Course choices aren't ai-digest decisions.** The brief's stack (LangChain, OpenRouter, Streamlit or Next.js) is only a suggestion, so this project can try what ai-digest is considering. Whatever turns up becomes evidence for ai-digest's stack questions, not a decision.
- **Bring back findings, not just code.** When something here answers an open question in `ideas.md`, write it there with a link, like the "Findings from the RAG experiments" section.
