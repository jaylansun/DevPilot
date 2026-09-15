import MarkdownIt from "markdown-it";

// 模型输出和文档内容不可信：禁用原始 HTML、远程图片及自动链接。
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true });
markdown.disable("image");
const validateLink = markdown.validateLink.bind(markdown);
markdown.validateLink = (url: string) =>
  /^https?:\/\//i.test(url) && validateLink(url);
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet("target", "_blank");
  tokens[index]!.attrSet("rel", "noopener noreferrer");
  tokens[index]!.attrSet("referrerpolicy", "no-referrer");
  return renderer.renderToken(tokens, index, options);
};
// 消息中的标题从三级开始，不能覆盖页面自己的标题层级。
for (const rule of ["heading_open", "heading_close"]) {
  markdown.renderer.rules[rule] = (tokens, index, options, _env, renderer) => {
    const token = tokens[index]!;
    token.tag = `h${Math.min(6, Number(token.tag.slice(1)) + 2)}`;
    return renderer.renderToken(tokens, index, options);
  };
}

export function renderSafeMarkdown(content: string): string {
  return markdown.render(content);
}
