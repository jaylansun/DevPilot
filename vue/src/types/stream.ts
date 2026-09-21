import type { ApprovalVO, PlanResultVO, RagAnswerVO, WorkflowResultVO } from "./api";

export const stepNames = [
  "retrieve_knowledge", "answer_knowledge", "validate_result", "classify_intent",
  "load_lookup_board", "answer_lookup", "retrieve_documents", "load_task_board",
  "generate_report", "clarify", "draft_proposal", "search_documents", "read_task_board", "submit_approval", "apply_approval",
] as const;
export type StepName = typeof stepNames[number];
export type EventBase = { version: 1; seq: number; request_id: string };
export type TraceEvent = EventBase & {
  type: "node" | "tool"; id: string; name: StepName;
  status: "started" | "completed" | "failed";
};
export type TokenEvent = EventBase & { type: "token"; text: string };
export type ApprovalRequiredEvent = EventBase & { type: "approval_required"; approval: ApprovalVO };
export type ProgressEvent = TraceEvent | TokenEvent | ApprovalRequiredEvent;
export type Results = { knowledge: RagAnswerVO; planning: PlanResultVO; workflow: WorkflowResultVO; approval: ApprovalVO };
export type RunKind = keyof Results;
export type FinalEvent = {
  [K in RunKind]: EventBase & { type: "final"; kind: K; result: Results[K] }
}[RunKind];
export type StreamEvent = ProgressEvent | FinalEvent | (EventBase & {
  type: "error"; status: number;
  error: { code: string; message: string; request_id: string; details: unknown };
});
