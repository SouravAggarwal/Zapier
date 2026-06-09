---
name: validate-pr
description: >
  Use before every PR, merge to main, or after completing a feature or bugfix.
  Runs tests, lint, convention checks, and logical review in sequence — stops
  at the first failure so issues are fixed before review proceeds.
---

# validate-pr

Full pre-PR validation for the Deployment Tracker API. Runs four phases in order; **stop and report failures before proceeding to the next phase**.

---

## Phase 1 — Tests

```bash
python manage.py test
```

All tests must pass with zero errors or failures. If any fail:
- Show the full failure output
- Stop here — do not proceed to Phase 2
- Ask the user to fix the failures first

---

## Phase 2 — Lint & Debug Checks

**2a. Lint**

```bash
flake8 deployments/ config/
```

Must produce **zero output**. Any output is a failure. If violations exist:
- List every violation with file, line, and rule
- Stop here — do not proceed to Phase 3
- Ask the user to fix them first

**2b. Leftover debug statements**

```bash
grep -rn "print(" deployments/ config/ --include="*.py"
```

Must produce **zero output**. Any `print()` call is a failure — all logging must use the `deployments` logger. If any are found:
- List every match with file and line number
- Stop here — do not proceed to Phase 3
- Ask the user to remove them first

---

## Phase 3 — Convention Check

Get changed files:

```bash
git diff --name-only HEAD
```

For each `.py` file in `deployments/` or `config/`, apply the `code-quality` skill and flag deviations. Key things to check per file type:

| File type | Check |
|-----------|-------|
| Models | Field ordering, `db_index` on filtered fields, `__str__`, no `null=True` on strings |
| Serializers | Explicit `fields` list (no `"__all__"`), `validate_<field>` methods, `read_only_fields` set |
| Views | `APIView` subclass, `{"error": "..."}` shape on errors, `%s` logger format, no `get_object_or_404` |
| Tests | `cache.clear()` in `setUp()`, descriptive test names, `assertNumQueries` for cache hits |
| Settings | `os.environ.get(KEY, default)` pattern, no hardcoded secrets |
| Services | Type hints on `__init__` and public methods, no HTTP concepts (Request/Response) |

Report each deviation as: `path/to/file.py — [rule violated] — [line if known]`

---

## Phase 4 — Logical Review

For each changed file, review for correctness:

**HTTP & response shape**
- Status codes semantically correct (200 reads, 201 create, 400 bad input, 404 missing, 409 conflict, never 500 for user errors)
- Every response is one of the three defined shapes: list envelope, single resource, or `{"error": "..."}`

**Edge cases**
- Empty querysets return `[]`, not an error
- Missing/invalid query params handled with 400
- Nonexistent IDs return 404 with `{"error": "No deployment found with id '...'"}`

**ORM & data integrity**
- No N+1 queries (use `select_related` or annotations on querysets)
- Read-modify-write operations use `select_for_update()` inside `transaction.atomic()`
- New filtered fields have `db_index=True`

**Cache**
- PUT invalidates cache via `cache.delete(key)` inside the transaction
- Cache key follows pattern `deployment:{id}`

**Security**
- No raw SQL that could allow injection
- No internal stack traces or model internals in error messages
- Input validated at boundaries via serializer before hitting the DB

---

## Report Format

```
## validate-pr Results

### Phase 1 — Tests: PASS ✓  (or FAIL ✗ — stop here)
### Phase 2 — Lint: PASS ✓ / FAIL ✗  |  Debug statements: PASS ✓ / FAIL ✗  (stop on either failure)
### Phase 3 — Conventions: PASS ✓ / N issues found
  - deployments/views.py — using get_object_or_404 (not allowed in API views)
### Phase 4 — Logical Review: PASS ✓ / N findings
  - deployments/views.py [bug] — POST returns 200 instead of 201
  - deployments/views.py [warning] — no N+1 guard on new related field lookup
```

Severity: **bug** (must fix before merge) | **warning** (should fix, won't break)
