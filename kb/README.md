# Knowledge base

Markdown files with a front-matter header. Every `*.md` under this folder is indexed at startup
(or via `POST /api/v1/admin/kb/reindex`).

```
---
title: Human readable title (any script)
source_url: official page — shown to users as the citation
category: agriculture | women | health | education | ...
aliases: comma separated names in Latin AND Tamil script (also fed to Prisma word boosting)
languages: ta-IN, en-IN
---
# Section heading
Paragraph in Tamil.

Same paragraph in English.
```

**Data note:** the sample scheme documents are compiled from public government information for the
demo and contain no personal data. Amounts and rules change, so verify against the linked official
source before any real deployment, and keep `source_url` accurate.
