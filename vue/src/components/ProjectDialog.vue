<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { createProject, updateProject } from "@/api/project_api";
import { errorMessage } from "@/api/http_client";
import type { ProjectVO } from "@/types/api";
const props = defineProps<{
  modelValue: boolean;
  project?: ProjectVO | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [project: ProjectVO];
}>();
const form = reactive({ name: "", description: "" });
const saving = ref(false);
const error = ref("");
watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    form.name = props.project?.name ?? "";
    form.description = props.project?.description ?? "";
    error.value = "";
  },
);
async function save() {
  if (saving.value) return;
  error.value = "";
  const payload = {
    name: form.name.trim(),
    description: form.description.trim(),
  };
  if (!payload.name) {
    error.value = "请输入项目名称";
    return;
  }
  saving.value = true;
  try {
    const result = props.project
      ? await updateProject(props.project.id, payload)
      : await createProject(payload);
    emit("update:modelValue", false);
    emit("saved", result);
  } catch (reason) {
    error.value = errorMessage(reason);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="project ? '编辑项目' : '新建项目'"
    width="560px"
    class="ui-dialog"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="mb-7 text-[13px] text-[#80919d]">
      给项目起个名字，写下你想完成的目标。
    </p>
    <form id="project-form" @submit.prevent="save">
      <div class="ui-field">
        <label for="project-name"
          >项目名称 <span class="text-[#b75849]">*</span></label
        ><el-input
          id="project-name"
          v-model="form.name"
          placeholder="例如：餐厅外卖网站"
          maxlength="120"
          show-word-limit
          :disabled="saving"
        />
      </div>
      <div class="ui-field">
        <label for="project-description">需求说明</label
        ><el-input
          id="project-description"
          v-model="form.description"
          type="textarea"
          :rows="6"
          maxlength="5000"
          show-word-limit
          placeholder="例如：顾客能查看菜单、点菜和付款，餐厅能查看并接收订单。"
          :disabled="saving"
        />
        <p class="ui-help">可以先写一个简单的想法，之后随时补充。</p>
      </div>
      <p v-if="error" role="alert" class="ui-error">{{ error }}</p>
    </form>
    <template #footer
      ><el-button :disabled="saving" @click="emit('update:modelValue', false)"
        >取消</el-button
      ><el-button
        type="primary"
        native-type="submit"
        form="project-form"
        :loading="saving"
        >{{ project ? "保存修改" : "创建项目" }}</el-button
      ></template
    >
  </el-dialog>
</template>
