import type { Usage } from "../api";

// U8: token usage under each answer, labelled "estimated" with FakeLLM.
export function UsageLine({ usage, steps }: { usage: Usage; steps: number }) {
  return (
    <p className="usage">
      {usage.input_tokens.toLocaleString()} in · {usage.output_tokens.toLocaleString()} out ·{" "}
      {usage.llm_calls} LLM calls · {steps} steps
      {usage.estimated && <span className="chip">estimated</span>}
    </p>
  );
}
