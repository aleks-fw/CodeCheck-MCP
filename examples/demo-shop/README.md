# Demo shop

A small static site with deliberate bugs, for trying `audit_project`. `serve.py` serves it and adds an API endpoint
that always answers HTTP 500.

```bash
python serve.py 8765
```

Then run `audit_project` on `http://127.0.0.1:8765/` with `criticalSelectors: ["#checkout"]`.

| Page | Deliberate bug | Expected finding |
|---|---|---|
| `/` | none | no warnings or critical findings |
| `/errors.html` | `console.error`, uncaught `ReferenceError`, unhandled promise rejection | `console/error`, `console/uncaught-exception`, `console/unhandled-rejection` |
| `/media.html` | image without `alt`, missing image, missing script | `accessibility/image-alt`, `network/image-failed`, `network/script-failed` |
| `/api.html` | `fetch("/api/orders")` answers 500 | `network/api-5xx` |
| `/mobile.html` | 640 px table | `layout/horizontal-overflow` at 375 px |
| `/buttons.html` | `#checkout` has no handler; "Add to cart" works | `interaction/no-effect` (critical) for `#checkout` only |
| `/notitle.html` | no `<title>` | `seo/missing-title` |

Notices such as missing canonical, favicon, Open Graph, robots.txt and sitemap.xml are expected too: the demo does
not have them.
