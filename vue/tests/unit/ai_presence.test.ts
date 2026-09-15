import { describe, expect, it, vi } from "vitest";
import {
  createPresenceMotion,
  createPresenceRenderer,
  presencePixelSize,
} from "@/graphics/ai_presence";

function frameClock() {
  let nextHandle = 0;
  const callbacks = new Map<number, FrameRequestCallback>();
  return {
    request: vi.fn((callback: FrameRequestCallback) => {
      const handle = ++nextHandle;
      callbacks.set(handle, callback);
      return handle;
    }),
    cancel: vi.fn((handle: number) => callbacks.delete(handle)),
    step(timestamp: number) {
      const pending = [...callbacks.values()];
      callbacks.clear();
      pending.forEach((callback) => callback(timestamp));
    },
    pending: () => callbacks.size,
  };
}

function glFixture(
  options: { compile?: boolean; link?: boolean; lost?: boolean } = {},
) {
  const gl = {
    VERTEX_SHADER: 1,
    FRAGMENT_SHADER: 2,
    COMPILE_STATUS: 3,
    LINK_STATUS: 4,
    TRIANGLES: 5,
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => options.compile !== false),
    createProgram: vi.fn(() => ({})),
    createVertexArray: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => options.link !== false),
    getUniformLocation: vi.fn(() => ({})),
    deleteShader: vi.fn(),
    deleteProgram: vi.fn(),
    deleteVertexArray: vi.fn(),
    isContextLost: vi.fn(() => options.lost === true),
    viewport: vi.fn(),
    useProgram: vi.fn(),
    bindVertexArray: vi.fn(),
    uniform2f: vi.fn(),
    uniform1f: vi.fn(),
    drawArrays: vi.fn(),
  };
  const canvas = document.createElement("canvas");
  const context = vi
    .spyOn(canvas, "getContext")
    .mockReturnValue(gl as unknown as WebGL2RenderingContext);
  return { gl, canvas, context };
}

describe("AI 核心的像素预算", () => {
  it("像素密度最高为 1.5", () => {
    expect(presencePixelSize(200, 100, 3)).toEqual({ width: 300, height: 150 });
  });

  it("大画布最长边不超过 600 并保持宽高比", () => {
    expect(presencePixelSize(1000, 500, 2)).toEqual({
      width: 600,
      height: 300,
    });
    expect(presencePixelSize(100, 1200, 1)).toEqual({ width: 50, height: 600 });
  });

  it("零尺寸和非有限值不会产生无效缓冲区", () => {
    expect(presencePixelSize(0, Number.NaN, Number.POSITIVE_INFINITY)).toEqual({
      width: 1,
      height: 1,
    });
  });
});

describe("AI 核心的动画调度", () => {
  it("初始不可见时不排队帧，显示后才开始", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    expect(clock.pending()).toBe(0);
    motion.setActive(true);
    clock.step(0);
    expect(render).toHaveBeenCalledExactlyOnceWith(0);
    expect(clock.pending()).toBe(1);
    motion.dispose();
  });

  it("普通播放时渲染频率不超过 30 帧", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setActive(true);
    [0, 16, 32, 34, 50, 66, 68].forEach(clock.step);
    expect(render).toHaveBeenCalledTimes(3);
    expect(render.mock.calls.map(([seconds]) => seconds)).toEqual([
      0, 0.034, 0.068,
    ]);
    motion.dispose();
  });

  it("离屏或页面隐藏后取消帧且返回时不跳过大量动画时间", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setActive(true);
    clock.step(0);
    clock.step(40);
    motion.setActive(false);
    expect(clock.pending()).toBe(0);
    clock.step(10000);
    expect(render).toHaveBeenCalledTimes(2);
    motion.setActive(true);
    clock.step(10040);
    expect(render).toHaveBeenLastCalledWith(0.04);
    motion.dispose();
  });

  it("连续尺寸变化也不突破每秒 30 帧预算", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setActive(true);
    clock.step(0);
    for (const timestamp of [8, 16, 24, 32, 40]) {
      motion.invalidate();
      clock.step(timestamp);
    }
    expect(render).toHaveBeenCalledTimes(2);
    motion.dispose();
  });

  it("减少动态只绘制一帧，尺寸改变才再次绘制", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setAnimated(false);
    motion.setActive(true);
    clock.step(0);
    expect(clock.pending()).toBe(0);
    motion.invalidate();
    clock.step(100);
    expect(render.mock.calls).toEqual([[0], [0]]);
    expect(clock.pending()).toBe(0);
    motion.dispose();
  });

  it("手动暂停保留当前帧，继续播放不重复创建动画循环", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setActive(true);
    clock.step(0);
    motion.setAnimated(false);
    expect(clock.pending()).toBe(0);
    motion.setAnimated(true);
    motion.setAnimated(true);
    motion.setActive(true);
    expect(clock.pending()).toBe(1);
    clock.step(1000);
    expect(render).toHaveBeenLastCalledWith(0);
    motion.dispose();
  });

  it("卸载后取消帧，后续可见性与尺寸事件不能重启", () => {
    const clock = frameClock();
    const render = vi.fn();
    const motion = createPresenceMotion(render, clock);
    motion.setActive(true);
    motion.dispose();
    motion.setActive(true);
    motion.setAnimated(true);
    motion.invalidate();
    clock.step(0);
    expect(render).not.toHaveBeenCalled();
    expect(clock.pending()).toBe(0);
  });
});

