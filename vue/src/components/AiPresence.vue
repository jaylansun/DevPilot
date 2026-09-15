<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from "vue";
import type { PresenceRenderer } from "@/graphics/ai_presence";

const root = ref<HTMLDivElement>();
const canvas = ref<HTMLCanvasElement>();
const ready = ref(false);
const unavailable = ref(false);
const paused = ref(false);
const reducedMotion = ref(false);
const gradientId = `ai-presence-${useId().replace(/:/g, "")}`;
const isStatic = computed(() => paused.value || reducedMotion.value);
let renderer: PresenceRenderer | null = null;
let motion: ReturnType<
  (typeof import("@/graphics/ai_presence"))["createPresenceMotion"]
> | null = null;
let intersection: IntersectionObserver | null = null;
let resize: ResizeObserver | null = null;
let media: MediaQueryList | null = null;
let visible = false;
let loading = false;
let disposed = false;

function syncMotion() {
  motion?.setAnimated(!isStatic.value);
  motion?.setActive(visible && !document.hidden);
}

function resizeCanvas() {
  const bounds = root.value?.getBoundingClientRect();
  if (!bounds || !renderer) return;
  renderer.resize(bounds.width, bounds.height, window.devicePixelRatio);
  motion?.invalidate();
}

function useFallback() {
  unavailable.value = true;
  ready.value = false;
  motion?.dispose();
  renderer?.dispose();
  motion = null;
  renderer = null;
}

async function loadGraphic() {
  if (
    loading ||
    renderer ||
    unavailable.value ||
    disposed ||
    !visible ||
    document.hidden
  )
    return;
  loading = true;
  try {
    // 第一次进入视口才加载着色器；网络慢或不支持 WebGL 时先显示静态图。
    const graphics = await import("@/graphics/ai_presence");
    if (disposed || !canvas.value || !visible || document.hidden) return;
    renderer = graphics.createPresenceRenderer(canvas.value);
    motion = graphics.createPresenceMotion((seconds) => {
      try {
        renderer?.render(seconds);
        ready.value = true;
      } catch {
        useFallback();
      }
    });
    resizeCanvas();
    syncMotion();
  } catch {
    if (!disposed) useFallback();
  } finally {
    loading = false;
  }
}

function visibilityChanged() {
  syncMotion();
  if (!document.hidden) void loadGraphic();
}

function preferenceChanged() {
  reducedMotion.value = media?.matches ?? false;
  syncMotion();
}

function toggleMotion() {
  if (reducedMotion.value) return;
  paused.value = !paused.value;
  syncMotion();
}

function contextLost(event: Event) {
  event.preventDefault();
  useFallback();
}

onMounted(() => {
  const device = navigator as Navigator & {
    deviceMemory?: number;
    connection?: { saveData?: boolean };
  };
  media = window.matchMedia("(prefers-reduced-motion: reduce)");
  reducedMotion.value = media.matches;
  media.addEventListener("change", preferenceChanged);
  // 节流网络或低配小屏保持静态展示，不占用 GPU。
  const lowMemory =
    device.deviceMemory !== undefined && device.deviceMemory <= 4;
  const fewCores =
    device.hardwareConcurrency > 0 && device.hardwareConcurrency <= 4;
  if (
    device.connection?.saveData ||
    (window.innerWidth <= 640 && (lowMemory || fewCores))
  ) {
    unavailable.value = true;
    return;
  }
  document.addEventListener("visibilitychange", visibilityChanged);
  canvas.value?.addEventListener("webglcontextlost", contextLost);
  if (typeof ResizeObserver !== "undefined") {
    resize = new ResizeObserver(resizeCanvas);
    if (root.value) resize.observe(root.value);
  } else window.addEventListener("resize", resizeCanvas);
  if (typeof IntersectionObserver !== "undefined") {
    intersection = new IntersectionObserver(
      (entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
        syncMotion();
        if (visible) void loadGraphic();
      },
      { threshold: 0.01 },
    );
    if (root.value) intersection.observe(root.value);
  } else {
    visible = true;
    void loadGraphic();
  }
});

