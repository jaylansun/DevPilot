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
      `删除“${project.name}”后，项目及其任务将永久删除。`,
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
    <div class="page-heading">
      <div>
        <p class="eyebrow">你的想法，从这里出发</p>
        <h1 id="projects-title">
          我的项目<span v-if="!loading && !error" class="count-badge">{{
            total
          }}</span>
        </h1>
        <p class="muted">集中管理项目目标，让每一步工作都有方向。</p>
      </div>
      <el-button type="primary" :icon="Plus" size="large" @click="openEditor()"
        >新建项目</el-button
      >
    </div>
    <div class="intro-banner">
      <span class="intro-icon"><FolderOpened /></span>
      <div>
        <h2>一个项目，承载一个目标</h2>
        <p>例如“餐厅外卖网站”。在项目里写下需求，为接下来的工作打好基础。</p>
      </div>
      <span class="banner-decoration" aria-hidden="true">↗</span>
    </div>
    <div class="section-toolbar">
      <h2>全部项目</h2>
      <el-button text :icon="Refresh" :loading="loading" @click="loadProjects"
        >刷新</el-button
      >
    </div>
    <div
      v-if="loading"
      class="project-grid"
      aria-label="正在加载项目"
      aria-busy="true"
    >
      <div v-for="n in 3" :key="n" class="project-card skeleton-card">
        <el-skeleton :rows="4" animated />
      </div>
    </div>
    <div v-else-if="error" class="state-panel" role="alert">
      <h2>项目加载失败</h2>
      <p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProjects">重新加载</el-button>
    </div>
    <div v-else-if="projects.length === 0" class="empty-state">
      <div class="empty-illustration"><FolderOpened /></div>
      <h2>从你的第一个项目开始</h2>
      <p>写下项目名称和需求说明，<br />把脑海里的想法变成可以推进的目标。</p>
      <el-button type="primary" :icon="Plus" @click="openEditor()"
        >创建第一个项目</el-button
      >
      <p class="empty-example">例如：个人博客、餐厅外卖网站、团队知识库</p>
    </div>
    <div v-else class="project-grid">
      <article
        v-for="(project, index) in projects"
        :key="project.id"
        class="project-card"
      >
        <div class="project-card-top">
          <span class="project-icon" :class="`tone-${index % 3}`"
            ><FolderOpened
          /></span>
          <div class="card-actions">
            <el-button
              text
              circle
              :aria-label="`编辑项目：${project.name}`"
              title="编辑项目"
              @click="openEditor(project)"
              ><el-icon><Edit /></el-icon></el-button
            ><el-button
              text
              circle
              :aria-label="`删除项目：${project.name}`"
              title="删除项目"
              :disabled="deletingId !== null"
              @click="removeProject(project)"
              ><el-icon><Delete /></el-icon
            ></el-button>
          </div>
        </div>
        <h3>
          <RouterLink :to="`/projects/${project.id}`">{{
            project.name
          }}</RouterLink>
        </h3>
        <p class="project-description">
          {{ project.description || "还没有需求说明，可以打开项目补充。" }}
        </p>
        <div class="project-card-bottom">
          <span>更新于 {{ formatDate(project.updated_at) }}</span
          ><RouterLink :to="`/projects/${project.id}`" class="enter-project"
            >打开项目<el-icon><ArrowRight /></el-icon
          ></RouterLink>
        </div>
      </article>
    </div>
    <div v-if="total > pageSize && !error" class="pagination">
      <span>共 {{ total }} 个项目</span
      ><el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        :disabled="loading"
        @current-change="loadProjects"
      />
    </div>
    <ProjectDialog
      v-model="dialogVisible"
      :project="editingProject"
      @saved="onSaved"
    />
  </section>
</template>
