# RC-2B1D2 Indirect Allocator-Bypass Call Graph

## Enforcement model

`check_architecture.py` still discovers every production Python file beneath the
Runtime root by default. It now also builds an AST symbol index and bounded call
graph. Resolution covers same-module calls, `self` methods, imported aliases,
method-name targets, helper re-exports at the call seam, and local callable aliases.

The diagnostic path is:

```text
public production entrypoint
  -> service/helper/adapter
  -> repository method or generic mutator
  -> forbidden revision write sink
```

Each failure reports entrypoint/call path, sink, file, symbol, line and reason.

## Mutation primitives

The scanner recognizes direct/augmented assignment, literal or locally resolvable
dynamic project-revision SQL, SQLAlchemy `.values(revision=...)`, named revision
mutators, dictionary-driven updates, column-name setters, generic project updates,
parameterized field names, and callable aliases. A neutral generic helper call is
not rejected unless its call supplies revision authority.

## Approved sinks

Only the exact `ProjectRevisionAllocator.execute` and `_ensure_lineage` symbols may
perform native allocation/CAS writes. The exact legacy import/replay boundary
symbols remain the ADR-RC2-007 limited-history exceptions. No directory or file is
allowlisted, and new production modules are scanned automatically.

## Evidence

The mutation suite blocks direct job/CLI/recovery/new-file writes, one-hop and
multi-hop repository paths, update-fields/set-column/dynamic-keyword/generic-SQL
helpers, import aliases, re-exports, local aliases, formatting variants and ORM
assignment. It permits the real allocator, a revision-neutral repository helper,
migration DDL data and test fixtures.
