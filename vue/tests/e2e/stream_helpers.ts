export function finalResponse(kind: "knowledge" | "planning" | "workflow" | "draft" | "approval", result: unknown) {
  return {
    contentType: "application/x-ndjson",
    body: JSON.stringify({ version: 1, seq: 1, request_id: "browser-test", type: "final", kind, result }) + "\n",
  };
}

export function savedDraft(projectId: string, goal: string, plan: unknown) {
  return { id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", project_id: projectId, goal,
    version: 1, status: "draft", conversation_id: null,
    created_at: "2026-09-23T00:00:00Z", updated_at: "2026-09-23T00:00:00Z",
    plan: { ...(plan as object), persisted: true } };
}
