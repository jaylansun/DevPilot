<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Back, Edit, Refresh, Document } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { getProject } from "@/api/project_api";
import { errorMessage } from "@/api/http_client";
import ProjectDialog from "@/components/ProjectDialog.vue";
import TaskBoard from "@/components/TaskBoard.vue";
import type { ProjectVO } from "@/types/api";

const route = useRoute();
const project = ref<ProjectVO | null>(null);
const loading = ref(true);
const error = ref("");
const editing = ref(false);
const showingTasks = computed(() => route.query.tab === "tasks");

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
  <section>
    <RouterLink
      to="/projects"
      class="mb-[30px] inline-flex items-center gap-2 text-[13px] text-[#5c7c89]"
      ><el-icon><Back /></el-icon>返回我的项目</RouterLink
    >
    <el-skeleton
      v-if="loading"
      class="ui-panel"
      :rows="7"
      animated
      aria-label="正在加载项目"
    />
    <div v-else-if="error" class="ui-state" role="alert">
      <h1>暂时无法打开项目</h1>
      <p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProject">重新加载</el-button>
    </div>
    <template v-else-if="project">
      <div class="ui-page-heading">
        <div>
          <p class="ui-eyebrow">{{ showingTasks ? "任务看板" : "项目概览" }}</p>
          <h1 class="wrap-anywhere">{{ project.name }}</h1>
          <p class="ui-muted">记录目标与需求，让项目的下一步更清晰。</p>
        </div>
        <el-button :icon="Edit" @click="editing = true">编辑项目</el-button>
      </div>
      <nav
        class="mb-7 flex gap-[26px] border-b border-[#dfe7ec]"
        aria-label="项目功能"
      >
        <RouterLink
          :to="{ path: route.path }"
          class="border-b-2 px-[3px] pt-3 pb-4 text-sm"
          :class="
            !showingTasks
              ? 'border-brand text-brand font-semibold'
              : 'border-transparent text-[#7c8d98]'
          "
          :aria-current="!showingTasks ? 'page' : undefined"
          >项目概览</RouterLink
        >
        <RouterLink
          :to="{ path: route.path, query: { tab: 'tasks' } }"
          class="border-b-2 px-[3px] pt-3 pb-4 text-sm"
          :class="
            showingTasks
              ? 'border-brand text-brand font-semibold'
              : 'border-transparent text-[#7c8d98]'
          "
          :aria-current="showingTasks ? 'page' : undefined"
          >任务看板</RouterLink
        >
      </nav>
      <TaskBoard v-if="showingTasks" :project-id="project.id" />
      <div
        v-else
        class="grid grid-cols-[minmax(0,1fr)_265px] gap-6 max-tablet:grid-cols-1"
      >
        <article class="ui-panel">
          <div
            class="flex items-center gap-[9px] border-b border-[#edf1f3] pb-[19px] text-[#467969] [&>h2]:m-0 [&>h2]:text-[15px] [&>h2]:text-[#314b59]"
          >
            <el-icon><Document /></el-icon>
            <h2>需求说明</h2>
          </div>
          <p
            class="my-[22px] text-sm leading-[2] whitespace-pre-wrap wrap-anywhere"
            :class="{ 'text-muted': !project.description }"
          >
            {{
              project.description ||
              "还没有填写需求说明。点击“编辑项目”，写下你想完成什么。"
            }}
          </p>
        </article>
        <aside
          class="ui-panel [&>h2]:text-[15px] [&_dt]:mt-6 [&_dt]:text-xs [&_dt]:text-[#8a9aa3] [&_dd]:mt-2.5 [&_dd]:mr-0 [&_dd]:mb-0 [&_dd]:ml-0 [&_dd]:text-xs [&_dd]:text-[#4e6573] [&>.ui-help]:mt-[26px]"
        >
          <h2>项目信息</h2>
          <dl>
            <dt>创建时间</dt>
            <dd>{{ formatDate(project.created_at) }}</dd>
            <dt>最近更新</dt>
            <dd>{{ formatDate(project.updated_at) }}</dd>
          </dl>
          <p class="ui-help">项目与需求说明已保存，可随时回来继续补充。</p>
        </aside>
      </div>
      <ProjectDialog v-model="editing" :project="project" @saved="saved" />
    </template>
  </section>
</template>
