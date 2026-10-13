import { useEffect, useRef, useState } from "react";
import type { Mood } from "../components/Robot";
import type { ChatState } from "./useChat";

// Patch's mood from the chat: thinking while an answer is on its way, happy for a few seconds when it lands,
// alert after an error, idle otherwise.
export function useMood(chat: ChatState): Mood {
  const [happy, setHappy] = useState(false);
  const count = useRef(chat.messages.length);
  useEffect(() => {
    const grew = chat.messages.length > count.current;
    count.current = chat.messages.length;
    if (!grew || chat.messages.at(-1)?.role !== "assistant") return;
    setHappy(true);
    const t = setTimeout(() => setHappy(false), 3000);
    return () => clearTimeout(t);
  }, [chat.messages]);
  if (chat.pending) return "thinking";
  if (chat.messages.at(-1)?.error) return "alert";
  return happy ? "happy" : "idle";
}
