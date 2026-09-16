<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  Plus,
  FolderOpened,
  ArrowRight,
  Refresh,
  Edit,
  Delete,
  Grid,
  List,
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
const viewMode = ref<"grid" | "list">("grid");
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
        icon: Delete,
        customClass: "ui-confirm-danger",
        confirmButtonType: "danger",
        autofocus: false,
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
    <div class="ui-page-heading pb-6 pt-2">
      <div>
        <h1 id="projects-title">我的项目</h1>
        <p class="ui-muted">留住每个好想法，一步步把它变成现实。</p>
      </div>
      <el-button type="primary" :icon="Plus" size="large" @click="openEditor()">新建项目</el-button>
    </div>
    <div class="mb-5 flex items-center justify-between">
      <h2 class="m-0 text-sm font-medium text-ink">全部项目<span v-if="!loading && !error" class="ml-2 text-muted">{{ total }}</span></h2>
      <div class="flex items-center gap-3">
        <el-button text :icon="Refresh" :loading="loading" @click="loadProjects">刷新</el-button>
        <div class="flex rounded-xl bg-raised/80 p-1" aria-label="项目展示方式">
          <button type="button" aria-label="网格视图" title="网格视图" :aria-pressed="viewMode === 'grid'" class="ui-interactive grid size-9 place-items-center rounded-lg" :class="viewMode === 'grid' ? 'bg-white text-ink shadow-soft' : 'text-muted'" @click="viewMode = 'grid'"><Grid /></button>
          <button type="button" aria-label="列表视图" title="列表视图" :aria-pressed="viewMode === 'list'" class="ui-interactive grid size-9 place-items-center rounded-lg" :class="viewMode === 'list' ? 'bg-white text-ink shadow-soft' : 'text-muted'" @click="viewMode = 'list'"><List /></button>
        </div>
      </div>
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
    <div v-else :key="viewMode" class="ui-enter grid gap-5" :class="viewMode === 'grid' ? 'grid-cols-3 max-desktop:grid-cols-2 max-mobile:grid-cols-1' : 'grid-cols-1'">
      <article v-for="(project, index) in projects" :key="project.id" class="ui-interactive group flex min-w-0 flex-col rounded-[22px] border border-line/70 bg-surface p-6 shadow-soft hover:-translate-y-0.5 hover:border-brand/25 hover:shadow-float" :class="{ 'desktop:grid desktop:grid-cols-[44px_minmax(0,1fr)_140px_88px] desktop:items-center desktop:gap-x-6': viewMode === 'list' }">
        <div class="flex items-center justify-between" :class="{ 'desktop:contents': viewMode === 'list' }">
          <span class="grid size-11 place-items-center rounded-xl text-2xl" :class="projectIconClasses[index % 3]"><FolderOpened aria-hidden="true" /></span>
          <div class="flex [&>.el-button+.el-button]:ml-0" :class="{ 'desktop:col-start-4 desktop:row-start-1': viewMode === 'list' }">
            <el-button text circle :aria-label="`编辑项目：${project.name}`" title="编辑项目" @click="openEditor(project)"><el-icon><Edit /></el-icon></el-button>
            <el-button text circle :aria-label="`删除项目：${project.name}`" title="删除项目" :disabled="deletingId !== null" @click="removeProject(project)"><el-icon><Delete /></el-icon></el-button>
          </div>
        </div>
        <div :class="{ 'desktop:col-start-2 desktop:row-start-1': viewMode === 'list' }">
          <h3 class="mt-6 mb-2 text-xl font-semibold leading-7 wrap-anywhere" :class="{ 'desktop:mt-0': viewMode === 'list' }"><RouterLink :to="`/projects/${project.id}`" class="ui-interactive hover:text-brand">{{ project.name }}</RouterLink></h3>
          <p class="mb-6 min-h-12 line-clamp-2 text-sm leading-7 text-muted wrap-anywhere" :class="{ 'desktop:mb-0 desktop:min-h-0': viewMode === 'list' }">{{ project.description || "还没有需求说明，可以打开项目补充。" }}</p>
        </div>
        <div class="mt-auto flex flex-wrap items-center justify-between gap-2 pt-3 text-xs text-muted" :class="{ 'desktop:col-start-3 desktop:row-start-1 desktop:mt-0 desktop:flex-col desktop:items-end desktop:pt-0': viewMode === 'list' }">
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
