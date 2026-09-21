export function finalResponse(kind: "knowledge" | "planning" | "workflow", result: unknown) {
  return {
    contentType: "application/x-ndjson",
    body: JSON.stringify({ version: 1, seq: 1, request_id: "browser-test", type: "final", kind, result }) + "\n",
  };
}
