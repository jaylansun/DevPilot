<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Back, Edit, Refresh, Document } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { getProject } from "@/api/project_api";
import { errorMessage } from "@/api/http_client";
import ProjectDialog from "@/components/ProjectDialog.vue";
import type { ProjectVO } from "@/types/api";

const route = useRoute();
const project = ref<ProjectVO | null>(null);
const loading = ref(true);
const error = ref("");
const editing = ref(false);

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
    <RouterLink to="/projects" class="back-link"
      ><el-icon><Back /></el-icon>返回我的项目</RouterLink
    >
    <el-skeleton
      v-if="loading"
      class="detail-panel"
      :rows="7"
      animated
      aria-label="正在加载项目"
    />
    <div v-else-if="error" class="state-panel" role="alert">
      <h1>暂时无法打开项目</h1>
      <p>{{ error }}</p>
      <el-button :icon="Refresh" @click="loadProject">重新加载</el-button>
    </div>
    <template v-else-if="project">
      <div class="page-heading">
        <div>
          <p class="eyebrow">项目概览</p>
          <h1 class="detail-title">{{ project.name }}</h1>
          <p class="muted">记录目标与需求，让项目的下一步更清晰。</p>
        </div>
        <el-button :icon="Edit" @click="editing = true">编辑项目</el-button>
      </div>
      <div class="detail-grid">
        <article class="detail-panel">
          <div class="panel-heading">
            <el-icon><Document /></el-icon>
            <h2>需求说明</h2>
          </div>
          <p class="requirement-text" :class="{ muted: !project.description }">
            {{
              project.description ||
              "还没有填写需求说明。点击“编辑项目”，写下你想完成什么。"
            }}
          </p>
        </article>
        <aside class="detail-panel project-meta">
          <h2>项目信息</h2>
          <dl>
            <dt>创建时间</dt>
            <dd>{{ formatDate(project.created_at) }}</dd>
            <dt>最近更新</dt>
            <dd>{{ formatDate(project.updated_at) }}</dd>
          </dl>
          <p class="field-help">项目与需求说明已保存，可随时回来继续补充。</p>
        </aside>
      </div>
      <ProjectDialog v-model="editing" :project="project" @saved="saved" />
    </template>
  </section>
</template>
