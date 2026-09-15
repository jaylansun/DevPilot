<script setup lang="ts">
import { computed } from "vue";
import { renderSafeMarkdown } from "@/utils/safe_markdown";

const props = defineProps<{ content: string }>();
const rendered = computed(() => renderSafeMarkdown(props.content));
</script>

<template>
  <!-- 只允许使用已禁用 HTML/图片/危险链接的解析结果，不能直接绑定模型原文。 -->
  <div
    class="min-w-0 text-sm leading-7 text-ink wrap-anywhere [&_p]:mb-4 [&_p:last-child]:mb-0 [&_h3]:mt-6 [&_h3]:mb-3 [&_h3]:text-lg [&_h4]:mt-5 [&_h4]:mb-2 [&_h4]:text-base [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-1 [&_a]:text-brand [&_a]:underline [&_a]:underline-offset-4 [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-focus [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-line [&_pre]:bg-canvas [&_pre]:p-4 [&_pre]:text-xs [&_pre]:leading-6 [&_code]:rounded [&_code]:bg-raised [&_code]:px-1 [&_code]:text-brand [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-ink [&_blockquote]:m-0 [&_blockquote]:my-4 [&_blockquote]:border-l-2 [&_blockquote]:border-brand/50 [&_blockquote]:pl-4 [&_blockquote]:text-muted [&_table]:block [&_table]:max-w-full [&_table]:overflow-auto [&_table]:border-collapse [&_td]:border [&_td]:border-line [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-line [&_th]:bg-raised [&_th]:px-3 [&_th]:py-2 [&_hr]:my-6 [&_hr]:border-0 [&_hr]:border-t [&_hr]:border-line"
    v-html="rendered"
  />
</template>