onBeforeUnmount(() => {
  disposed = true;
  intersection?.disconnect();
  resize?.disconnect();
  media?.removeEventListener("change", preferenceChanged);
  document.removeEventListener("visibilitychange", visibilityChanged);
  window.removeEventListener("resize", resizeCanvas);
  canvas.value?.removeEventListener("webglcontextlost", contextLost);
  motion?.dispose();
  renderer?.dispose();
});
</script>

<template>
  <div
    ref="root"
    class="relative isolate h-full w-full"
    data-testid="ai-presence"
  >
    <div class="pointer-events-none absolute inset-0" aria-hidden="true">
      <svg
        v-show="!ready"
        class="h-full w-full"
        viewBox="0 0 320 320"
        fill="none"
        data-testid="ai-presence-fallback"
      >
        <defs>
          <linearGradient
            :id="`${gradientId}-metal`"
            x1="74"
            y1="73"
            x2="243"
            y2="248"
            gradientUnits="userSpaceOnUse"
          >
            <stop stop-color="#d7eeff" />
            <stop offset="0.25" stop-color="#8296af" />
            <stop offset="0.5" stop-color="#263f5a" />
            <stop offset="0.73" stop-color="#8ccfff" />
            <stop offset="1" stop-color="#344f69" />
          </linearGradient>
          <radialGradient
            :id="`${gradientId}-core`"
            cx="0"
            cy="0"
            r="1"
            gradientTransform="translate(150 145) rotate(48) scale(51)"
            gradientUnits="userSpaceOnUse"
          >
            <stop stop-color="#d7f0ff" />
            <stop offset="0.3" stop-color="#8ccfff" />
            <stop offset="0.72" stop-color="#39688a" />
            <stop offset="1" stop-color="#122c43" />
          </radialGradient>
        </defs>
        <ellipse
          cx="160"
          cy="160"
          rx="101"
          ry="60"
          transform="rotate(-30 160 160)"
          :stroke="`url(#${gradientId}-metal)`"
          stroke-width="18"
        />
        <ellipse
          cx="160"
          cy="160"
          rx="57"
          ry="86"
          transform="rotate(-25 160 160)"
          :stroke="`url(#${gradientId}-metal)`"
          stroke-width="12"
        />
        <circle cx="160" cy="160" r="33" :fill="`url(#${gradientId}-core)`" />
        <path
          d="M78 196c20 13 60 10 97-8s65-45 69-65"
          :stroke="`url(#${gradientId}-metal)`"
          stroke-width="18"
          stroke-linecap="round"
        />
        <path
          d="M137 87c-12 19-12 51-3 84s26 61 44 70"
          :stroke="`url(#${gradientId}-metal)`"
          stroke-width="12"
          stroke-linecap="round"
        />
      </svg>
      <canvas
        ref="canvas"
        class="absolute inset-0 h-full w-full"
        :class="ready ? 'opacity-100' : 'opacity-0'"
      />
    </div>
    <button
      v-if="ready && !unavailable && !reducedMotion"
      type="button"
      class="absolute bottom-0 right-0 flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-full border border-white/20 bg-[#141c2a]/90 text-[#b7cede] transition-colors hover:border-[#8ccfff]/60 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8ccfff] motion-reduce:transition-none"
      :aria-label="paused ? '播放装饰动画' : '暂停装饰动画'"
      :title="paused ? '播放装饰动画' : '暂停装饰动画'"
      @click="toggleMotion"
    >
      <svg
        v-if="paused"
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="m5 3 7 5-7 5V3Z" />
      </svg>
      <svg
        v-else
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden="true"
      >
        <rect x="4" y="3" width="2.5" height="10" rx="1" />
        <rect x="9.5" y="3" width="2.5" height="10" rx="1" />
      </svg>
    </button>
    <span
      v-if="reducedMotion && ready"
      class="absolute bottom-1 right-1 text-xs text-[#9daec0]"
      >已减少动态</span
    >
  </div>
</template>
