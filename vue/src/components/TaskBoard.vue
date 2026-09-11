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
  1: "bg-[#fbece9] text-[#b35443]",
  2: "bg-[#fcf1df] text-[#ac803c]",
  3: "bg-[#ebf1fa] text-[#5476a7]",
  4: "bg-[#eef2f4] text-[#788b97]",
  5: "bg-[#eef2f4] text-[#788b97]",
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
      class="mb-6 flex items-center justify-between gap-5 [&_h2]:mb-2 [&_h2]:text-[19px] [&_p]:m-0 [&_p]:text-xs [&_p]:leading-[1.8] [&_p]:text-[#7e8d98] max-mobile:flex-wrap max-mobile:items-start max-mobile:gap-3.5 max-mobile:[&_h2]:text-[17px]"
    >
      <div>
        <h2>把目标，变成下一步行动</h2>
        <p>拆解任务、明确标准，让每一步都有进展。</p>
      </div>
      <el-button
        type="primary"
        :icon="Plus"
        :disabled="Boolean(busyId)"
        @click="create()"
        >新建任务</el-button
      >
    </div>
    <div
      class="mb-[22px] flex flex-wrap items-end justify-between gap-[18px] max-mobile:items-start"
    >
      <div class="flex flex-wrap items-end gap-3">
        <div class="flex flex-col gap-2 text-[11px] text-[#728693]">
          <label for="board-status-filter">状态筛选</label
          ><select
            id="board-status-filter"
            v-model="statusFilter"
            class="ui-select"
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
        <div class="flex flex-col gap-2 text-[11px] text-[#728693]">
          <label for="board-priority-filter">优先级筛选</label
          ><select
            id="board-priority-filter"
            v-model.number="priorityFilter"
            class="ui-select"
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
          text
          :disabled="Boolean(busyId)"
          @click="clearFilters"
          >清除筛选</el-button
        >
      </div>
      <div
        class="flex items-center gap-3.5 text-[11px] text-[#7d8f9a] max-mobile:w-full max-mobile:justify-between"
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
      class="grid items-start gap-[18px]"
      :class="
        visibleColumns.length === 1
          ? 'grid-cols-1 max-w-[700px]'
          : 'grid-cols-3 max-board:grid-cols-1'
      "
    >
      <section
        v-for="column in visibleColumns"
        :key="column.status"
        class="min-w-0 overflow-hidden rounded-xl border border-[#e2e8ec] bg-[#edf1f4]"
        :class="columnColors[column.status]"
        data-testid="task-column"
        :aria-label="`${column.label}任务`"
        :aria-busy="columns[column.status].loading"
      >
        <header
          class="flex items-center justify-between border-t-[3px] [border-top-color:var(--column-color)] px-4 py-[18px] [&_h3]:mt-0 [&_h3]:mb-2 [&_h3]:flex [&_h3]:items-center [&_h3]:gap-2 [&_h3]:text-[13px] [&_p]:m-0 [&_p]:text-[10px] [&_p]:text-[#8797a1]"
        >
          <div>
            <h3>
              <span class="size-[7px] rounded-full bg-(--column-color)" />{{
                column.label
              }}<span
                class="rounded-[5px] bg-[#dfe6eb] px-1.5 py-0.5 text-[10px] text-[#657e8d]"
                >{{ columns[column.status].total }}</span
              >
            </h3>
            <p>{{ column.hint }}</p>
          </div>
          <el-button
            :icon="Plus"
            text
            circle
            :aria-label="`新建${column.label}任务`"
            :disabled="Boolean(busyId)"
            @click="create(column.status)"
          />
        </header>
        <div
          class="flex min-h-[225px] flex-col gap-3 px-2.5 pb-3 max-board:min-h-40"
        >
          <article
            v-for="task in columns[column.status].items"
            :key="task.id"
            class="min-w-0 rounded-[9px] border border-[#e0e7ec] bg-white px-3.5 pt-4 pb-2.5 shadow-[0_2px_3px_#173a4810]"
            :aria-label="task.title"
          >
            <div class="mb-3.5 flex items-center justify-between gap-2">
              <span
                class="rounded px-1.5 py-1 text-[10px]"
                :class="priorityColors[task.priority]"
                >{{
                  PRIORITIES.find(
                    (priority) => priority.value === task.priority,
                  )?.label
                }}</span
              ><span class="text-[10px] text-[#8da0aa]">{{
                task.source === "ai" ? "AI 生成" : "手工创建"
              }}</span>
            </div>
            <button
              type="button"
              class="mt-0 mr-0 mb-2.5 ml-0 block max-w-full cursor-pointer border-0 bg-transparent p-0 text-left text-sm font-semibold leading-[1.7] text-[#2d4654] wrap-anywhere hover:text-brand [&>.el-icon]:mr-1.5 [&>.el-icon]:text-[#42967f]"
              :disabled="Boolean(busyId)"
              @click="edit(task)"
            >
              <el-icon v-if="task.status === 'done'"><CircleCheck /></el-icon
              >{{ task.title }}
            </button>
            <p
              v-if="task.description"
              class="mb-3.5 line-clamp-3 text-[11px] leading-[1.85] whitespace-pre-wrap text-[#81919b] wrap-anywhere"
            >
              {{ task.description }}
            </p>
            <details
              v-if="task.acceptance_criteria"
              class="my-3 text-[11px] text-[#718691] [&>summary]:cursor-pointer [&>p]:mt-[9px] [&>p]:mb-0 [&>p]:rounded-[5px] [&>p]:bg-[#f6f9f9] [&>p]:p-2.5 [&>p]:leading-[1.9] [&>p]:whitespace-pre-wrap [&>p]:wrap-anywhere"
            >
              <summary>查看验收标准</summary>
              <p>{{ task.acceptance_criteria }}</p>
            </details>
            <footer
              class="mt-3.5 flex items-center justify-between gap-1.5 border-t border-[#edf1f3] pt-2 [&_.el-button]:size-7 [&_.el-button]:text-[13px] [&_.el-button]:text-[#859aa5]"
            >
              <select
                :value="task.status"
                :aria-label="`修改任务 ${task.title} 的状态`"
                class="max-w-[110px] rounded-[5px] border-0 bg-[#f2f6f6] p-1.5 text-[11px] text-[#5c7884] focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-2 disabled:cursor-wait disabled:opacity-60"
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
              <div class="flex [&>.el-button+.el-button]:ml-0.5">
                <el-button
                  :icon="Edit"
                  text
                  circle
                  :aria-label="`编辑任务 ${task.title}`"
                  :disabled="Boolean(busyId)"
                  @click="edit(task)"
                /><el-button
                  :icon="Delete"
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
            class="rounded-[9px] bg-white p-4"
            :rows="3"
            animated
          />
          <div
            v-else-if="columns[column.status].error"
            class="px-2.5 py-5 text-xs leading-[1.8] text-[#a05648]"
            role="alert"
          >
            <p>{{ columns[column.status].error }}</p>
            <el-button
              size="small"
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
            class="px-2.5 py-[30px] text-center text-[11px] text-[#8fa0aa]"
          >
            <span
              class="mx-auto mb-[18px] grid size-[34px] place-items-center rounded-[9px] border border-dashed border-[#bdcbd2]"
              >—</span
            >
            <p>
              {{ priorityFilter ? "没有符合筛选条件的任务" : "这里还没有任务" }}
            </p>
            <el-button text size="small" @click="create(column.status)"
              >添加一个任务</el-button
            >
          </div>
          <el-button
            v-else-if="
              columns[column.status].nextOffset < columns[column.status].total
            "
            class="w-full border-dashed bg-transparent text-[11px]"
            :disabled="Boolean(busyId)"
            @click="loadColumn(column.status, true)"
            >加载更多（已显示 {{ columns[column.status].items.length }} /
            {{ columns[column.status].total }}）</el-button
          >
        </div>
      </section>
    </div>
    <p class="mt-5 mb-0 text-[11px] leading-[1.8] text-[#8b9ca6]">
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
