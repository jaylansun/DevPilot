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
      <p class="eyebrow">DAY 01 · FOUNDATION</p>
      <h1 id="page-title">DevPilot</h1>
      <p class="lead">面向项目文档、任务看板与人工审批的 AI 协作助手。</p>

      <div class="milestone-grid" aria-label="第一天完成范围">
        <article>
          <span>01</span>
          <h2>Vue 工作台</h2>
          <p>Vite + TypeScript 前端入口已经就绪。</p>
        </article>
        <article>
          <span>02</span>
          <h2>FastAPI 服务</h2>
          <p>健康检查与自动接口文档可直接访问。</p>
        </article>
        <article>
          <span>03</span>
          <h2>PostgreSQL 基线</h2>
          <p>Docker Compose 已声明 pgvector 数据服务。</p>
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
        下一步：接入 Alembic、PostgreSQL 数据模型和项目 CRUD。
      </footer>
    </section>
  </main>
</template>

