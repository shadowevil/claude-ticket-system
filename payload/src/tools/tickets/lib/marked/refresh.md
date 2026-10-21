# refreshing the vendored marked

The markdown renderer of the ticket viewer, which lives in `<CLI_DIR>/` (`src/tools/tickets/` or
`tools/tickets/`); this folder is `<CLI_DIR>/lib/marked/`. `<CLI_DIR>/serve.py` serves it to the browser as
`/lib/marked.min.js`. Nothing here is edited by hand, and nothing is built: the viewer has no build step.
Update the pin below in the same change set as any refresh.

## what is pinned

| | |
|---|---|
| Library | marked 18.0.14 (GitHub-flavoured markdown: tables, task lists, fenced code, autolinks) |
| File | `marked.umd.min.js` - the UMD build, so a plain `<script>` tag defines `window.marked` |
| Source | https://cdnjs.cloudflare.com/ajax/libs/marked/18.0.14/lib/marked.umd.min.js |
| sha256 | `e67a06aa3661785f8ab4ee803094651c04570630814df305b492decef588d905` |
| sha512 (cdnjs SRI) | `trN9mtGYvoySPVI909KTnwbJI9AkKPydRCV/qAsUG1+q39hhpKltEag9b5JpdjeIZn5i8IH62hHRFdbKwMFh9w==` - matched cdnjs's published SRI on download |
| Licence | `LICENSE` (MIT), from https://raw.githubusercontent.com/markedjs/marked/v18.0.14/LICENSE - cdnjs ships no licence file; upstream's canonical name is kept |
| Licence sha256 | `8e3a3f82f59a60958f56ca08f445647c32a4733dc7ca6c2c46f6eb898471ab9c` |
| Vendored | 2026-09-29 (download approved by the user for this library and DOMPurify only) |

## notes

- marked does **not** sanitise. The viewer always passes its output through DOMPurify (`../dompurify/`);
  never render marked's HTML without it.
- Nothing compiles or links this file; `serve.py`'s route table is its only consumer, and it is sent only to
  the browser that opens the viewer.

## refreshing

1. Pick the version (`https://api.cdnjs.com/libraries/marked?fields=version`), download
   `lib/marked.umd.min.js` from cdnjs and `LICENSE` from the matching upstream tag.
2. Check the file's sha512 against cdnjs's SRI (`https://api.cdnjs.com/libraries/marked/<version>?fields=sri`),
   record both hashes above.
3. Open the viewer and read a ticket with a table, a task list and a fenced block; `marked.parse` is the
   only call the viewer makes (`app.js`, `render_markdown`).
