<script setup lang="ts">
import { computed } from "vue";
import { renderSafeMarkdown } from "@/utils/safe_markdown";

const props = defineProps<{ content: string }>();
const rendered = computed(() => renderSafeMarkdown(props.content));
</script>

<template>
  <!-- 只允许使用已禁用 HTML/图片/危险链接的解析结果，不能直接绑定模型原文。 -->
  <div
    class="min-w-0 max-w-[72ch] text-base leading-[1.85] text-ink wrap-anywhere [&>:first-child]:mt-0 [&>:last-child]:mb-0 [&_p]:mt-0 [&_p]:mb-5 [&_h3]:mt-7 [&_h3]:mb-3 [&_h3]:text-xl [&_h3]:leading-normal [&_h3]:font-semibold [&_h4]:mt-6 [&_h4]:mb-2 [&_h4]:text-lg [&_h4]:leading-normal [&_h4]:font-semibold [&_h5]:mt-5 [&_h5]:mb-2 [&_h5]:text-[17px] [&_h5]:leading-normal [&_h5]:font-semibold [&_h6]:mt-5 [&_h6]:mb-2 [&_h6]:text-base [&_h6]:leading-normal [&_h6]:font-semibold [&_strong]:font-semibold [&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-1.5 [&_li>p]:mb-2 [&_a]:rounded-sm [&_a]:text-brand [&_a]:underline [&_a]:decoration-brand/35 [&_a]:underline-offset-4 [&_a:hover]:decoration-brand [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-2 [&_a:focus-visible]:outline-brand [&_pre]:my-5 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-line [&_pre]:bg-canvas [&_pre]:p-4 [&_pre]:text-[13px] [&_pre]:leading-7 [&_code]:rounded-md [&_code]:bg-raised [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.875em] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit [&_blockquote]:mx-0 [&_blockquote]:my-5 [&_blockquote]:border-l-2 [&_blockquote]:border-brand/30 [&_blockquote]:pl-4 [&_blockquote]:text-muted [&_table]:my-5 [&_table]:block [&_table]:max-w-full [&_table]:overflow-auto [&_table]:border-collapse [&_table]:text-sm [&_td]:border [&_td]:border-line [&_td]:px-4 [&_td]:py-2.5 [&_th]:border [&_th]:border-line [&_th]:bg-canvas [&_th]:px-4 [&_th]:py-2.5 [&_th]:font-semibold [&_hr]:my-7 [&_hr]:border-0 [&_hr]:border-t [&_hr]:border-line"
    v-html="rendered"
  />
</template>
