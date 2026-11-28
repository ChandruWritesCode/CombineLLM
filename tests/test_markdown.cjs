const test = require("node:test");
const assert = require("node:assert/strict");
const markdownit = require("../app/static/vendor/markdown-it.umd.min.js");
const { createMarkdownRenderer } = require("../app/static/markdown.js");
const render = createMarkdownRenderer(markdownit);

test("renders useful response markup and escaped code", () => {
  const html = render("## Answer\n\n- one\n- two\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```js\nconst x = '<script>';\n```");
  assert.match(html, /<h2>Answer<\/h2>/);
  assert.match(html, /<li>one<\/li>/);
  assert.match(html, /<table>/);
  assert.match(html, /class="copy-code"/);
  assert.match(html, /&lt;script&gt;/);
});

test("does not execute HTML or load remote images", () => {
  const html = render('<img src=x onerror=alert(1)>\n\n![private](https://example.com/pixel)');
  assert.doesNotMatch(html, /<img\b/i);
  assert.match(html, /&lt;img/);
  assert.match(html, /private/);
});

test("allows safe external links and blocks script links", () => {
  const html = render("[site](https://example.com) [bad](javascript:alert%281%29)");
  assert.match(html, /href="https:\/\/example.com"/);
  assert.match(html, /rel="noopener noreferrer nofollow"/);
  assert.doesNotMatch(html, /href="javascript:/i);
});
