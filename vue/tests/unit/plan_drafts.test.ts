import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createApp, h, nextTick, ref, type App } from "vue";
import { ElButton } from "element-plus";
import PlanDraftActions from "@/components/PlanDraftActions.vue";
import * as api from "@/api/plan_draft_api";
import { ApiError } from "@/api/http_client";
import contract from "@/types/stream.contract.json";
import type { ApprovalVO, PlanDraftVO } from "@/types/api";

vi.mock("@/api/plan_draft_api", () => ({
  getDraft: vi.fn(), updateDraft: vi.fn(), submitDraft: vi.fn(), generateDraft: vi.fn(),
}));
const sample = () => structuredClone(contract.events.find(e => e.type === "final" && e.kind === "draft")!.result) as PlanDraftVO;
const approval = () => structuredClone(contract.events.find(e => e.type === "final" && e.kind === "approval")!.result) as ApprovalVO;
let app: App | undefined;
let root: HTMLDivElement;
const onSubmitted = vi.fn();
function mount(value = sample()) {
  root = document.createElement("div"); document.body.append(root);
  const draft = ref(value);
  app = createApp({ setup: () => () => h(PlanDraftActions, {
    draft: draft.value, disabled: false, onUpdate: value => { draft.value = value; }, onSubmitted,
  }) });
  app.component("ElButton", ElButton); app.mount(root);
}
function button(label: string) {
  const result = [...root.querySelectorAll("button")].find(el => el.textContent?.trim() === label);
  expect(result, label).toBeDefined(); return result!;
}
async function click(label: string) { button(label).click(); await nextTick(); }
async function editTitle() {
  await click("编辑草案");
  const input = root.querySelector("fieldset input") as HTMLInputElement;
  input.value = "成员编辑的订单校验"; input.dispatchEvent(new Event("input", { bubbles: true }));
  await nextTick(); return input;
}
beforeEach(() => vi.resetAllMocks());
afterEach(() => { app?.unmount(); app = undefined; root?.remove(); });

it("编辑只改变副本；保存确切版本后送审，不重新生成", async () => {
  const original = sample(); mount(original);
  await editTitle();
  expect(original.plan.proposal.tasks[0]!.title).toBe("实现下单校验");
  expect(root.textContent).not.toContain("提交这一版");
  vi.mocked(api.updateDraft).mockImplementation(async (_project, _id, body) => ({
    ...original, version: 2, plan: { ...original.plan, proposal: body.proposal },
  }));
  await click("保存修改");
  await vi.waitFor(() => expect(root.textContent).toContain("第 2 版"));
  expect(api.updateDraft).toHaveBeenCalledWith(original.project_id, original.id,
    expect.objectContaining({ version: 1, proposal: expect.objectContaining({
      tasks: expect.arrayContaining([expect.objectContaining({ title: "成员编辑的订单校验" })]),
    }) }), expect.any(AbortSignal));
  vi.mocked(api.submitDraft).mockResolvedValue(approval());
  await click("提交这一版");
  await vi.waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(approval()));
  expect(api.submitDraft).toHaveBeenCalledWith(original.project_id, original.id, 2, expect.any(AbortSignal), expect.any(Function));
  expect(api.generateDraft).not.toHaveBeenCalled();
  expect(root.textContent).not.toContain("编辑草案");
});

it("409 保留本地编辑，显式放弃后才载入最新版本", async () => {
  mount(); const input = await editTitle();
  vi.mocked(api.updateDraft).mockRejectedValue(new ApiError("草案已被修改", 409, "draft_version_conflict", "conflict-id"));
  await click("保存修改");
  await vi.waitFor(() => expect(root.textContent).toContain("conflict-id"));
  expect(input.value).toBe("成员编辑的订单校验");
  expect(button("保存修改").disabled).toBe(true);
  expect(api.getDraft).not.toHaveBeenCalled();
  vi.mocked(api.getDraft).mockResolvedValue({ ...sample(), version: 3 });
  await click("放弃本地修改并载入最新草案");
  await vi.waitFor(() => expect(root.textContent).toContain("第 3 版"));
  expect(root.querySelector("fieldset")).toBeNull();
});

it("重复点击只送审一次，取消后可重试原草案，卸载忽略迟到结果", async () => {
  const original = sample(); mount(original);
  vi.mocked(api.submitDraft).mockImplementation((_p, _d, _v, signal) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("取消", "AbortError")), { once: true });
  }));
  await click("提交这一版"); await click("提交这一版");
  expect(api.submitDraft).toHaveBeenCalledTimes(1);
  await click("停止等待");
  await vi.waitFor(() => expect(root.textContent).toContain("服务器可能已保存结果"));
  let resolve!: (value: ApprovalVO) => void;
  vi.mocked(api.submitDraft).mockReturnValue(new Promise(done => { resolve = done; }));
  await click("提交这一版");
  expect(api.submitDraft).toHaveBeenLastCalledWith(original.project_id, original.id, original.version, expect.any(AbortSignal), expect.any(Function));
  app!.unmount(); app = undefined;
  expect(vi.mocked(api.submitDraft).mock.calls[1]![3].aborted).toBe(true);
  resolve(approval()); await nextTick(); await nextTick();
  expect(onSubmitted).not.toHaveBeenCalled();
  expect(api.generateDraft).not.toHaveBeenCalled();
});
