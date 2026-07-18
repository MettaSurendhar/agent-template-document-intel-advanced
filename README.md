# Document Intelligence Agent Template

[#document-intelligence-agent-template](#document-intelligence-agent-template)

A production-grade template for building a **team-scoped, citation-grounded document Q&A agent**. Includes RAG retrieval over AWS Bedrock Knowledge Bases, OpenSearch-backed metadata/audit, dual-mode JWT/Azure AD auth, and document ingestion with format conversion.

## Which tier do I need?

[#which-tier-do-i-need](#which-tier-do-i-need)

This is the **advanced** tier of the Document Intel Agent Template family — three tiers, same underlying concept, different scale:

| Tier                     | Use it when...                                                                                                                    | Link                                                                                                                       |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| POC                      | You're prototyping or demoing. Single-user, no auth, ChromaDB, minutes to first answer.                                           | [agent-template-document-intel-poc](https://github.com/MettaSurendhar/agent-template-document-intel-poc)                   |
| Intermediate             | You have real users needing isolation, want to compare FAISS vs. Chroma, and want an audit trail.                                 | [agent-template-document-intel-intermediate](https://github.com/MettaSurendhar/agent-template-document-intel-intermediate) |
| **Advanced (this repo)** | You're deploying for a real team/organization: multi-team isolation, SSO, compliance-grade audit, enterprise document conversion. | —                                                                                                                          |

Don't start here for a prototype — the AWS Bedrock Knowledge Base + OpenSearch cluster requirement is real infrastructure to stand up. Start at the POC or intermediate tier and move up when you actually hit their limits (see each tier's `CLAUDE.md` for exactly what those limits are).

## Who is this for?

[#who-is-this-for](#who-is-this-for)

This template is for developers building an **knowledge-retrieval agent** for a specific domain — HR policies, contracts, engineering specs, compliance docs, legacy system documentation, whatever your team's documents are. It assumes:

- You're comfortable with **Python + FastAPI**.
- You have (or can provision) an **AWS account** with Bedrock Knowledge Bases enabled, and an **OpenSearch** cluster.
- You want retrieval-augmented answers **grounded strictly in your own documents** — this template is deliberately not a general-purpose chatbot.

If you're new to RAG concepts, start by reading [`usage.md`](./usage.md) alongside the code — the `/agents/converse` flow is the best place to see retrieval, grounding, and citation in action.

## Table of Contents

[#table-of-contents](#table-of-contents)

| Section                       | Link                                                            |
| ----------------------------- | --------------------------------------------------------------- |
| Overview                      | [Overview](#overview)                                           |
| Repo Structure                | [Repo Structure](#repo-structure)                               |
| Features                      | [Features](#features)                                           |
| Setup                         | [Setup](#setup)                                                 |
| Usage                         | [Usage](#usage)                                                 |
| Working with AI Coding Agents | [Working with AI Coding Agents](#working-with-ai-coding-agents) |
| Creating a Good README        | [Creating a Good README](#creating-a-good-readme)               |
| Contribution                  | [Contribution](#contribution)                                   |
| License                       | [License](#license)                                             |

---

## Overview

[#overview](#overview)

This repo provides a working FastAPI backend for a document-intelligence agent: upload documents → they're converted, stored in S3, and indexed into a Bedrock Knowledge Base → users ask questions scoped to their team's documents → the agent retrieves relevant chunks, generates a context-bound answer with citations, and logs everything to an audit trail.

It's built to be **forked and re-themed** for a new document domain, not run as-is for a generic use case.

## Repo Structure

[#repo-structure](#repo-structure)

For detailed information on each folder, see its own README:

- **[api/client](./api/client/README.md):** Wrappers around external AI services (Amazon Bedrock retrieve + generate).
- **[api/exceptions](./api/exceptions/README.md):** The single error-handling pattern (`APIException` + `ErrorCode` enum) used across the whole API.
- **[api/middleware](./api/middleware/README.md):** Dual-mode JWT/Azure AD auth middleware and team resolution.
- **[api/routers](./api/routers/README.md):** One file per resource — auth, teams, users, documents, agents, emails, audit.
- **[api/schemas](./api/schemas/README.md):** Pydantic request/response models.
- **[api/templates](./api/templates/README.md):** Jinja2 HTML email templates.
- **[api/types](./api/types/README.md):** Shared generic/request/response building blocks for complex resources.
- **[api/utils](./api/utils/README.md):** OpenSearch client, Bedrock KB helpers, email sending, logging.

## Features

[#features](#features)

- **Retrieval-Augmented Generation** over AWS Bedrock Knowledge Bases, filtered per-team by document S3 URI. 🔍
- **Context-bound generation**: the LLM is prompted to answer _only_ from retrieved chunks and return a `__NO_CONTEXT__` sentinel when it can't — no silent hallucination. 🛡️
- **Citation enrichment**: every answer comes back with the source documents, tags, and upload metadata attached. 📎
- **Dual-mode authentication**: local JWT (HS256) for dev/service accounts, Azure AD SSO (RS256 via JWKS) for production — validated by one middleware. 🔐
- **Full audit trail**: every query, response, and document action is logged to OpenSearch. 🧾
- **Document ingestion pipeline**: upload → format conversion (docx/pptx/ppt → PDF via LibreOffice) → S3 storage → KB sync. 🗂️
- **Follow-up question suggestions** generated directly from retrieved chunks (single LLM call, no extra KB lookups). 💬
- **Centralized, typed error handling** via `APIException` + `ErrorCode` enum — no ad-hoc error strings. 🚨
- **Dockerized, uv-managed, pre-commit enforced**: ruff, pyright, gitleaks, mdformat, sqlfluff, shellcheck, checkmake, conventional-gitmoji commits. ✅

## Setup

[#setup](#setup)

New to this repo? Start with [`QUICKSTART.md`](./QUICKSTART.md) — a local OpenSearch via Docker Compose gets you `/ping`, auth, and most endpoints running in a few minutes, no cluster to provision.

For the full picture — provisioning a real Bedrock Knowledge Base, OpenSearch cluster, and Azure AD SSO for production — see [`setup.md`](./setup.md).

## Usage

[#usage](#usage)

See [`usage.md`](./usage.md) for example requests/responses against the running API, including the `/agents/converse` RAG flow end-to-end.

## Working with AI Coding Agents

[#working-with-ai-coding-agents](#working-with-ai-coding-agents)

This repo includes a [`CLAUDE.md`](./CLAUDE.md) describing its architecture, conventions, and a step-by-step checklist for forking this template into a new document-intelligence vertical. If you're using Claude Code (or another AI coding agent) to adapt this template, point it at `CLAUDE.md` first.

## Creating a Good README

[#creating-a-good-readme](#creating-a-good-readme)

When you fork this template for your own vertical, update this README to describe _your_ agent, not this one. See [`good-readme.md`](./good-readme.md) for guidance on what to keep, what to rewrite, and what makes a README actually useful to someone landing on your repo for the first time.

## Contribution

[#contribution](#contribution)

Contributions to improve the template itself (not a specific fork) are welcome:

- **Reporting Bugs**: open an issue.
- **Feature Requests**: suggest improvements to the shared scaffold.
- **Pull Requests**: fork, branch, and submit — see [`contributing.md`](./contributing.md).

## License

[#license](#license)

MIT — see [LICENSE](./LICENSE).

---

## [❤️ Sponsor Me](https://github.com/sponsors/MettaSurendhar)

Sponsoring helps sustain open-source template work like this one.

## [🌟 Star this Repository](#)

If this saved you a few days of RAG-plumbing boilerplate, a star helps others find it.
