<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Document, Refresh, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteDocument,
  listDocuments,
  retryDocument,
  uploadDocument,
} from "@/api/document_api";
import { errorMessage } from "@/api/http_client";
import type { DocumentStatus, DocumentVO } from "@/types/api";

const props = defineProps<{ projectId: string }>();
const documents = ref<DocumentVO[]>([]);
const loading = ref(true);
const error = ref("");
const uploading = ref(false);
const workingId = ref("");
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement>();
let active = true;
let generation = 0;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

const statuses: Record<DocumentStatus, { label: string; color: string }> = {
  queued: { label: "等待索引", color: "bg-slate-100 text-slate-600" },
  indexing: { label: "正在索引", color: "bg-amber-50 text-amber-700" },
  ready: { label: "已就绪", color: "bg-emerald-50 text-emerald-700" },
  failed: { label: "索引失败", color: "bg-red-50 text-red-700" },
  deleting: { label: "正在删除", color: "bg-slate-100 text-slate-600" },
  delete_failed: { label: "删除失败", color: "bg-red-50 text-red-700" },
};
const readyCount = computed(
  () => documents.value.filter((doc) => doc.status === "ready").length,
);
const pending = computed(() =>
  documents.value.some((doc) =>
    ["queued", "indexing", "deleting"].includes(doc.status),
  ),
);

function schedulePoll() {
  clearTimeout(pollTimer);
  if (active && pending.value && !error.value)
    pollTimer = setTimeout(() => void load(false), 3000);
}

async function load(showLoading = true) {
  const current = ++generation;
  if (showLoading) loading.value = true;
  error.value = "";
  try {
    const result = await listDocuments(props.projectId);
    if (active && current === generation) documents.value = result.items;
  } catch (reason) {
    if (active && current === generation) error.value = errorMessage(reason);
  } finally {
    if (active && current === generation) {
      loading.value = false;
      schedulePoll();
    }
  }
}

function chooseFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  error.value = "";
}

async function upload() {
  const file = selectedFile.value;
  if (!file) {
    error.value = "请先选择一个文档";
    return;
  }
  if (!/\.(md|txt)$/i.test(file.name)) {
    error.value = "仅支持 .md 和 .txt 文件";
    return;
  }
  if (file.size === 0 || file.size > 2 * 1024 * 1024) {
    error.value = "请选择非空且不超过 2 MB 的文件";
    return;
  }
  uploading.value = true;
  clearTimeout(pollTimer);
  generation++;
  loading.value = false;
  error.value = "";
  try {
    await uploadDocument(props.projectId, file);
    if (!active) return;
    selectedFile.value = null;
    if (fileInput.value) fileInput.value.value = "";
    ElMessage.success("文档已上传，正在后台准备索引");
    await load(false);
  } catch (reason) {
    if (active) error.value = errorMessage(reason);
  } finally {
    uploading.value = false;
  }
}

async function operate(doc: DocumentVO, remove: boolean) {
  if (remove) {
    try {
      await ElMessageBox.confirm(
        `确定删除“${doc.filename}”吗？文档和对应向量将一起移除。`,
        "删除文档",
        {
          confirmButtonText: "确认删除",
          cancelButtonText: "取消",
          type: "warning",
        },
      );
    } catch {
      return;
    }
  }
  if (!active) return;
  workingId.value = doc.id;
  clearTimeout(pollTimer);
  generation++;
  loading.value = false;
  error.value = "";
  try {
    if (remove) await deleteDocument(props.projectId, doc.id);
    else await retryDocument(props.projectId, doc.id);
    if (!active) return;
    ElMessage.success(
      remove ? "已提交删除，清理完成后文档会从列表消失" : "已重新加入处理队列",
    );
    await load(false);
  } catch (reason) {
    if (active) error.value = errorMessage(reason);
  } finally {
    workingId.value = "";
  }
}

onMounted(() => void load());
onBeforeUnmount(() => {
  active = false;
  generation++;
  clearTimeout(pollTimer);
});
</script>

