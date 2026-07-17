# Creating a Good README

[#creating-a-good-readme](#creating-a-good-readme)

When you fork this template for your own document-intelligence vertical, don't just change the title — rewrite the README so it describes *your* agent to someone who's never seen this template. Here's what to keep, what to rewrite, and what to avoid.

## Keep the shape, rewrite the content

The section structure (Overview → Who is this for → Repo Structure → Features → Setup → Usage → Contribution → License) works well because it answers questions in the order a new reader actually has them. Keep it. But every sentence under those headers should be about your agent, not this template.

**Bad** (just relabeling): *"A template for building document-intelligence agents, now called Contracts AI."*

**Good** (actually describes the fork): *"Contracts AI answers questions about your organization's active vendor contracts — payment terms, renewal dates, liability clauses — scoped per legal team, with every answer traceable back to the source clause."*

## Say what it's grounded in, specifically

Document-intelligence agents live or die on trust. Your README should say, in the Overview, exactly what document types the agent answers from (e.g. "signed vendor contracts and their amendments" not "documents"). This sets correct expectations before someone uploads the wrong thing and gets a confusing `__NO_CONTEXT__` response.

## Who is this for — be honest about prerequisites

Don't just copy this template's "who is this for" — update the AWS/OpenSearch/Azure AD assumptions if you've changed any of them, and add anything domain-specific (e.g. "you'll need read access to your contract management system's export").

## Repo Structure — keep links working

If you add or remove folders, update the Repo Structure section's links accordingly. A README that links to a folder README that no longer exists (or omits a new one) is worse than no links at all — it signals the docs aren't maintained.

## Features — lead with outcomes, not implementation

Compare:

- ❌ "Uses AWS Bedrock Knowledge Bases with OpenSearch metadata enrichment."
- ✅ "Get grounded answers about contract terms with a direct link back to the clause it came from — no guessing which contract 'seems' relevant."

Mention the implementation in `setup.md`, not the feature list.

## Don't remove the honesty about limitations

Keep a clear statement that the agent won't answer beyond what's in the ingested documents (the `__NO_CONTEXT__` behavior). This isn't a weakness to hide — it's the thing that makes the tool trustworthy for the people who'll actually rely on its answers.

## Checklist before you publish your fork's README

- [ ] Title, tagline, and Overview describe *your* domain, not "document intelligence" generically
- [ ] "Who is this for" reflects your actual auth/infra assumptions
- [ ] Repo Structure links all resolve
- [ ] Features list reads as outcomes a user cares about
- [ ] `setup.md` env var table matches your actual `.env.example`
- [ ] `usage.md` examples use realistic queries for your domain, not the generic spec-sheet example
- [ ] License section still correct
- [ ] You've removed or updated `CLAUDE.md` §6's checklist once you've actually completed it (it's a one-time migration guide, not a permanent fixture)
