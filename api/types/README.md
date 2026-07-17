# api/types

[#api-types](#api-types)

Shared building blocks for resources whose request/response shapes are complex enough to benefit from a `generic` / `request` / `response` split, rather than living flat in `api/schemas`. Currently used for `auth`, `documents`, and `teams`.

## Structure per resource

```
api/types/<resource>/
├── __init__.py
├── generic.py     # Shared base fields/models used by both request and response
├── request.py     # Inbound payload shapes
└── response.py    # Outbound payload shapes
```

## When to use this instead of a flat `api/schemas/<resource>.py`

- The resource has enough shared structure between its request and response shapes that duplicating fields would be error-prone (e.g. auth tokens carrying claims that also appear in responses).
- The resource has multiple request/response variants that share a common core (e.g. documents: upload request vs. list response vs. sync-status response, all referencing the same underlying document shape).

For anything simpler — a single request model and a single response model with little overlap — keep it flat in `api/schemas/` instead. Don't split into `types/` prematurely; only do it once duplication actually shows up.

## Conventions

- `generic.py` should have zero dependencies on `request.py` or `response.py` — it's the shared foundation, not a grab-bag.
- Don't put business logic here — these are data shapes only. Validation constraints are fine (they belong to the shape); side effects don't.
