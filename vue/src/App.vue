<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheckFilled, Connection, MagicStick } from '@element-plus/icons-vue'

type Health = {
  status: string
  service: string
  timestamp: string
  ai_mode: string
}

const status = ref<'idle' | 'checking' | 'online' | 'offline'>('idle')
const health = ref<Health | null>(null)
const error = ref('')

async function checkApi() {
  status.value = 'checking'
  error.value = ''
  try {
    const response = await fetch('/api/v1/health')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json()
    status.value = 'online'
  } catch (reason) {
    health.value = null
    status.value = 'offline'
    error.value = reason instanceof Error ? reason.message : '无法连接到 API'
  }
}
</script>

<template>
  <main class="landing-shell">
    <section class="workspace-card" aria-labelledby="page-title">
      <div class="brand-mark" aria-hidden="true"><MagicStick /></div>
      <p class="eyebrow">第 4 天 · 项目与任务 API</p>
      <h1 id="page-title">DevPilot</h1>
      <p class="lead">面向项目文档、任务看板与人工审批的 AI 协作助手。</p>

      <div class="milestone-grid" aria-label="前四天完成范围">
        <article>
          <span>01</span>
          <h2>认证与权限</h2>
          <p>JWT、预置账号和成员/审批人权限已经就绪。</p>
        </article>
        <article>
          <span>02</span>
          <h2>项目管理</h2>
          <p>项目创建、分页查询、局部更新和归属校验已经就绪。</p>
        </article>
        <article>
          <span>03</span>
          <h2>任务管理</h2>
          <p>任务筛选、状态更新和并发版本控制已经就绪。</p>
        </article>
      </div>

      <div class="api-check">
        <div>
          <p class="check-title"><Connection /> 服务连通性</p>
          <p v-if="status === 'idle'">启动服务后，检查 FastAPI 是否可用。</p>
          <p v-else-if="status === 'checking'">正在检查 API…</p>
          <p v-else-if="status === 'online'" class="success">
            <CircleCheckFilled /> {{ health?.service }} 已就绪 · {{ health?.ai_mode }} 模式
          </p>
          <p v-else class="failure">尚未连接：{{ error }}</p>
        </div>
        <el-button type="primary" :loading="status === 'checking'" @click="checkApi">
          检查 API
        </el-button>
      </div>

      <footer>
        当前进度：实施计划第 1 至第 4 天后端内容已经完成。
      </footer>
    </section>
  </main>
</template>
