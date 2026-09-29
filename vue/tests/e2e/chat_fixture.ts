import { randomUUID } from "node:crypto";
import type { Route } from "@playwright/test";
import type { ChatAnswerVO, ChatSessionVO, SavedChatMessageVO } from "../../src/types/api";

export class ChatFixture {
  sessions: ChatSessionVO[] = [];
  messages = new Map<string, SavedChatMessageVO[]>();

  record(path: string, payload: { question: string; client_message_id: string }, answer: ChatAnswerVO) {
    const id = path.split("/sessions/")[1]!.split("/")[0]!;
    const session = this.sessions.find(s => s.id === id)!;
    const messages = this.messages.get(id)!;
    const old = messages.find(m => m.client_message_id === payload.client_message_id);
    if (old) { old.answer = answer; old.status = "completed"; return; }
    messages.push({ id: randomUUID(), client_message_id: payload.client_message_id, question: payload.question,
      seq: messages.length + 1, answer, status: "completed", error: null, created_at: new Date().toISOString() });
    if (messages.length === 1) session.title = payload.question;
    session.updated_at = new Date().toISOString();
  }

  async handle(route: Route): Promise<boolean> {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path.endsWith("/chat/sessions")) {
      if (method === "POST") {
        const session: ChatSessionVO = { id: randomUUID(), title: "新对话", created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
        this.sessions.unshift(session); this.messages.set(session.id, []);
        await route.fulfill({ status: 201, json: session });
      } else await route.fulfill({ json: this.sessions.slice(Number(url.searchParams.get("offset") ?? 0), 50) });
      return true;
    }
    if (/\/chat\/sessions\/[^/]+$/.test(path)) {
      const id = path.split("/").at(-1)!;
      if (method === "DELETE") {
        this.sessions = this.sessions.filter(s => s.id !== id); this.messages.delete(id);
        await route.fulfill({ status: 204 });
      } else await route.fulfill({ json: { session: this.sessions.find(s => s.id === id), messages: this.messages.get(id), has_more: false } });
      return true;
    }
    return false;
  }
}
