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
            :id="`${gradientId}-front`"
            x1="70"
            y1="98"
            x2="210"
            y2="245"
            gradientUnits="userSpaceOnUse"
          >
            <stop stop-color="#e4edff" />
            <stop offset="0.45" stop-color="#c3dbf5" />
            <stop offset="1" stop-color="#bfd0ed" />
          </linearGradient>
          <linearGradient
            :id="`${gradientId}-top`"
            x1="88"
            y1="59"
            x2="224"
            y2="152"
            gradientUnits="userSpaceOnUse"
          >
            <stop stop-color="#e9f4ff" />
            <stop offset="1" stop-color="#b8c8eb" />
          </linearGradient>
          <linearGradient
            :id="`${gradientId}-side`"
            x1="196"
            y1="110"
            x2="270"
            y2="254"
            gradientUnits="userSpaceOnUse"
          >
            <stop stop-color="#c3c5ed" />
            <stop offset="0.5" stop-color="#ded6f3" />
            <stop offset="1" stop-color="#c4d4ed" />
          </linearGradient>
          <radialGradient :id="`${gradientId}-shadow`">
            <stop stop-color="#899ec2" stop-opacity="0.17" />
            <stop offset="1" stop-color="#899ec2" stop-opacity="0" />
          </radialGradient>
        </defs>
        <ellipse
          cx="158"
          cy="280"
          rx="94"
          ry="17"
          :fill="`url(#${gradientId}-shadow)`"
        />
        <path
          d="m82 89 104-36q10-3 17 5l55 65q5 6 4 14l-53 29-108-25-25-35q-6-12 6-17Z"
          :fill="`url(#${gradientId}-top)`"
        />
        <path
          d="m262 130-5 118q0 10-11 11l-103 5-9-135 128 1Z"
          :fill="`url(#${gradientId}-side)`"
        />
        <path
          d="m80 91 105 36q8 3 8 13l-7 111q-1 12-12 12l-107-37q-11-4-9-16L74 104q1-10 6-13Z"
          :fill="`url(#${gradientId}-front)`"
          fill-opacity="0.87"
        />
        <path
          d="m86 96 99 34q5 2 5 9l-7 109"
          stroke="white"
          stroke-opacity="0.68"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="m117 122 75-20q7-2 12 5l30 40-4 70q0 8-8 9l-79 7q-7 0-11-6l-29-34 8-62q1-7 6-9Z"
          stroke="#9daedb"
          stroke-opacity="0.26"
          stroke-width="3"
        />
        <path
          d="m193 140-5 68q-1 8-10 10l-54 7"
          stroke="#e9e4ff"
          stroke-opacity="0.65"
          stroke-width="7"
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
      class="absolute bottom-0 right-0 flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-xl text-[#637086] transition-colors before:absolute before:inset-2 before:rounded-lg before:bg-white/85 before:shadow-[0_2px_10px_rgba(35,55,100,0.06)] hover:text-[#365eea] hover:before:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#365eea] motion-reduce:transition-none"
      :aria-label="paused ? '播放装饰动画' : '暂停装饰动画'"
      :title="paused ? '播放装饰动画' : '暂停装饰动画'"
      @click="toggleMotion"
    >
      <svg
        v-if="paused"
        class="relative"
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
        class="relative"
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
      class="absolute bottom-1 right-1 text-xs text-[#637086]"
      >已减少动态</span
    >
  </div>
</template>
