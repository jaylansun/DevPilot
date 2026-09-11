<script setup lang="ts">
import { CircleCheck } from "@element-plus/icons-vue";
</script>

<template>
  <section>
    <div class="ui-page-heading">
      <div>
        <p class="ui-eyebrow">让每一份计划更可靠</p>
        <h1>审批工作区</h1>
        <p class="ui-muted">你已作为审批人登录。</p>
      </div>
    </div>
    <div class="ui-empty">
      <div class="ui-empty-icon"><CircleCheck /></div>
      <h2>审批中心即将开放</h2>
      <p>
        这里将展示成员提交的 AI 任务方案。<br />你可以查看风险、调整任务，然后批准或拒绝。
      </p>
      <p class="ui-empty-example">
        审批功能尚未接入，当前暂无可执行的审批操作。
      </p>
    </div>
  </section>
</template>
