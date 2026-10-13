import { useState } from "react";
import { ApiError, chat, type Turn } from "../api";
import type { Message } from "../components/Chat";

// The backend accepts at most 10 history turns of 2000 characters each (V1).
const MAX_TURNS = 10;
const MAX_TURN_CHARS = 2000;

// U2: the last 10 turns that really happened. A failed request and the question that caused it are left out.
function toHistory(messages: Message[]): Turn[] {
  return messages
    .filter((m, i) => !m.error && !messages[i + 1]?.error)
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_TURN_CHARS) }));
}

// One conversation for the whole app, so switching layout or page never loses it.
export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [unread, setUnread] = useState(false);

  async function send(text: string) {
    if (pending) return;
    const history = toHistory(messages);
    const answerIndex = messages.length + 1; // after the user message added below
    setMessages((ms) => [...ms, { role: "user", content: text }]);
    setPending(true);
    try {
      const reply = await chat(text, history);
      setMessages((ms) => [...ms, { role: "assistant", content: reply.answer, reply }]);
      setSelected(answerIndex);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
      setMessages((ms) => [...ms, { role: "assistant", content: "", error: message }]);
    } finally {
      setPending(false);
      setUnread(true);
    }
  }

  function newChat() {
    setMessages([]);
    setSelected(null);
  }

  return { messages, pending, selected, setSelected, send, newChat, unread, markRead: () => setUnread(false) };
}

export type ChatState = ReturnType<typeof useChat>;