<template>
  <section aria-label="项目知识库" class="space-y-6">
    <div class="ui-panel">
      <div class="flex items-start gap-4 max-mobile:flex-col">
        <span
          class="grid size-12 shrink-0 place-items-center rounded-xl bg-emerald-50 text-2xl text-brand"
        >
          <el-icon><UploadFilled /></el-icon>
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="m-0 text-lg">把项目资料放在这里</h2>
          <p class="ui-muted text-sm leading-7">
            上传需求说明、产品规则或验收标准，为后续 AI 问答准备可检索的资料。
          </p>
          <p class="ui-help">
            支持 UTF-8 编码的 .md / .txt，每个文件最多 2 MB，每个项目最多 20
            个。
          </p>
        </div>
        <span class="rounded-lg bg-canvas px-3 py-2 text-sm text-muted"
          >{{ documents.length }} / 20 个文档</span
        >
      </div>
      <form
        class="mt-5 flex items-center gap-3 max-mobile:flex-col max-mobile:items-stretch"
        @submit.prevent="upload"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".md,.txt"
          aria-label="选择知识库文档"
          class="min-w-0 flex-1 rounded-lg border border-slate-200 p-3 text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-canvas file:px-3 file:py-2 file:text-brand"
          :disabled="uploading"
          @change="chooseFile"
        />
        <el-button
          native-type="submit"
          type="primary"
          :loading="uploading"
          :disabled="loading || documents.length >= 20 || !selectedFile"
          >上传文档</el-button
        >
      </form>
      <div
        class="mt-5 rounded-lg bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-800"
      >
        首次索引需要下载本地中文向量模型，可能需要几分钟；之后会复用缓存。
        向量化在服务器本地完成，无需填写大模型 API Key。索引就绪后可进入“AI
        问答”；真实问答会把相关片段发送给服务器配置的模型服务。
      </div>
    </div>

    <div
      v-if="error"
      class="ui-error flex flex-wrap items-center justify-between gap-3"
      role="alert"
    >
      <span>{{ error }}</span>
      <el-button size="small" @click="load()">重新加载列表</el-button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <h2 class="m-0 text-base">
        项目文档
        <span class="ml-2 text-xs font-normal text-muted"
          >{{ readyCount }} 个已就绪</span
        >
      </h2>
      <el-button
        text
        :icon="Refresh"
        :loading="loading"
        :disabled="uploading || !!workingId"
        aria-label="刷新知识库"
        @click="load()"
        >刷新</el-button
      >
    </div>
    <el-skeleton
      v-if="loading && !documents.length"
      class="ui-panel"
      :rows="4"
      animated
    />
    <div v-else-if="!documents.length && !error" class="ui-empty">
      <el-icon class="ui-empty-icon"><Document /></el-icon>
      <h3>还没有项目文档</h3>
      <p>先上传一份需求说明，让 AI 之后能够根据资料回答问题。</p>
    </div>
    <div v-else class="grid grid-cols-2 gap-4 max-tablet:grid-cols-1">
      <article
        v-for="doc in documents"
        :key="doc.id"
        :aria-label="doc.filename"
        class="ui-panel min-w-0"
      >
        <div class="flex items-start justify-between gap-3">
          <h3 class="m-0 min-w-0 text-sm leading-6 wrap-anywhere">
            {{ doc.filename }}
          </h3>
          <span
            class="shrink-0 rounded-md px-2 py-1 text-xs"
            :class="statuses[doc.status].color"
            >{{ statuses[doc.status].label }}</span
          >
        </div>
        <p class="my-4 text-xs text-muted">
          {{ (doc.size_bytes / 1024).toFixed(1) }} KB ·
          {{ doc.chunk_count }} 个片段
        </p>
        <p
          v-if="doc.error_message"
          class="ui-error text-xs leading-6"
          role="alert"
        >
          {{ doc.error_message }}
        </p>
        <p v-else-if="doc.status === 'indexing'" class="ui-help">
          正在下载模型或生成向量，可以离开此页面，稍后回来查看。
        </p>
        <p v-else-if="doc.status === 'deleting'" class="ui-help">
          正在清理文档向量，完成后会自动移除。
        </p>
        <div
          class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3"
        >
          <time :datetime="doc.created_at" class="text-xs text-muted">{{
            new Date(doc.created_at).toLocaleString("zh-CN", { hour12: false })
          }}</time>
          <div>
            <el-button
              v-if="doc.status === 'failed' || doc.status === 'delete_failed'"
              text
              type="primary"
              :disabled="!!workingId || uploading"
              :aria-label="'重试文档 ' + doc.filename"
              @click="operate(doc, false)"
              >重试</el-button
            >
            <el-button
              text
              type="danger"
              :disabled="doc.status === 'deleting' || !!workingId || uploading"
              :aria-label="'删除文档 ' + doc.filename"
              @click="operate(doc, true)"
              >删除</el-button
            >
          </div>
        </div>
      </article>
    </div>
    <p v-if="pending && !error" class="ui-help" role="status">
      后台正在处理，列表每 3 秒自动更新。
    </p>
  </section>
</template>
