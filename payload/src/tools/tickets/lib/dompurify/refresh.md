# refreshing the vendored DOMPurify

The HTML sanitiser of the ticket viewer, which lives in `<CLI_DIR>/` (`src/tools/tickets/` or
`tools/tickets/`); this folder is `<CLI_DIR>/lib/dompurify/`. Every ticket body is rendered by marked and
then cleaned by DOMPurify before it touches the page. Served by `<CLI_DIR>/serve.py` as `/lib/purify.min.js`.
Nothing here is edited by hand. Update the pin below in the same change set as any refresh.

## what is pinned

| | |
|---|---|
| Library | DOMPurify 3.4.16 |
| File | `purify.min.js` - defines `window.DOMPurify` |
| Source | https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.4.16/purify.min.js |
| sha256 | `2c90a9b46d6463f26038a29b686e82bc91de01fdac9d5229e7cfe3b360134ea2` |
| sha512 (cdnjs SRI) | `flQmhkXNRQ3iUfvtdCobtpMjCb6kE+zLnTiAulAQJ3WykVfy84JvCMOo6vhwWXHTXjR25h9Zj+LyGFRWKjRoag==` - matched cdnjs's published SRI on download |
| Licence | `LICENSE`, from https://raw.githubusercontent.com/cure53/DOMPurify/3.4.16/LICENSE - cdnjs ships no licence file |
| Licence sha256 | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| Vendored | 2026-09-29 (download approved by the user for this library and marked only) |

## the licence choice

DOMPurify is dual-licensed, `MPL-2.0 OR Apache-2.0` (the header of `purify.min.js` says so). Upstream's
`LICENSE` file at this tag carries the **Apache-2.0** text only, so that is the licence this copy is taken
under.

## notes

- The viewer calls `DOMPurify.sanitize(html, { USE_PROFILE: { html: true } })` (`app.js`, `render_markdown`).
  Verified 2026-09-29 with a ticket body holding a `<script>`, an `onerror` handler, a `javascript:` link and
  an `<iframe>`: none survived and none ran. `serve.py` also sends `script-src 'self'`, so an inline script
  would be blocked even if one got through.
- Nothing compiles or links this file; it is sent only to the browser that opens the viewer.

## refreshing

As `../marked/refresh.md`: pick the version on cdnjs, check the sha512 against its SRI, take `LICENSE`
from the matching upstream tag, record both hashes above, then repeat the torture-ticket check.
