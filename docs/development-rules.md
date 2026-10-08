# Development Rules — SearchOps MCP

## Branch Governance

- Development happens on bounded feature/refactor branches
- `main` represents the current stable integrated state
- Branches are created only when needed, never batch-created upfront
- Each milestone is separately authorized — never auto-continue to the next

## Session Protocol

1. Verify current branch with `git branch --show-current`
2. Read `IMPLEMENTATION_STATUS.md`
3. Implement only the approved milestone scope
4. Run tests before and after changes
5. Update `IMPLEMENTATION_STATUS.md`
6. Stop at milestone boundary

## Code Principles

- Evolve in-place, never rebuild from scratch
- Preserve working upstream functionality
- No internal LLM dependency — deterministic analysis first
- Keep MCP tool surface compact and high-level
- Token efficiency is a first-class requirement

## Testing Requirements

- New functionality requires unit tests
- Test with fixtures, not live APIs
- E2E tests validate full server subprocess
- All existing tests must continue passing

## Git Rules

- No AI attribution in commits (no Co-Authored-By, no generated-by trailers)
- Commit authorship remains the repository owner's Git identity
- One milestone per branch
