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
  "bg-[#e4f2ee] text-[#318976]",
  "bg-[#eaf0fa] text-[#587eae]",
  "bg-[#f7efe2] text-[#ab8655]",
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
    <div class="ui-page-heading">
      <div>
        <p class="ui-eyebrow">你的想法，从这里出发</p>
        <h1 id="projects-title">
          我的项目<span
            v-if="!loading && !error"
            class="ml-3 inline-flex min-w-[29px] items-center justify-center rounded-lg bg-[#e9eef1] px-[9px] py-[3px] align-middle text-sm tracking-normal text-muted"
            >{{ total }}</span
          >
        </h1>
        <p class="ui-muted">集中管理项目目标，让每一步工作都有方向。</p>
      </div>
      <el-button type="primary" :icon="Plus" size="large" @click="openEditor()"
        >新建项目</el-button
      >
    </div>
    <div
      class="relative mb-7 flex items-center gap-[19px] overflow-hidden rounded-xl border border-[#d8e9e4] bg-[#edf5f3] px-[25px] py-[22px] [&_h2]:mb-[7px] [&_h2]:text-sm [&_h2]:text-[#2b5e51] [&_p]:mb-0 [&_p]:text-xs [&_p]:leading-[1.8] [&_p]:text-[#719186] max-mobile:items-start max-mobile:gap-[13px] max-mobile:p-[18px] max-mobile:[&_p]:text-[11px]"
    >
      <span
        class="grid size-[43px] shrink-0 place-items-center rounded-[10px] bg-[#d9ece5] text-2xl text-[#438b76]"
        ><FolderOpened
      /></span>
      <div>
        <h2>一个项目，承载一个目标</h2>
        <p>例如“餐厅外卖网站”。在项目里写下需求，为接下来的工作打好基础。</p>
      </div>
      <span
        class="ml-auto pr-3 text-[70px] leading-none text-[#bdd9cf] max-mobile:hidden"
        aria-hidden="true"
        >↗</span
      >
    </div>
    <div
      class="mt-2.5 mb-[17px] flex items-center justify-between [&>h2]:m-0 [&>h2]:text-[15px]"
    >
      <h2>全部项目</h2>
      <el-button text :icon="Refresh" :loading="loading" @click="loadProjects"
        >刷新</el-button
      >
    </div>
    <div
      v-if="loading"
      class="grid grid-cols-3 gap-5 max-desktop:grid-cols-2 max-mobile:grid-cols-1 max-mobile:gap-4"
      aria-label="正在加载项目"
      aria-busy="true"
    >
      <div
        v-for="n in 3"
        :key="n"
        class="min-w-0 rounded-xl border border-[#e3e9ed] bg-white p-[22px] transition-[border-color,box-shadow] duration-[180ms] hover:border-[#acccc3] hover:shadow-[0_6px_18px_#183e3510] [&>h3]:mt-[23px] [&>h3]:mb-3 [&>h3]:text-[17px] [&>h3]:leading-[1.6] [&>h3]:wrap-anywhere [&>h3>a]:hover:text-brand"
      >
        <el-skeleton :rows="4" animated />
      </div>
    </div>
    <div v-else-if="error" class="ui-state" role="alert">
      <h2>项目加载失败</h2>
      <p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProjects">重新加载</el-button>
    </div>
    <div v-else-if="projects.length === 0" class="ui-empty">
      <div class="ui-empty-icon"><FolderOpened /></div>
      <h2>从你的第一个项目开始</h2>
      <p>写下项目名称和需求说明，<br />把脑海里的想法变成可以推进的目标。</p>
      <el-button type="primary" :icon="Plus" @click="openEditor()"
        >创建第一个项目</el-button
      >
      <p class="ui-empty-example">例如：个人博客、餐厅外卖网站、团队知识库</p>
    </div>
    <div
      v-else
      class="grid grid-cols-3 gap-5 max-desktop:grid-cols-2 max-mobile:grid-cols-1 max-mobile:gap-4"
    >
      <article
        v-for="(project, index) in projects"
        :key="project.id"
        class="min-w-0 rounded-xl border border-[#e3e9ed] bg-white p-[22px] transition-[border-color,box-shadow] duration-[180ms] hover:border-[#acccc3] hover:shadow-[0_6px_18px_#183e3510] [&>h3]:mt-[23px] [&>h3]:mb-3 [&>h3]:text-[17px] [&>h3]:leading-[1.6] [&>h3]:wrap-anywhere [&>h3>a]:hover:text-brand"
      >
        <div class="flex items-center justify-between">
          <span
            class="grid size-10 place-items-center rounded-[10px] text-[22px]"
            :class="projectIconClasses[index % 3]"
            ><FolderOpened
          /></span>
          <div class="flex [&>.el-button+.el-button]:ml-0.5">
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
        <p
          class="mb-3 h-[46px] line-clamp-2 text-xs leading-[1.9] text-[#7a8a94] wrap-anywhere"
        >
          {{ project.description || "还没有需求说明，可以打开项目补充。" }}
        </p>
        <div
          class="mt-[23px] flex items-center justify-between gap-2.5 border-t border-[#edf1f3] pt-[19px] text-[10px] text-[#8a99a1]"
        >
          <span>更新于 {{ formatDate(project.updated_at) }}</span
          ><RouterLink
            :to="`/projects/${project.id}`"
            class="inline-flex items-center gap-[7px] text-[11px] whitespace-nowrap text-[#278a7c]"
            >打开项目<el-icon><ArrowRight /></el-icon
          ></RouterLink>
        </div>
      </article>
    </div>
    <div
      v-if="total > pageSize && !error"
      class="mt-[27px] flex items-center justify-between text-xs text-[#7e8f9a] max-mobile:flex-wrap max-mobile:gap-2.5"
    >
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
