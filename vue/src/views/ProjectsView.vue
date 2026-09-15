<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  Plus,
  FolderOpened,
  ArrowRight,
  Refresh,
  Edit,
  Delete,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import * as projectApi from "@/api/project_api";
import { errorMessage } from "@/api/http_client";
import ProjectDialog from "@/components/ProjectDialog.vue";
import type { ProjectVO } from "@/types/api";

// 使用完整类名，确保 Tailwind 构建时能提取所有颜色。
const projectIconClasses = [
  "bg-brand/10 text-brand",
  "bg-success/10 text-success",
  "bg-warning/10 text-warning",
];

const projects = ref<ProjectVO[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 9;
const loading = ref(true);
const error = ref("");
const dialogVisible = ref(false);
const editingProject = ref<ProjectVO | null>(null);
const deletingId = ref<string | null>(null);
let requestNumber = 0;

async function loadProjects() {
  const current = ++requestNumber;
  loading.value = true;
  error.value = "";
  try {
    const result = await projectApi.listProjects(
      (page.value - 1) * pageSize,
      pageSize,
    );
    if (current !== requestNumber) return;
    projects.value = result.items;
    total.value = result.total;
    if (!result.items.length && page.value > 1) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize));
      await loadProjects();
    }
  } catch (reason) {
    if (current === requestNumber) error.value = errorMessage(reason);
  } finally {
    if (current === requestNumber) loading.value = false;
  }
}

function openEditor(project: ProjectVO | null = null) {
  editingProject.value = project;
  dialogVisible.value = true;
}

function onSaved() {
  ElMessage.success(editingProject.value ? "项目已更新" : "项目已创建");
  if (!editingProject.value) page.value = 1;
  void loadProjects();
}

async function removeProject(project: ProjectVO) {
  if (deletingId.value) return;
  try {
    await ElMessageBox.confirm(
      `删除“${project.name}”后，项目、任务和上传的文档将永久删除，对应向量会在后台清理。`,
      "删除项目",
      {
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  deletingId.value = project.id;
  try {
    await projectApi.deleteProject(project.id);
    ElMessage.success("项目已删除");
    await loadProjects();
  } catch (reason) {
    ElMessage.error(errorMessage(reason));
  } finally {
    deletingId.value = null;
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

onMounted(loadProjects);
</script>

<template>
  <section aria-labelledby="projects-title">
    <div class="ui-page-heading border-b border-line/70 pb-7">
      <div>
        <h1 id="projects-title">我的项目<span v-if="!loading && !error" class="ml-3 rounded-lg bg-raised px-2.5 py-1 align-middle text-sm font-normal tracking-normal text-muted">{{ total }}</span></h1>
        <p class="ui-muted">选择一个项目，连接需求、知识与下一步行动。</p>
      </div>
      <el-button type="primary" :icon="Plus" size="large" @click="openEditor()">新建项目</el-button>
    </div>
    <div class="mb-5 flex items-center justify-between">
      <h2 class="m-0 text-sm font-medium text-muted">全部项目</h2>
      <el-button text :icon="Refresh" :loading="loading" @click="loadProjects">刷新</el-button>
    </div>
    <div v-if="loading" class="grid grid-cols-3 gap-5 max-desktop:grid-cols-2 max-mobile:grid-cols-1" aria-label="正在加载项目" aria-busy="true">
      <div v-for="n in 3" :key="n" class="ui-panel"><el-skeleton :rows="4" animated /></div>
    </div>
    <div v-else-if="error" class="ui-state" role="alert">
      <h2>项目加载失败</h2><p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProjects">重新加载</el-button>
    </div>
    <div v-else-if="projects.length === 0" class="ui-empty">
      <div class="ui-empty-icon"><FolderOpened /></div>
      <h2>从你的第一个项目开始</h2>
      <p>写下项目名称和需求说明，<br />把脑海里的想法变成可以推进的目标。</p>
      <el-button type="primary" :icon="Plus" @click="openEditor()">创建第一个项目</el-button>
      <p class="ui-empty-example">例如：个人博客、餐厅外卖网站、团队知识库</p>
    </div>
    <div v-else class="grid grid-cols-3 gap-5 max-desktop:grid-cols-2 max-mobile:grid-cols-1">
      <article v-for="(project, index) in projects" :key="project.id" class="group flex min-w-0 flex-col rounded-2xl border border-line/70 bg-surface p-6 transition-colors duration-200 hover:border-brand/50">
        <div class="flex items-center justify-between">
          <span class="grid size-11 place-items-center rounded-xl text-2xl" :class="projectIconClasses[index % 3]"><FolderOpened aria-hidden="true" /></span>
          <div class="flex [&>.el-button+.el-button]:ml-0">
            <el-button text circle :aria-label="`编辑项目：${project.name}`" title="编辑项目" @click="openEditor(project)"><el-icon><Edit /></el-icon></el-button>
            <el-button text circle :aria-label="`删除项目：${project.name}`" title="删除项目" :disabled="deletingId !== null" @click="removeProject(project)"><el-icon><Delete /></el-icon></el-button>
          </div>
        </div>
        <h3 class="mt-7 mb-3 text-xl font-semibold leading-7 wrap-anywhere"><RouterLink :to="`/projects/${project.id}`" class="transition-colors hover:text-brand">{{ project.name }}</RouterLink></h3>
        <p class="mb-7 min-h-12 line-clamp-2 text-sm leading-6 text-muted wrap-anywhere">{{ project.description || "还没有需求说明，可以打开项目补充。" }}</p>
        <div class="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line/70 pt-4 text-xs text-muted">
          <span>更新于 {{ formatDate(project.updated_at) }}</span>
          <RouterLink :to="`/projects/${project.id}`" class="inline-flex min-h-10 items-center gap-2 font-medium text-brand">打开项目<el-icon><ArrowRight /></el-icon></RouterLink>
        </div>
      </article>
    </div>
    <div v-if="total > pageSize && !error" class="mt-7 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
      <span>共 {{ total }} 个项目</span>
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" :disabled="loading" @current-change="loadProjects" />
    </div>
    <ProjectDialog v-model="dialogVisible" :project="editingProject" @saved="onSaved" />
  </section>
</template>
