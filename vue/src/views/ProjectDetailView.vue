<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Back, Edit, Refresh, Document, ChatDotRound, Aim, Files } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { getProject } from "@/api/project_api";
import { errorMessage } from "@/api/http_client";
import ProjectDialog from "@/components/ProjectDialog.vue";
import TaskBoard from "@/components/TaskBoard.vue";
import DocumentLibrary from "@/components/DocumentLibrary.vue";
import KnowledgeChat from "@/components/KnowledgeChat.vue";
import TaskPlanning from "@/components/TaskPlanning.vue";
import RequirementCheck from "@/components/RequirementCheck.vue";
import ProjectTabs from "@/components/ProjectTabs.vue";
import type { ProjectVO } from "@/types/api";

const route = useRoute();
const project = ref<ProjectVO | null>(null);
const loading = ref(true);
const error = ref("");
const editing = ref(false);
const activeComponent = computed(() => ({ tasks: TaskBoard, documents: DocumentLibrary, chat: KnowledgeChat, planning: TaskPlanning, assistant: RequirementCheck })[String(route.query.tab) as "tasks" | "documents" | "chat" | "planning" | "assistant"]);

async function loadProject() {
  loading.value = true;
  error.value = "";
  try {
    project.value = await getProject(String(route.params.id));
  } catch (reason) {
    error.value = errorMessage(reason);
  } finally {
    loading.value = false;
  }
}

function saved(result: ProjectVO) {
  project.value = result;
  ElMessage.success("项目已更新");
}
function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
onMounted(loadProject);
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col">
    <el-skeleton v-if="loading" class="ui-panel" :rows="7" animated aria-label="正在加载项目" />
    <div v-else-if="error" class="ui-state" role="alert">
      <h1>暂时无法打开项目</h1><p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProject">重新加载</el-button>
    </div>
    <template v-else-if="project">
      <div class="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-3 max-mobile:gap-2">
          <RouterLink to="/projects" aria-label="返回我的项目" title="返回我的项目" class="ui-interactive grid size-11 shrink-0 place-items-center rounded-xl border border-line/70 bg-surface text-muted hover:border-brand/30 hover:text-brand"><el-icon :size="18" aria-hidden="true"><Back /></el-icon></RouterLink>
          <h1 :title="project.name" class="mb-0 min-w-0 line-clamp-2 text-2xl wrap-anywhere max-mobile:text-xl">{{ project.name }}</h1>
        </div>
        <el-button class="shrink-0" text :icon="Edit" @click="editing = true">编辑项目</el-button>
      </div>
      <ProjectTabs />
      <Transition name="content" mode="out-in">
      <component v-if="activeComponent" :is="activeComponent" :key="String(route.query.tab)" :project-id="project.id" />
      <div v-else class="work-scroll grid grid-cols-[minmax(0,1fr)_280px] items-start gap-5 max-tablet:grid-cols-1">
        <article class="ui-panel">
          <div class="flex items-center gap-3 pb-2">
            <el-icon class="text-muted"><Document /></el-icon><h2 class="m-0 text-lg">需求说明</h2>
          </div>
          <p class="mt-5 mb-2 max-w-[70ch] text-base leading-8 whitespace-pre-wrap wrap-anywhere" :class="{ 'text-muted': !project.description }">{{ project.description || "还没有填写需求说明。点击“编辑项目”，写下你想完成什么。" }}</p>
        </article>
        <aside class="space-y-5">
          <div class="p-1">
            <h2 class="mb-4 text-base">继续推进项目</h2>
            <RouterLink :to="{path: route.path, query: {tab: 'assistant'}}" class="ui-interactive mb-2 flex min-h-12 items-center gap-3 rounded-xl bg-white px-4 text-sm hover:text-brand hover:shadow-soft"><el-icon><Aim /></el-icon>检查需求与任务缺口</RouterLink>
            <RouterLink :to="{path: route.path, query: {tab: 'documents'}}" class="ui-interactive mb-2 flex min-h-12 items-center gap-3 rounded-xl bg-white px-4 text-sm hover:text-brand hover:shadow-soft"><el-icon><Files /></el-icon>管理项目资料</RouterLink>
            <RouterLink :to="{path: route.path, query: {tab: 'chat'}}" class="ui-interactive mb-2 flex min-h-12 items-center gap-3 rounded-xl bg-white px-4 text-sm hover:text-brand hover:shadow-soft"><el-icon><ChatDotRound /></el-icon>向项目知识提问</RouterLink>
            <RouterLink :to="{path: route.path, query: {tab: 'planning'}}" class="ui-interactive flex min-h-12 items-center gap-3 rounded-xl bg-white px-4 text-sm hover:text-brand hover:shadow-soft"><el-icon><Aim /></el-icon>生成行动方案</RouterLink>
          </div>
          <div class="border-t border-line/80 px-1 pt-5">
            <h2 class="mb-4 text-sm">项目信息</h2>
            <dl class="m-0 text-xs leading-6"><dt class="text-muted">创建时间</dt><dd class="m-0 mb-3">{{ formatDate(project.created_at) }}</dd><dt class="text-muted">最近更新</dt><dd class="m-0">{{ formatDate(project.updated_at) }}</dd></dl>
            <p class="ui-help">项目与需求说明已保存，可随时回来继续补充。</p>
          </div>
        </aside>
      </div>
      </Transition>
      <ProjectDialog v-model="editing" :project="project" @saved="saved" />
    </template>
  </section>
</template>
