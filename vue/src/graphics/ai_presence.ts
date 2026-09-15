/**
 * 局部 AI 核心装饰：原生 WebGL2，无网络资源、第三方运行时或业务数据。
 * SDF 圆角立方、球面追踪与菲涅耳透射近似参考 shader-dev（MIT）。
 * 来源：https://github.com/MiniMax-AI/skills/tree/main/skills/shader-dev
 * Copyright (c) 2026 MiniMax
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

export const PRESENCE_MAX_PIXEL_SIZE = 600;
export const PRESENCE_MAX_DPR = 1.5;
export const PRESENCE_FRAME_INTERVAL = 1000 / 30;

export function presencePixelSize(width: number, height: number, dpr: number) {
  const safeWidth = Math.max(1, Number.isFinite(width) ? width : 1);
  const safeHeight = Math.max(1, Number.isFinite(height) ? height : 1);
  const pixelRatio = Math.max(
    1,
    Math.min(Number.isFinite(dpr) ? dpr : 1, PRESENCE_MAX_DPR),
  );
  const scale = Math.min(
    pixelRatio,
    PRESENCE_MAX_PIXEL_SIZE / Math.max(safeWidth, safeHeight),
  );
  return {
    width: Math.max(1, Math.round(safeWidth * scale)),
    height: Math.max(1, Math.round(safeHeight * scale)),
  };
}

const vertexSource = `#version 300 es
void main() {
  vec2 position = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(position * 2.0 - 1.0, 0.0, 1.0);
}`;

const fragmentSource = `#version 300 es
precision highp float;
uniform vec2 uResolution;
uniform float uTime;
out vec4 fragColor;

mat2 rotate2(float angle) {
  float c = cos(angle), s = sin(angle);
  return mat2(c, -s, s, c);
}

// 很小幅度的摆动保留三面构图；不持续自转，避免阅读时抢夺注意力。
vec3 localPoint(vec3 p) {
  p.y -= 0.055 + sin(uTime * 0.65) * 0.025;
  p.xy = rotate2(-0.12) * p.xy;
  p.yz = rotate2(-0.44 + sin(uTime * 0.28) * 0.025) * p.yz;
  p.xz = rotate2(0.62 + sin(uTime * 0.35) * 0.045) * p.xz;
  return p;
}

float sceneDistance(vec3 p) {
  vec3 q = abs(localPoint(p)) - vec3(0.49);
  return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0) - 0.12;
}

vec3 surfaceNormal(vec3 p) {
  const vec2 e = vec2(0.0015, -0.0015);
  return normalize(
    e.xyy * sceneDistance(p + e.xyy) +
    e.yyx * sceneDistance(p + e.yyx) +
    e.yxy * sceneDistance(p + e.yxy) +
    e.xxx * sceneDistance(p + e.xxx)
  );
}

// 浅色摄影棚环境由数学函数生成，无贴图下载或黑色天幕。
vec3 studioLight(vec3 direction) {
  float horizon = smoothstep(-0.75, 0.8, direction.y);
  vec3 light = mix(vec3(0.70, 0.77, 0.89), vec3(0.99, 1.0, 1.0), horizon);
  float windowLight = pow(max(0.0, dot(direction, normalize(vec3(-0.6, 0.7, 1.0)))), 14.0);
  return light + vec3(0.3) * windowLight;
}

float backEdge(vec3 p) {
  vec3 sides = abs(abs(localPoint(p)) - vec3(0.61));
  float secondSide = min(max(sides.x, sides.y), min(max(sides.x, sides.z), max(sides.y, sides.z)));
  return 1.0 - smoothstep(0.018, 0.065, secondSide);
}

void main() {
  vec2 uv = (2.0 * gl_FragCoord.xy - uResolution) / min(uResolution.x, uResolution.y);
  vec3 origin = vec3(0.0, 0.0, 3.8);
  vec3 ray = normalize(vec3(uv, -3.1));
  float travel = 2.7;
  bool hit = false;
  vec3 p = origin;

  // 56 次表面步进；透射只另取 8 次内部样本，无后期处理通道。
  for (int i = 0; i < 56; i++) {
    p = origin + travel * ray;
    float distance = sceneDistance(p);
    if (distance < 0.0015) {
      hit = true;
      break;
    }
    travel += distance;
    if (travel > 5.0) break;
  }

  if (!hit) {
    vec2 shadowPoint = (uv - vec2(0.0, -0.78)) / vec2(0.60, 0.12);
    float shadow = exp(-dot(shadowPoint, shadowPoint) * 1.8) * 0.11;
    fragColor = vec4(0.39, 0.48, 0.66, shadow);
    return;
  }

  vec3 normal = surfaceNormal(p);
  vec3 reflected = reflect(ray, normal);
  vec3 transmittedRay = refract(ray, normal, 0.76);
  vec3 localEntry = localPoint(p);
  vec3 localRay = normalize(localPoint(p + transmittedRay) - localEntry);
  vec3 raySign = mix(vec3(-1.0), vec3(1.0), step(vec3(0.0), localRay));
  vec3 safeRay = raySign * max(abs(localRay), vec3(0.0001));
  vec3 exits = (raySign * 0.61 - localEntry) / safeRay;
  float depth = max(0.01, min(exits.x, min(exits.y, exits.z)));
  // 从包围盒背面回溯至圆角表面，固定 8 步也不产生内部步进的破碎边缘。
  for (int j = 0; j < 8; j++) {
    float outside = sceneDistance(p + transmittedRay * depth);
    if (outside < 0.0008) break;
    depth -= outside;
  }
  vec3 rear = p + transmittedRay * depth;
  vec3 rearNormal = surfaceNormal(rear);
  vec3 outgoing = refract(transmittedRay, -rearNormal, 1.0 / 0.76);
  if (dot(outgoing, outgoing) < 0.1) outgoing = reflect(transmittedRay, -rearNormal);
  vec3 localNormal = normalize(localPoint(p + normal) - localPoint(p));
  vec3 glassTint = mix(vec3(0.70, 0.85, 0.99), vec3(0.84, 0.78, 0.98), smoothstep(-0.6, 0.7, localNormal.x));
  vec3 absorption = mix(vec3(0.19, 0.075, 0.015), vec3(0.08, 0.15, 0.012), smoothstep(-0.5, 0.8, localNormal.x));
  vec3 transmission = studioLight(outgoing) * exp(-absorption * depth);
  transmission = mix(transmission, glassTint, 0.18);
  transmission -= backEdge(rear) * vec3(0.085, 0.06, 0.01);

  vec3 key = normalize(vec3(-0.7, 0.9, 1.2));
  float diffuse = max(dot(normal, key), 0.0);
  float highlight = pow(max(dot(normal, normalize(key - ray)), 0.0), 100.0);
  float grazing = pow(1.0 - max(dot(normal, -ray), 0.0), 3.0);
  float fresnel = 0.04 + 0.96 * grazing;
  vec3 color = mix(transmission * (0.84 + diffuse * 0.13), studioLight(reflected), fresnel * 0.72);
  color += highlight * vec3(0.30);
  // 蓝紫色边缘分出轮廓，让 110px 的小尺寸也能读出立方体的三个面。
  color -= grazing * vec3(0.21, 0.13, 0.015);
  color = pow(clamp(color, 0.0, 1.0), vec3(0.8));
  fragColor = vec4(color, 0.97);
}`;

export interface PresenceRenderer {
  render(seconds: number): void;
  resize(width: number, height: number, dpr: number): void;
  dispose(): void;
}

export function createPresenceRenderer(
  canvas: HTMLCanvasElement,
): PresenceRenderer {
  const gl = canvas.getContext("webgl2", {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    powerPreference: "low-power",
    premultipliedAlpha: false,
    // 小画布暂停后保留绘制结果，重新合成图层时不出现透明空白。
    preserveDrawingBuffer: true,
  });
  if (!gl) throw new Error("当前设备不支持 WebGL2");

  const shaders: WebGLShader[] = [];
  let program: WebGLProgram | null = null;
  let vertexArray: WebGLVertexArrayObject | null = null;
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    for (const shader of shaders) gl.deleteShader(shader);
    if (program) gl.deleteProgram(program);
    if (vertexArray) gl.deleteVertexArray(vertexArray);
  };

  try {
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) throw new Error("无法创建装饰图形着色器");
      shaders.push(shader);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error("装饰图形着色器编译失败");
      }
      return shader;
    };
    const vertex = compile(gl.VERTEX_SHADER, vertexSource);
    const fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    program = gl.createProgram();
    vertexArray = gl.createVertexArray();
    if (!program || !vertexArray) throw new Error("无法创建装饰图形程序");
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error("装饰图形程序链接失败");
    }
    const resolution = gl.getUniformLocation(program, "uResolution");
    const time = gl.getUniformLocation(program, "uTime");
    if (resolution === null || time === null)
      throw new Error("装饰图形参数不可用");

    return {
      resize(width, height, dpr) {
        if (disposed) return;
        const pixels = presencePixelSize(width, height, dpr);
        if (canvas.width !== pixels.width || canvas.height !== pixels.height) {
          canvas.width = pixels.width;
          canvas.height = pixels.height;
        }
      },
      render(seconds) {
        if (disposed || gl.isContextLost()) return;
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.useProgram(program);
        gl.bindVertexArray(vertexArray);
        gl.uniform2f(resolution, canvas.width, canvas.height);
        gl.uniform1f(time, seconds);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      },
      dispose,
    };
  } catch (error) {
    dispose();
    throw error;
  }
}

interface FrameScheduler {
  request: (callback: FrameRequestCallback) => number;
  cancel: (handle: number) => void;
}

/** 统一控制显示、暂停与减少动态；隐藏时不继续排队动画帧。 */
export function createPresenceMotion(
  render: (seconds: number) => void,
  scheduler: FrameScheduler = {
    request: (callback) => requestAnimationFrame(callback),
    cancel: (handle) => cancelAnimationFrame(handle),
  },
) {
  let active = false;
  let animated = true;
  let disposed = false;
  let pending: number | null = null;
  let lastFrame: number | null = null;
  let elapsed = 0;
  let dirty = true;

  const cancel = () => {
    if (pending !== null) scheduler.cancel(pending);
    pending = null;
    lastFrame = null;
  };
  const schedule = () => {
    if (!disposed && active && pending === null && (animated || dirty)) {
      pending = scheduler.request(frame);
    }
  };
  const frame = (timestamp: number) => {
    pending = null;
    if (disposed || !active) return;
    const delta = lastFrame === null ? 0 : timestamp - lastFrame;
    if (lastFrame === null || delta >= PRESENCE_FRAME_INTERVAL) {
      if (animated && lastFrame !== null)
        elapsed += Math.min(delta, 100) / 1000;
      lastFrame = timestamp;
      dirty = false;
      render(elapsed);
    }
    schedule();
  };

  return {
    setActive(value: boolean) {
      if (disposed || active === value) return;
      active = value;
      if (value) {
        dirty = true;
        schedule();
      } else cancel();
    },
    setAnimated(value: boolean) {
      if (disposed || animated === value) return;
      animated = value;
      cancel();
      // 暂停时保留当前画面，不再无意义地重新渲染。
      if (value || dirty) schedule();
    },
    invalidate() {
      if (disposed) return;
      dirty = true;
      schedule();
    },
    dispose() {
      disposed = true;
      cancel();
    },
  };
}
