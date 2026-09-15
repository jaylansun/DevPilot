<script setup lang="ts">
import { ref, toRef } from "vue";
import {
  Plus,
  Refresh,
  Edit,
  Delete,
  CircleCheck,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ApiError, errorMessage } from "@/api/http_client";
import { deleteTask, updateTask } from "@/api/task_api";
import { useTaskBoard } from "@/composables/use_task_board";
import { PRIORITIES, TASK_COLUMNS } from "@/utils/task_form";
import type { TaskStatus, TaskVO } from "@/types/api";
import TaskDialog from "./TaskDialog.vue";

// 动态状态使用静态类名映射，不拼接 Tailwind 工具类。
const columnColors: Record<TaskStatus, string> = {
  todo: "[--column-color:#94a7b6]",
  in_progress: "[--column-color:#d7a051]",
  done: "[--column-color:#4da58d]",
};
const priorityColors: Record<number, string> = {
  1: "bg-danger/10 text-danger",
  2: "bg-warning/10 text-warning",
  3: "bg-brand/10 text-brand",
  4: "bg-raised text-muted",
  5: "bg-raised text-muted",
};

const props = defineProps<{ projectId: string }>();
const {
  statusFilter,
  priorityFilter,
  columns,
  visibleColumns,
  loading,
  hasError,
  total,
  loadColumn,
  reload,
} = useTaskBoard(toRef(props, "projectId"));
const dialogOpen = ref(false);
const editingId = ref<string | null>(null);
const initialStatus = ref<TaskStatus>("todo");
const initialPriority = ref(3);
const busyId = ref<string | null>(null);
const notice = ref("");

