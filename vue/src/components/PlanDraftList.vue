<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { getDraft, listDrafts } from "@/api/plan_draft_api";
import { errorMessage } from "@/api/http_client";
import type { PlanDraftVO } from "@/types/api";

const props = defineProps<{ projectId: string; refreshKey: number; disabled: boolean; selectedId?: string }>();
const emit = defineEmits<{ select: [draft: PlanDraftVO] }>();
const items = ref<PlanDraftVO[]>([]), total = ref(0), offset = ref(0);
const loading = ref(false), opening = ref(false), message = ref("");
let active = true, loader: AbortController | undefined, opener: AbortController | undefined;

async function load() {
  loader?.abort();
  const current = new AbortController(); loader = current; loading.value = true; message.value = "";
  try {
    const page = await listDrafts(props.projectId, offset.value, current.signal);
    if (active && !current.signal.aborted) { items.value = page.items; total.value = page.total; }
  } catch (error) {
    if (active && !current.signal.aborted) message.value = errorMessage(error);
  } finally { if (active && !current.signal.aborted) loading.value = false; }
}
async function open(id: string) {
  if (props.disabled || opening.value) return;
  opener?.abort();
  const current = new AbortController(); opener = current; opening.value = true; message.value = "";
  try {
    const draft = await getDraft(props.projectId, id, current.signal);
    if (active && !current.signal.aborted && !props.disabled) emit("select", draft);
  } catch (error) {
    if (active && !current.signal.aborted) message.value = errorMessage(error);
  } finally { if (active && !current.signal.aborted) opening.value = false; }
}
function page(delta: number) { offset.value = Math.max(0, offset.value + delta); void load(); }
watch(() => props.refreshKey, () => { offset.value = 0; void load(); });
watch(() => props.disabled, value => { if (value) { opener?.abort(); opening.value = false; } });
onMounted(load);
onBeforeUnmount(() => { active = false; loader?.abort(); opener?.abort(); });
</script>

<template>
  <section aria-label="已保存草案" class="mt-5 border-t border-line pt-4">
    <div class="flex items-center justify-between gap-2">
      <h3 class="m-0 text-sm font-semibold">已保存草案 <span class="font-normal text-muted">{{ total }}</span></h3>
      <el-button text :loading="loading" :disabled="disabled || opening" @click="load">刷新草案</el-button>
    </div>
    <p v-if="message" role="alert" class="ui-error">{{ message }}</p>
    <p v-if="!loading && !items.length" class="text-xs leading-6 text-muted">生成成功后会自动保存，刷新页面也可从这里打开。</p>
    <ul class="my-2 max-h-64 list-none space-y-2 overflow-y-auto overscroll-contain p-0">
      <li v-for="item in items" :key="item.id">
        <button type="button" :disabled="disabled || opening" :aria-pressed="selectedId === item.id" :aria-label="'打开草案：' + item.goal" class="w-full cursor-pointer rounded-lg border border-line bg-canvas p-3 text-left disabled:cursor-not-allowed disabled:opacity-50 aria-pressed:border-brand focus-visible:outline-2 focus-visible:outline-brand" @click="open(item.id)">
          <span class="line-clamp-2 text-sm leading-6 wrap-anywhere">{{ item.goal }}</span>
          <span class="mt-1 block text-xs text-muted">{{ item.status === 'draft' ? '待提交' : '已提交审批' }} · 第 {{ item.version }} 版</span>
        </button>
      </li>
    </ul>
    <div v-if="total > 20" class="flex gap-2">
      <el-button :disabled="!offset || loading || disabled" @click="page(-20)">上一页草案</el-button>
      <el-button :disabled="offset + 20 >= total || loading || disabled" @click="page(20)">下一页草案</el-button>
    </div>
  </section>
</template>
