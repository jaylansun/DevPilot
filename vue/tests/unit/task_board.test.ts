import { effectScope, ref, type EffectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listTasks } from "@/api/task_api";
import { useTaskBoard } from "@/composables/use_task_board";
import type { TaskPageVO, TaskVO } from "@/types/api";

vi.mock("@/api/task_api", () => ({ listTasks: vi.fn() }));
const listMock = vi.mocked(listTasks);
const scopes: EffectScope[] = [];
const page = (
  items: TaskVO[] = [],
  total = items.length,
  offset = 0,
): TaskPageVO => ({ items, total, offset, limit: 8 });
const task = (id: string): TaskVO => ({
  id,
  project_id: "project-id",
  title: id,
  description: "",
  priority: 3,
  status: "todo",
  acceptance_criteria: "",
  source: "manual",
  version: 1,
  created_at: "",
  updated_at: "",
});
const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};
function setup() {
  const scope = effectScope();
  scopes.push(scope);
  const projectId = ref("project-id");
  return { board: scope.run(() => useTaskBoard(projectId))!, projectId, scope };
}
beforeEach(() => {
  listMock.mockReset();
  listMock.mockResolvedValue(page());
});
afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop());
});

describe("任务看板分页和请求竞争", () => {
  it("三个状态独立分页，筛选后只读取对应列", async () => {
    const { board } = setup();
    await flush();
    expect(listMock).toHaveBeenCalledTimes(3);
    expect(listMock).toHaveBeenCalledWith("project-id", {
      status: "todo",
      priority: undefined,
      offset: 0,
      limit: 8,
    });
    listMock.mockClear();
    board.statusFilter.value = "done";
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(board.visibleColumns.value.map((column) => column.status)).toEqual([
      "done",
    ]);
    board.priorityFilter.value = 1;
    await flush();
    expect(listMock).toHaveBeenLastCalledWith("project-id", {
      status: "done",
      priority: 1,
      offset: 0,
      limit: 8,
    });
  });
  it("追加分页按 ID 去重，但下一页位置使用服务器返回的记录数量", async () => {
    listMock.mockImplementation(async (_, query) =>
      query?.status === "todo" ? page([task("1"), task("2")], 5) : page(),
    );
    const { board } = setup();
    await flush();
    listMock.mockResolvedValueOnce(page([task("2"), task("3")], 5, 2));
    await board.loadColumn("todo", true);
    expect(board.columns.todo.items.map((task) => task.id)).toEqual([
      "1",
      "2",
      "3",
    ]);
    expect(board.columns.todo.nextOffset).toBe(4);
    listMock.mockResolvedValueOnce(page([task("4")], 5, 4));
    await board.loadColumn("todo", true);
    expect(listMock).toHaveBeenLastCalledWith(
      "project-id",
      expect.objectContaining({ offset: 4 }),
    );
  });
  it("旧筛选请求的迟到响应不会覆盖新筛选结果", async () => {
    let finishOld!: (value: TaskPageVO) => void;
    listMock.mockImplementation((_, query) =>
      query?.status === "todo" && !query.priority
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve(page()),
    );
    const { board } = setup();
    board.priorityFilter.value = 1;
    await flush();
    finishOld(page([task("旧数据")]));
    await flush();
    expect(board.columns.todo.items).toEqual([]);
    expect(board.columns.todo.loading).toBe(false);
  });
  it("一列失败不影响其他列，重试后恢复", async () => {
    listMock.mockImplementation(async (_, query) => {
      if (query?.status === "todo") throw new Error("读取任务失败");
      return page([task("正常任务")]);
    });
    const { board } = setup();
    await flush();
    expect(board.columns.todo.error).toBe("读取任务失败");
    expect(board.columns.done.items).toHaveLength(1);
    listMock.mockResolvedValueOnce(page([task("恢复任务")]));
    await board.loadColumn("todo");
    expect(board.columns.todo.error).toBe("");
    expect(board.columns.todo.items[0]?.id).toBe("恢复任务");
  });
  it("离开页面后不会将迟到响应写入旧看板", async () => {
    let finish!: (value: TaskPageVO) => void;
    listMock.mockImplementation((_, query) =>
      query?.status === "todo"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : Promise.resolve(page()),
    );
    const { board, scope } = setup();
    scope.stop();
    finish(page([task("迟到任务")]));
    await flush();
    expect(board.columns.todo.items).toEqual([]);
  });
});
