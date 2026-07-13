# Upstream synchronization

## Remotes and recorded revisions

- `inkos-upstream`: `https://github.com/Narcooo/inkos.git`; recorded base `fd87b04c3fbac7ab6ebc1b022fa117ee8051825e`.
- `webnovel-writer-upstream`: `https://github.com/lingfengQAQ/webnovel-writer.git`; recorded base `59654ccaa17f240c5ae41fe51db9443284f8ca1f`.
- `origin` remains the Hybrid repository. Do not force-push an upstream branch over Hybrid history.

Configure with `git remote add inkos-upstream ...` and `git remote add webnovel-writer-upstream ...`; fetches are review inputs, never automatic merges. Update `hybrid/story-runtime/UPSTREAM_PROVENANCE.yml` for every adopted upstream change with source path, commit, license, target path, and modification summary.

## Evaluation workflow

1. Fetch without merging and compare the recorded base to the proposed upstream tag/commit.
2. Classify changes as product shell, Runtime contract, migration provenance, security, dependency, or irrelevant legacy authority path.
3. Reject changes that restore long-form writes outside Story Runtime or introduce an LLM dependency into deterministic tests.
4. Port the smallest coherent change on a dedicated branch. Preserve Hybrid contracts and migration checksums.
5. Run architecture gates, Python tests, InkOS typecheck/build/tests, migration fixtures, deterministic E2E, package smoke, license and SBOM generation.
6. Review `git diff` specifically for authority mode, fallback writes, project schema, licenses, generated lockfiles, and deleted Hybrid recovery behavior.
7. Record the new upstream commit only after the synchronized change is accepted.

Do not merge either upstream tree wholesale. Conflicts in `story-runtime`, Studio Runtime proxy/panel, authority gates, migration code, provenance, or release workflows require a Hybrid maintainer review.
