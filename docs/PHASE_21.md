# Phase 21: formatted chat and mobile layout

Chat now renders assistant Markdown locally: headings, emphasis, lists,
blockquotes, tables, links, inline code, and fenced code blocks. Every code
block has **Copy code**. Each completed answer has **Copy** for the original
text and **View source** to inspect the exact Markdown; switch back with
**Rendered view**. The saved transcript and exports still contain the original
provider text, so rendering does not alter conversation history.

The browser bundles `markdown-it` 15.0.3 with its MIT license in
`app/static/vendor/`; no CDN is needed at runtime. Rendering uses `html: false`,
allows only HTTP(S) links in new tabs, and shows image alt text instead of
loading remote images. Code is escaped before it reaches the page. Provider
responses remain untrusted text; do not enable raw HTML without a separate
sanitization design. This follows the [markdown-it safety guidance](https://github.com/markdown-it/markdown-it/blob/master/docs/safety.md).

The chat layout takes visual cues from the [Gemini app's expressive design](https://blog.google/innovation-and-ai/products/gemini-app/next-evolution-gemini-app/),
while retaining CombineLLM's own
branding and existing themes. User prompts sit in compact right-aligned
bubbles; answers have more reading space and a distinct assistant mark. The
composer remains at the bottom. On narrow screens, **Chats & pages** opens
the navigation only when needed. A **Latest message** button appears when
you scroll away from the end of a long conversation. Conversation export,
rename, delete, and API docs stay available under the narrow-screen actions
menu beside the chat title.

## Validation

The local Markdown tests cover formatted code, raw HTML escaping, blocked
script links, and remote-image suppression. Browser review checked an existing
saved Java answer with headings, numbered instructions, and copyable code.
All 108 isolated backend tests and three Markdown checks passed. Ruff lint
and format, JavaScript syntax, and Docker Compose configuration passed. The
rebuilt container became healthy. Browser review confirmed desktop and mobile
layout, mobile navigation, conversation actions, Markdown rendering, and the
source toggle. No new live provider request was made for this interface phase.
