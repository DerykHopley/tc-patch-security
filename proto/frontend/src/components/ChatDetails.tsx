import { useState } from "react";
import type { ChatReply } from "../api";
import { QueryPanel } from "./QueryPanel";
import { SourcesPanel } from "./SourcesPanel";
import { ToolCallCard } from "./ToolCallCard";

type Tab = "sources" | "tools" | "query";

// An answer's sources, tool calls and query plan as tabs: the overlay layouts show these inline, under the answer.
export function ChatDetails({ reply, idPrefix, initial = "sources" }: { reply: ChatReply; idPrefix: string; initial?: Tab }) {
  const [tab, setTab] = useState<Tab>(reply.sources.length ? initial : reply.tool_calls.length ? "tools" : "query");
  const tabs: { id: Tab; label: string; n?: number; show: boolean }[] = [
    { id: "sources", label: "Sources", n: reply.sources.length, show: true },
    { id: "tools", label: "Tool calls", n: reply.tool_calls.length, show: reply.tool_calls.length > 0 },
    { id: "query", label: "Query plan", show: !!reply.query },
  ];
  return (
    <div className="chat-details">
      <div className="detail-tabs" role="tablist">
        {tabs.filter((t) => t.show).map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}{t.n !== undefined && <span className="count">{t.n}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "sources" && <SourcesPanel sources={reply.sources} idPrefix={idPrefix} />}
        {tab === "tools" && reply.tool_calls.map((c) => <ToolCallCard key={c.id} call={c} />)}
        {tab === "query" && reply.query && <QueryPanel query={reply.query} />}
      </div>
    </div>
  );
}
