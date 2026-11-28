"use strict";
// Local Markdown rendering. Provider text is untrusted: no raw HTML or remote images.
function createMarkdownRenderer(markdownit) {
  const markdown = markdownit({ html: false, linkify: false, breaks: true, typographer: false });
  markdown.validateLink = (value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:";
    } catch { return false; }
  };
  const originalLinkOpen = markdown.renderer.rules.link_open || ((tokens, index, options, env, self) => self.renderToken(tokens, index, options));
  markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
    tokens[index].attrSet("target", "_blank");
    tokens[index].attrSet("rel", "noopener noreferrer nofollow");
    return originalLinkOpen(tokens, index, options, env, self);
  };
  markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index].content);
  function code(content, info) {
    const language = (info || "").trim().split(/\s+/)[0].slice(0, 30);
    return `<div class="code-block"><div class="code-head"><span>${markdown.utils.escapeHtml(language || "Code")}</span><button class="copy-code" type="button">Copy code</button></div><pre><code>${markdown.utils.escapeHtml(content)}</code></pre></div>`;
  }
  markdown.renderer.rules.fence = (tokens, index) => code(tokens[index].content, tokens[index].info);
  markdown.renderer.rules.code_block = (tokens, index) => code(tokens[index].content, "");
  return (source) => markdown.render(source);
}
const renderMarkdown = typeof window !== "undefined" && window.markdownit
  ? createMarkdownRenderer(window.markdownit)
  : null;
if (typeof module !== "undefined") module.exports = { createMarkdownRenderer };
