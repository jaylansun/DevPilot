import { describe, expect, it } from "vitest";
import { renderSafeMarkdown } from "../../src/utils/safe_markdown";

describe("安全的回答排版", () => {
  it("保留列表、加粗、代码及引用编号，消息标题不占用页面一级标题", () => {
    const html = renderSafeMarkdown("# 计划\n\n**目标** [1]\n\n- 编写接口\n\n```js\nconst value = 1;\n```");
    expect(html).toContain("<h3>计划</h3>");
    expect(html).toContain("<strong>目标</strong> [1]");
    expect(html).toContain("<li>编写接口</li>");
    expect(html).toContain("<pre><code");
  });

  it("原始HTML只作为文本显示，不加载Markdown图片", () => {
    const html = renderSafeMarkdown('<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n![跟踪](https://example.com/tracker.png)');
    expect(html).not.toMatch(/<(script|img|iframe)\b/i);
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;img");
  });

  it.each(["javascript:alert(1)", "data:text/html,evil", "file:///etc/passwd", "//example.com", "javascript&#58;alert(1)"])("拒绝危险或不明确的链接 %s", (url) => {
    expect(renderSafeMarkdown(`[链接](${url})`)).not.toContain("<a ");
  });

  it("允许明确的https链接，并限制新窗口和来源泄露", () => {
    const html = renderSafeMarkdown("[资料](https://example.com/docs)");
    expect(html).toContain('href="https://example.com/docs"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('referrerpolicy="no-referrer"');
  });
});