describe("AI 核心的 WebGL 资源", () => {
  it("使用透明低功耗 WebGL2，限制尺寸且每帧只发出一次绘制", () => {
    const { gl, canvas, context } = glFixture();
    const renderer = createPresenceRenderer(canvas);
    expect(context).toHaveBeenCalledWith(
      "webgl2",
      expect.objectContaining({
        alpha: true,
        powerPreference: "low-power",
        depth: false,
      }),
    );
    renderer.resize(800, 400, 3);
    renderer.render(2);
    expect([canvas.width, canvas.height]).toEqual([600, 300]);
    expect(gl.viewport).toHaveBeenCalledWith(0, 0, 600, 300);
    expect(gl.drawArrays).toHaveBeenCalledExactlyOnceWith(gl.TRIANGLES, 0, 3);
    const source = gl.shaderSource.mock.calls[1]?.[1] as string;
    expect(source.startsWith("#version 300 es")).toBe(true);
    expect(source).toContain("i < 56");
    renderer.dispose();
  });

  it("不支持 WebGL2 时将失败交给组件的静态降级", () => {
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(null);
    expect(() => createPresenceRenderer(canvas)).toThrow(
      "当前设备不支持 WebGL2",
    );
  });

  it("编译失败清理已创建的着色器", () => {
    const { gl, canvas } = glFixture({ compile: false });
    expect(() => createPresenceRenderer(canvas)).toThrow("编译失败");
    expect(gl.deleteShader).toHaveBeenCalledTimes(1);
    expect(gl.createProgram).not.toHaveBeenCalled();
  });

  it("链接失败清理全部已分配资源", () => {
    const { gl, canvas } = glFixture({ link: false });
    expect(() => createPresenceRenderer(canvas)).toThrow("链接失败");
    expect(gl.deleteShader).toHaveBeenCalledTimes(2);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    expect(gl.deleteVertexArray).toHaveBeenCalledTimes(1);
  });

  it("上下文丢失时不继续绘制", () => {
    const { gl, canvas } = glFixture({ lost: true });
    const renderer = createPresenceRenderer(canvas);
    renderer.render(0);
    expect(gl.drawArrays).not.toHaveBeenCalled();
    renderer.dispose();
  });

  it("多次卸载只清理一次，卸载后不再访问绘制资源", () => {
    const { gl, canvas } = glFixture();
    const renderer = createPresenceRenderer(canvas);
    renderer.dispose();
    renderer.dispose();
    renderer.resize(100, 100, 1);
    renderer.render(1);
    expect(gl.deleteShader).toHaveBeenCalledTimes(2);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    expect(gl.deleteVertexArray).toHaveBeenCalledTimes(1);
    expect(gl.drawArrays).not.toHaveBeenCalled();
  });
});
