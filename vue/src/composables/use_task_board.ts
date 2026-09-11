import { computed, onScopeDispose, reactive, ref, watch, type Ref } from "vue";
import { listTasks } from "@/api/task_api";
import { errorMessage } from "@/api/http_client";
import { TASK_COLUMNS } from "@/utils/task_form";
import type { TaskStatus, TaskVO } from "@/types/api";

type ColumnState = {
  items: TaskVO[];
  total: number;
  nextOffset: number;
  loading: boolean;
  error: string;
};
const PAGE_SIZE = 8;
const emptyColumn = (): ColumnState => ({
  items: [],
  total: 0,
  nextOffset: 0,
  loading: false,
  error: "",
});

export function useTaskBoard(projectId: Ref<string>) {
  const statusFilter = ref<TaskStatus | "">("");
  const priorityFilter = ref<number | "">("");
  const columns = reactive<Record<TaskStatus, ColumnState>>({
    todo: emptyColumn(),
    in_progress: emptyColumn(),
    done: emptyColumn(),
  });
  const tickets: Record<TaskStatus, number> = {
    todo: 0,
    in_progress: 0,
    done: 0,
  };
  let disposed = false;
  const visibleColumns = computed(() =>
    TASK_COLUMNS.filter(
      (column) => !statusFilter.value || column.status === statusFilter.value,
    ),
  );
  const loading = computed(() =>
    visibleColumns.value.some((column) => columns[column.status].loading),
  );
  const hasError = computed(() =>
    visibleColumns.value.some((column) => columns[column.status].error),
  );
  const total = computed(() =>
    visibleColumns.value.reduce(
      (count, column) => count + columns[column.status].total,
      0,
    ),
  );

  async function loadColumn(status: TaskStatus, append = false) {
    if (disposed) return;
    const column = columns[status];
    if (append && column.loading) return;
    const ticket = ++tickets[status];
    const offset = append ? column.nextOffset : 0;
    column.loading = true;
    column.error = "";
    try {
      const result = await listTasks(projectId.value, {
        offset,
        limit: PAGE_SIZE,
        status,
        priority: priorityFilter.value || undefined,
      });
      if (disposed || ticket !== tickets[status]) return;
      // 删除或并发移动会改变分页位置，加载更多时按 ID 去重。
      const items = append ? [...column.items, ...result.items] : result.items;
      column.items = [
        ...new Map(items.map((task) => [task.id, task])).values(),
      ];
      column.total = result.total;
      column.nextOffset = result.items.length
        ? result.offset + result.items.length
        : result.total;
    } catch (reason) {
      if (!disposed && ticket === tickets[status])
        column.error = errorMessage(reason);
    } finally {
      if (!disposed && ticket === tickets[status]) column.loading = false;
    }
  }

  async function reload() {
    if (disposed) return;
    for (const { status } of TASK_COLUMNS) {
      tickets[status]++;
      Object.assign(columns[status], {
        items: [],
        total: 0,
        nextOffset: 0,
        loading: false,
        error: "",
      });
    }
    await Promise.all(
      visibleColumns.value.map((column) => loadColumn(column.status)),
    );
  }

  watch([projectId, statusFilter, priorityFilter], reload, {
    immediate: true,
    flush: "sync",
  });
  onScopeDispose(() => {
    disposed = true;
  });
  return {
    statusFilter,
    priorityFilter,
    columns,
    visibleColumns,
    loading,
    hasError,
    total,
    loadColumn,
    reload,
  };
}