function create(status?: TaskStatus) {
  editingId.value = null;
  initialStatus.value = status || statusFilter.value || "todo";
  initialPriority.value = priorityFilter.value || 3;
  dialogOpen.value = true;
}
function edit(task: TaskVO) {
  editingId.value = task.id;
  dialogOpen.value = true;
}
async function saved(task: TaskVO) {
  const hidden =
    (statusFilter.value && statusFilter.value !== task.status) ||
    (priorityFilter.value && priorityFilter.value !== task.priority);
  notice.value = hidden
    ? "任务已保存，但不符合当前筛选条件。清除筛选后即可查看。"
    : "";
  ElMessage.success(editingId.value ? "任务已更新" : "任务已创建");
  await reload();
}
async function move(task: TaskVO, event: Event) {
  const select = event.target as HTMLSelectElement;
  const status = select.value as TaskStatus;
  // 服务器确认后再移动卡片，失败时保持原来的状态。
  select.value = task.status;
  if (busyId.value || status === task.status) return;
  busyId.value = task.id;
  notice.value = "";
  try {
    await updateTask(props.projectId, task.id, {
      status,
      version: task.version,
    });
    ElMessage.success("任务状态已更新");
    await reload();
  } catch (reason) {
    notice.value = errorMessage(reason);
    if (
      reason instanceof ApiError &&
      (reason.code === "task_version_conflict" || reason.status === 404)
    ) {
      notice.value += "。已重新读取看板，请确认最新内容后再操作。";
      await reload();
    }
  } finally {
    busyId.value = null;
  }
}
async function remove(task: TaskVO) {
  try {
    await ElMessageBox.confirm(
      `确定删除任务“${task.title}”吗？此操作不能撤销。`,
      "删除任务",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  if (busyId.value) return;
  busyId.value = task.id;
  notice.value = "";
  try {
    await deleteTask(props.projectId, task.id);
    ElMessage.success("任务已删除");
    await reload();
  } catch (reason) {
    notice.value = errorMessage(reason);
    if (reason instanceof ApiError && reason.status === 404) await reload();
  } finally {
    busyId.value = null;
  }
}
function clearFilters() {
  statusFilter.value = "";
  priorityFilter.value = "";
  notice.value = "";
}
</script>

<template>
  <section aria-label="任务看板">
    <div
      class="mb-6 flex items-center justify-between gap-5 [&_h2]:mb-2 [&_h2]:text-xl [&_p]:m-0 [&_p]:text-sm [&_p]:leading-7 [&_p]:text-muted max-mobile:flex-wrap max-mobile:items-start max-mobile:gap-4"
    >
      <div>
        <h2>把目标，变成下一步行动</h2>
        <p>拆解任务、明确标准，让每一步都有进展。</p>
      </div>
      <el-button
        type="primary"
        :icon="Plus"
        class="ui-interactive min-h-11!"
        :disabled="Boolean(busyId)"
        @click="create()"
        >新建任务</el-button
      >
    </div>
    <div
      class="mb-[22px] flex flex-wrap items-end justify-between gap-[18px] max-mobile:items-start"
    >
      <div class="flex flex-wrap items-end gap-3">
        <div class="flex flex-col gap-2 text-xs text-muted">
          <label for="board-status-filter">状态筛选</label
          ><select
            id="board-status-filter"
            v-model="statusFilter"
            class="ui-select ui-interactive"
            :disabled="Boolean(busyId)"
          >
            <option value="">全部状态</option>
            <option
              v-for="column in TASK_COLUMNS"
              :key="column.status"
              :value="column.status"
            >
              {{ column.label }}
            </option>
          </select>
        </div>
        <div class="flex flex-col gap-2 text-xs text-muted">
          <label for="board-priority-filter">优先级筛选</label
          ><select
            id="board-priority-filter"
            v-model.number="priorityFilter"
            class="ui-select ui-interactive"
            :disabled="Boolean(busyId)"
          >
            <option value="">全部优先级</option>
            <option
              v-for="priority in PRIORITIES"
              :key="priority.value"
              :value="priority.value"
            >
              {{ priority.label }}
            </option>
          </select>
        </div>
        <el-button
          v-if="statusFilter || priorityFilter"
          class="ui-interactive min-h-11!"
          text
          :disabled="Boolean(busyId)"
          @click="clearFilters"
          >清除筛选</el-button
        >
      </div>
      <div
        class="flex items-center gap-3.5 text-xs text-muted max-mobile:w-full max-mobile:justify-between"
      >
        <span role="status">{{
          loading
            ? "正在加载…"
            : hasError
              ? "部分任务未能加载"
              : `当前筛选共 ${total} 项任务`
        }}</span
        ><el-button
          :icon="Refresh"
          class="ui-interactive min-h-11! min-w-11!"
          circle
          aria-label="刷新任务看板"
          :loading="loading"
          :disabled="Boolean(busyId)"
          @click="reload"
        />
      </div>
    </div>
    <el-alert
      v-if="notice"
      :title="notice"
      type="warning"
      show-icon
      :closable="false"
      class="mb-[18px]"
    />
    <div
      class="ui-enter grid items-start gap-4"
      :class="
        visibleColumns.length === 1
          ? 'grid-cols-1 max-w-[700px]'
          : 'grid-cols-3 max-board:grid-cols-1'
      "
    >
      <section
        v-for="column in visibleColumns"
        :key="column.status"
        class="min-w-0 overflow-hidden rounded-2xl bg-raised/65"
        :class="columnColors[column.status]"
        data-testid="task-column"
        :aria-label="`${column.label}任务`"
        :aria-busy="columns[column.status].loading"
      >
        <header
          class="flex items-center justify-between px-4 py-5 [&_h3]:mt-0 [&_h3]:mb-2 [&_h3]:flex [&_h3]:items-center [&_h3]:gap-2 [&_h3]:text-sm [&_p]:m-0 [&_p]:text-xs [&_p]:text-muted"
        >
          <div>
            <h3>
              <span class="size-2 rounded-full bg-(--column-color)" aria-hidden="true" />{{
                column.label
              }}<span
                class="rounded-full bg-surface/80 px-2 py-0.5 text-xs text-muted"
                >{{ columns[column.status].total }}</span
              >
            </h3>
            <p>{{ column.hint }}</p>
          </div>
          <el-button
            :icon="Plus"
            class="ui-interactive min-h-11! min-w-11!"
            text
            circle
            :aria-label="`新建${column.label}任务`"
            :disabled="Boolean(busyId)"
            @click="create(column.status)"
          />
        </header>
        <div
          class="flex min-h-[225px] flex-col gap-3 px-3 pb-3 max-board:min-h-40"
        >
          <article
            v-for="task in columns[column.status].items"
            :key="task.id"
            class="ui-interactive min-w-0 rounded-xl bg-surface px-4 pt-4 pb-2.5 shadow-sm shadow-ink/5 focus-within:shadow-md focus-within:shadow-brand/8"
            :aria-label="task.title"
          >
            <div class="mb-3.5 flex items-center justify-between gap-2">
              <span
                class="rounded-full px-2 py-1 text-xs font-medium"
                :class="priorityColors[task.priority]"
                >{{
                  PRIORITIES.find(
                    (priority) => priority.value === task.priority,
                  )?.label
                }}</span
              ><span class="text-xs text-muted">{{
                task.source === "ai" ? "AI 生成" : "手工创建"
              }}</span>
            </div>
            <button
              type="button"
              class="ui-interactive mt-0 mr-0 mb-2.5 ml-0 block min-h-11 max-w-full cursor-pointer border-0 bg-transparent p-0 text-left text-base font-semibold leading-7 text-ink wrap-anywhere hover:text-brand [&>.el-icon]:mr-1.5 [&>.el-icon]:text-success"
              :disabled="Boolean(busyId)"
              @click="edit(task)"
            >
              <el-icon v-if="task.status === 'done'" aria-hidden="true"><CircleCheck /></el-icon
              >{{ task.title }}
            </button>
            <p
              v-if="task.description"
              class="mb-3 line-clamp-3 text-sm leading-7 whitespace-pre-wrap text-muted wrap-anywhere"
            >
              {{ task.description }}
            </p>
            <details
              v-if="task.acceptance_criteria"
              class="my-2 text-sm text-muted [&>p]:mt-2 [&>p]:mb-3 [&>p]:rounded-lg [&>p]:bg-canvas [&>p]:p-3 [&>p]:leading-7 [&>p]:whitespace-pre-wrap [&>p]:wrap-anywhere"
            >
              <summary class="ui-interactive min-h-11 cursor-pointer py-3 hover:text-brand">查看验收标准</summary>
              <p class="ui-enter">{{ task.acceptance_criteria }}</p>
            </details>
            <footer
              class="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line/65 pt-2 [&_.el-button]:min-h-11 [&_.el-button]:min-w-11 [&_.el-button]:text-sm [&_.el-button]:text-muted"
            >
              <select
                :value="task.status"
                :aria-label="`修改任务 ${task.title} 的状态`"
                class="ui-interactive min-h-11 max-w-[110px] cursor-pointer rounded-lg border-0 bg-canvas p-2 text-xs text-muted hover:bg-raised focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-2 disabled:cursor-wait disabled:opacity-60"
                :disabled="Boolean(busyId)"
                @change="move(task, $event)"
              >
                <option
                  v-for="target in TASK_COLUMNS"
                  :key="target.status"
                  :value="target.status"
                >
                  {{ target.label }}
                </option>
              </select>
              <div class="flex gap-2 [&>.el-button+.el-button]:ml-0">
                <el-button
                  :icon="Edit"
                  class="ui-interactive"
                  text
                  circle
                  :aria-label="`编辑任务 ${task.title}`"
                  :disabled="Boolean(busyId)"
                  @click="edit(task)"
                /><el-button
                  :icon="Delete"
                  class="ui-interactive"
                  text
                  circle
                  :aria-label="`删除任务 ${task.title}`"
                  :disabled="Boolean(busyId)"
                  @click="remove(task)"
                />
              </div>
            </footer>
          </article>
          <el-skeleton
            v-if="columns[column.status].loading"
            class="rounded-xl bg-surface p-4"
            :rows="3"
            animated
          />
          <div
            v-else-if="columns[column.status].error"
            class="px-2.5 py-5 text-xs leading-[1.8] text-danger"
            role="alert"
          >
            <p>{{ columns[column.status].error }}</p>
            <el-button
              size="small"
              class="ui-interactive min-h-11!"
              @click="
                loadColumn(
                  column.status,
                  columns[column.status].items.length > 0,
                )
              "
              >重试加载</el-button
            >
          </div>
          <div
            v-else-if="!columns[column.status].items.length"
            class="px-2.5 py-[30px] text-center text-xs text-muted"
          >
            <span
              class="mx-auto mb-4 grid size-10 place-items-center rounded-xl bg-surface/70 text-lg"
              >—</span
            >
            <p>
              {{ priorityFilter ? "没有符合筛选条件的任务" : "这里还没有任务" }}
            </p>
            <el-button text size="small" class="ui-interactive min-h-11!" @click="create(column.status)"
              >添加一个任务</el-button
            >
          </div>
          <el-button
            v-else-if="
              columns[column.status].nextOffset < columns[column.status].total
            "
            class="ui-interactive min-h-11! w-full border-0! bg-transparent text-xs"
            :disabled="Boolean(busyId)"
            @click="loadColumn(column.status, true)"
            >加载更多（已显示 {{ columns[column.status].items.length }} /
            {{ columns[column.status].total }}）</el-button
          >
        </div>
      </section>
    </div>
    <p class="mt-5 mb-0 text-xs leading-[1.8] text-muted">
      任务修改会保存到当前项目。点击任务标题可查看完整内容或编辑。
    </p>
    <TaskDialog
      v-model="dialogOpen"
      :project-id="projectId"
      :task-id="editingId"
      :initial-status="initialStatus"
      :initial-priority="initialPriority"
      @saved="saved"
    />
  </section>
</template>
