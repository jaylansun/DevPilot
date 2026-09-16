<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Delete, Document, Refresh, UploadFilled } from "@element-plus/icons-vue";
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
  queued: { label: "等待索引", color: "bg-raised text-muted" },
  indexing: { label: "正在索引", color: "bg-warning/10 text-warning" },
  ready: { label: "已就绪", color: "bg-success/10 text-success" },
  failed: { label: "索引失败", color: "bg-danger/10 text-danger" },
  deleting: { label: "正在删除", color: "bg-raised text-muted" },
  delete_failed: { label: "删除失败", color: "bg-danger/10 text-danger" },
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
          icon: Delete,
          customClass: "ui-confirm-danger",
          confirmButtonType: "danger",
          autofocus: false,
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
  <section aria-label="项目知识库" class="ui-enter space-y-6">
    <div class="pb-2">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <h2 class="m-0 text-xl font-semibold">把项目资料放在这里</h2>
          <p class="mt-2 mb-0 text-sm leading-7 text-muted">上传需求说明、产品规则或验收标准，让 AI 能根据资料回答问题。</p>
        </div>
        <span class="rounded-full bg-raised px-3 py-1.5 text-xs text-muted">{{ documents.length }} / 20 个文档</span>
      </div>
      <form class="mt-5 flex flex-wrap items-center gap-3 rounded-2xl bg-surface p-4 mobile:p-5" @submit.prevent="upload">
        <div class="min-w-0 flex-1 max-mobile:basis-full">
          <label for="knowledge-upload" class="mb-2 block text-sm font-medium">选择知识库文档</label>
          <input
            id="knowledge-upload"
            ref="fileInput"
            type="file"
            accept=".md,.txt"
            aria-label="选择知识库文档"
            class="ui-interactive block min-h-11 w-full min-w-0 rounded-lg border-0 bg-transparent text-sm text-muted file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-lg file:border-0 file:bg-raised file:px-4 file:py-2 file:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="uploading"
            @change="chooseFile"
          />
          <p class="mt-2 mb-0 text-xs leading-6 text-muted">支持 UTF-8 编码的 .md / .txt，每个文件最多 2 MB，每个项目最多 20 个。</p>
        </div>
        <el-button native-type="submit" type="primary" :icon="UploadFilled" class="ui-interactive min-h-11! max-mobile:w-full" :loading="uploading" :disabled="loading || documents.length >= 20 || !selectedFile">上传文档</el-button>
      </form>
      <details class="mt-2 text-sm text-muted">
        <summary class="ui-interactive min-h-11 cursor-pointer py-3 hover:text-brand">索引与模型使用说明</summary>
        <p class="ui-enter mt-0 mb-0 max-w-prose rounded-xl bg-raised/55 px-4 py-3 text-sm leading-7">
          首次索引需要下载本地中文向量模型，可能需要几分钟；之后会复用缓存。向量化在服务器本地完成，无需填写大模型 API Key。索引就绪后可进入“AI 问答”；真实问答会把相关片段发送给服务器配置的模型服务。
        </p>
      </details>
    </div>

    <div v-if="error" class="ui-error ui-enter flex flex-wrap items-center justify-between gap-3" role="alert">
      <span class="min-w-0 wrap-anywhere">{{ error }}</span>
      <el-button size="small" class="ui-interactive min-h-11!" @click="load()">重新加载列表</el-button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <h2 class="m-0 text-base font-semibold">项目文档 <span class="ml-2 text-xs font-normal text-muted">{{ readyCount }} 个已就绪</span></h2>
      <el-button text :icon="Refresh" class="ui-interactive min-h-11!" :loading="loading" :disabled="uploading || !!workingId" aria-label="刷新知识库" @click="load()">刷新</el-button>
    </div>
    <el-skeleton v-if="loading && !documents.length" class="rounded-2xl bg-surface p-6" :rows="4" animated />
    <div v-else-if="!documents.length && !error" class="ui-enter rounded-2xl bg-surface px-6 py-12 text-center">
      <el-icon class="mb-4 text-3xl text-brand" aria-hidden="true"><Document /></el-icon>
      <h3 class="mb-3 text-lg font-semibold">还没有项目文档</h3>
      <p class="m-0 text-sm leading-7 text-muted">先上传一份需求说明，让 AI 之后能够根据资料回答问题。</p>
    </div>
    <div v-else class="ui-enter divide-y divide-line rounded-2xl bg-surface">
      <article v-for="doc in documents" :key="doc.id" :aria-label="doc.filename" class="ui-interactive min-w-0 px-5 py-5 first:rounded-t-2xl last:rounded-b-2xl hover:bg-canvas/60 mobile:px-6">
        <div class="flex items-start gap-3">
          <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-raised text-lg text-brand" aria-hidden="true"><el-icon><Document /></el-icon></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <h3 class="m-0 min-w-0 text-base font-medium leading-7 wrap-anywhere">{{ doc.filename }}</h3>
              <span class="shrink-0 rounded-full px-2.5 py-1 text-xs" :class="statuses[doc.status].color">{{ statuses[doc.status].label }}</span>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs leading-6 text-muted">
              <span>{{ (doc.size_bytes / 1024).toFixed(1) }} KB</span>
              <span>{{ doc.chunk_count }} 个片段</span>
              <time :datetime="doc.created_at">{{ new Date(doc.created_at).toLocaleString("zh-CN", { hour12: false }) }}</time>
            </div>
            <p v-if="doc.error_message" class="ui-error ui-enter mt-3 mb-0 text-sm leading-7 wrap-anywhere" role="alert">{{ doc.error_message }}</p>
            <p v-else-if="doc.status === 'indexing'" class="mt-3 mb-0 text-sm leading-7 text-muted">正在下载模型或生成向量，可以离开此页面，稍后回来查看。</p>
            <p v-else-if="doc.status === 'deleting'" class="mt-3 mb-0 text-sm leading-7 text-muted">正在清理文档向量，完成后会自动移除。</p>
          </div>
        </div>
        <div class="mt-2 flex justify-end gap-2 [&>.el-button+.el-button]:ml-0">
          <el-button v-if="doc.status === 'failed' || doc.status === 'delete_failed'" text type="primary" class="ui-interactive min-h-11!" :disabled="!!workingId || uploading" :aria-label="'重试文档 ' + doc.filename" @click="operate(doc, false)">重试</el-button>
          <el-button text type="danger" class="ui-interactive min-h-11!" :disabled="doc.status === 'deleting' || !!workingId || uploading" :aria-label="'删除文档 ' + doc.filename" @click="operate(doc, true)">删除</el-button>
        </div>
      </article>
    </div>
    <p v-if="pending && !error" class="ui-help" role="status">后台正在处理，列表每 3 秒自动更新。</p>
  </section>
</template>
