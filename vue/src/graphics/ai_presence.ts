/**
 * 局部 AI 核心装饰：原生 WebGL2，无网络资源、第三方运行时或业务数据。
 * SDF 圆环与球面追踪方法参考 MiniMax-AI/skills 的 shader-dev（MIT）。
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

// 圆环保留真实厚度；两组姿态共同构成空间轨道，而不是平面描边。
vec2 sceneDistance(vec3 p) {
  p.xz = rotate2(uTime * 0.12 + 0.38) * p.xz;
  p.yz = rotate2(0.24) * p.yz;
  vec3 a = p;
  a.yz = rotate2(0.72) * a.yz;
  float outer = length(vec2(length(a.xy) - 0.92, a.z)) - 0.12;
  vec3 b = p;
  b.xz = rotate2(0.62) * b.xz;
  b.xy = rotate2(-0.45) * b.xy;
  float inner = length(vec2(length(b.xy) - 0.71, b.z)) - 0.09;
  float core = length(p) - 0.33;
  vec2 result = vec2(core, 0.0);
  if (outer < result.x) result = vec2(outer, 1.0);
  if (inner < result.x) result = vec2(inner, 2.0);
  return result;
}

vec3 surfaceNormal(vec3 p) {
  const vec2 e = vec2(0.0015, -0.0015);
  return normalize(
    e.xyy * sceneDistance(p + e.xyy).x +
    e.yyx * sceneDistance(p + e.yyx).x +
    e.yxy * sceneDistance(p + e.yxy).x +
    e.xxx * sceneDistance(p + e.xxx).x
  );
}

vec3 studioReflection(vec3 direction) {
  float strip = pow(max(0.0, 1.0 - abs(direction.x + 0.38 * direction.z)), 12.0);
  float upper = smoothstep(-0.18, 0.75, direction.y);
  float blueRim = pow(max(dot(direction, normalize(vec3(-0.8, 0.4, -0.6))), 0.0), 10.0);
  return vec3(0.025, 0.047, 0.082) +
    upper * vec3(0.09, 0.15, 0.22) +
    strip * vec3(0.75, 0.9, 1.0) +
    blueRim * vec3(0.22, 0.56, 0.95);
}

void main() {
  vec2 uv = (2.0 * gl_FragCoord.xy - uResolution) / min(uResolution.x, uResolution.y);
  vec3 origin = vec3(0.0, 0.12, 3.8);
  vec3 ray = normalize(vec3(uv, -2.72));
  float travel = 2.5;
  float material = -1.0;
  vec3 p = origin;

  // 只有 56 次主步进，无纹理采样、阴影循环或多重后期通道。
  for (int i = 0; i < 56; i++) {
    p = origin + travel * ray;
    vec2 sampleDistance = sceneDistance(p);
    if (sampleDistance.x < 0.002) {
      material = sampleDistance.y;
      break;
    }
    travel += sampleDistance.x;
    if (travel > 5.1) break;
  }

  if (material < 0.0) {
    fragColor = vec4(0.0);
    return;
  }

  vec3 normal = surfaceNormal(p);
  vec3 reflected = reflect(ray, normal);
  vec3 key = normalize(vec3(-0.6, 0.9, 1.2));
  float diffuse = max(dot(normal, key), 0.0);
  float specular = pow(max(dot(normal, normalize(key - ray)), 0.0), 64.0);
  float fresnel = pow(1.0 - max(dot(normal, -ray), 0.0), 3.0);
  float occlusion = clamp(sceneDistance(p + normal * 0.09).x / 0.09, 0.3, 1.0);
  vec3 tint = material < 0.5 ? vec3(0.27, 0.63, 0.89) :
    (material > 1.5 ? vec3(0.2, 0.43, 0.62) : vec3(0.55, 0.67, 0.79));
  vec3 color = tint * (0.065 + diffuse * 0.24) * occlusion;
  color += studioReflection(reflected) * (0.6 + fresnel * 0.5);
  color += specular * vec3(0.76, 0.9, 1.0) * 0.85;
  color += fresnel * vec3(0.12, 0.32, 0.5) * 0.24;
  if (material < 0.5) color += vec3(0.025, 0.12, 0.2);
  color = color / (color + vec3(0.75));
  color = pow(color, vec3(0.4545));
  fragColor = vec4(color, 1.0);
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
