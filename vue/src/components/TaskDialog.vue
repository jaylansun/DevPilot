<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ApiError, errorMessage } from "@/api/http_client";
import * as taskApi from "@/api/task_api";
import type { TaskStatus, TaskVO } from "@/types/api";
import {
  TASK_COLUMNS,
  PRIORITIES,
  newTaskForm,
  taskToForm,
  toCreateQO,
  toUpdateQO,
} from "@/utils/task_form";

const props = defineProps<{
  modelValue: boolean;
  projectId: string;
  taskId: string | null;
  initialStatus: TaskStatus;
  initialPriority: number;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [task: TaskVO];
}>();
const form = reactive(newTaskForm());
const original = ref<TaskVO | null>(null);
const loading = ref(false);
const saving = ref(false);
const loadError = ref("");
const error = ref("");
const conflict = ref(false);
const missing = ref(false);
const blocked = computed(
  () =>
    loading.value ||
    saving.value ||
    Boolean(loadError.value) ||
    conflict.value ||
    missing.value,
);
let requestNumber = 0;

async function loadTask() {
  const current = ++requestNumber;
  if (!props.taskId) return;
  loading.value = true;
  loadError.value = "";
  try {
    const task = await taskApi.getTask(props.projectId, props.taskId);
    if (current !== requestNumber || !props.modelValue) return;
    original.value = task;
    Object.assign(form, taskToForm(task));
    error.value = "";
    conflict.value = false;
    missing.value = false;
  } catch (reason) {
    if (current === requestNumber) loadError.value = errorMessage(reason);
  } finally {
    if (current === requestNumber) loading.value = false;
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    requestNumber++;
    if (!visible) return;
    original.value = null;
    error.value = "";
    loadError.value = "";
    conflict.value = false;
    missing.value = false;
    loading.value = false;
    Object.assign(
      form,
      newTaskForm(props.initialStatus, props.initialPriority),
    );
    if (props.taskId) void loadTask();
  },
);

async function refreshConflict() {
  try {
    await ElMessageBox.confirm(
      "载入最新内容会替换当前未保存的草稿，请先复制需要保留的内容。",
      "重新载入任务",
      {
        confirmButtonText: "载入最新内容",
        cancelButtonText: "继续保留草稿",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  await loadTask();
}

async function save() {
  if (blocked.value) return;
  error.value = "";
  if (!form.title.trim()) {
    error.value = "请输入任务标题";
    return;
  }
  saving.value = true;
  try {
    let result: TaskVO;
    if (props.taskId) {
      if (!original.value) return;
      const qo = toUpdateQO(original.value, form);
      if (!qo) {
        ElMessage.info("任务内容没有变化");
        emit("update:modelValue", false);
        return;
      }
      result = await taskApi.updateTask(props.projectId, props.taskId, qo);
    } else result = await taskApi.createTask(props.projectId, toCreateQO(form));
    emit("update:modelValue", false);
    emit("saved", result);
  } catch (reason) {
    error.value = errorMessage(reason);
    conflict.value =
      reason instanceof ApiError && reason.code === "task_version_conflict";
    missing.value = reason instanceof ApiError && reason.status === 404;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="taskId ? '编辑任务' : '新建任务'"
    width="640px"
    class="ui-dialog [&_.ui-field]:mb-5 [&_.ui-error_p:last-child]:mb-0 max-mobile:mt-[5vh]"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-skeleton
      v-if="loading && !original"
      :rows="5"
      animated
      aria-label="正在读取任务"
    />
    <div v-else-if="loadError && !original" role="alert">
      <p>{{ loadError }}</p>
      <el-button @click="loadTask">重新读取任务</el-button>
    </div>
    <form v-else id="task-form" @submit.prevent="save">
      <p class="mb-5 text-[13px] text-[#80919d]">
        写清楚要做什么，以及怎样才算完成。
      </p>
      <p v-if="loadError" role="alert" class="ui-error">
        {{ loadError }}。草稿仍然保留，请稍后重试载入。
      </p>
      <div class="ui-field">
        <label for="task-title"
          >任务标题 <span class="text-[#b75849]">*</span></label
        ><el-input
          id="task-title"
          v-model="form.title"
          placeholder="例如：完成购物车页面"
          maxlength="200"
          show-word-limit
          :disabled="loading || saving"
        />
      </div>
      <div
        class="grid grid-cols-2 gap-[18px] [&_.ui-select]:w-full max-mobile:grid-cols-1 max-mobile:gap-0"
      >
        <div class="ui-field">
          <label for="task-priority">优先级</label
          ><select
            id="task-priority"
            v-model.number="form.priority"
            class="ui-select"
            :disabled="loading || saving"
          >
            <option
              v-for="priority in PRIORITIES"
              :key="priority.value"
              :value="priority.value"
            >
              {{ priority.label }}
            </option>
          </select>
        </div>
        <div class="ui-field">
          <label for="task-status">任务状态</label
          ><select
            id="task-status"
            v-model="form.status"
            class="ui-select"
            :disabled="loading || saving"
          >
            <option
              v-for="column in TASK_COLUMNS"
              :key="column.status"
              :value="column.status"
            >
              {{ column.label }}
            </option>
          </select>
        </div>
      </div>
      <div class="ui-field">
        <label for="task-description">任务说明</label
        ><el-input
          id="task-description"
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="10000"
          show-word-limit
          placeholder="描述具体要做的工作"
          :disabled="loading || saving"
        />
      </div>
      <div class="ui-field">
        <label for="task-acceptance">验收标准</label
        ><el-input
          id="task-acceptance"
          v-model="form.acceptance_criteria"
          type="textarea"
          :rows="3"
          maxlength="10000"
          show-word-limit
          placeholder="例如：能添加商品、修改数量，并正确显示合计金额。"
          :disabled="loading || saving"
        />
      </div>
      <div v-if="error" role="alert" class="ui-error">
        <p>{{ error }}</p>
        <template v-if="conflict"
          ><p>你的草稿已保留。请先查看最新内容，再决定如何修改。</p>
          <el-button :loading="loading" @click="refreshConflict"
            >载入最新任务</el-button
          ></template
        >
        <p v-if="missing">请关闭窗口并刷新看板，你可以先复制需要保留的内容。</p>
      </div>
    </form>
    <template #footer
      ><el-button :disabled="saving" @click="emit('update:modelValue', false)"
        >取消</el-button
      ><el-button
        type="primary"
        native-type="submit"
        form="task-form"
        :loading="saving"
        :disabled="blocked"
        >{{ taskId ? "保存任务" : "创建任务" }}</el-button
      ></template
    >
  </el-dialog>
</template>
