# Token Efficiency — SearchOps MCP

Token efficiency is a first-class product requirement for both runtime and development.

## Runtime Token Targets

| Response Type | Target |
|---------------|--------|
| Simple tool | < 500 tokens |
| Standard summary | < 1,500 tokens |
| Site audit summary | < 3,000 tokens |
| Issue list | < 2,500 tokens |
| Single issue evidence | < 2,000 tokens |

Raw mode (`detail_level=raw`) is exempt from these targets.

## Design Principles

### Summary by Default
All potentially large tools default to summary responses.

### Progressive Disclosure
```
summary → issue list → specific issue → evidence → raw provider response
```

### Server-Side Aggregation
The MCP performs totals, sorting, ranking, filtering, grouping, threshold detection, and comparisons. Never send raw data to the agent for calculation.

### Pagination
Every potentially large list supports `limit`/`offset`. Default: 10-25 items.

### Omit Empty Fields
Avoid verbose null-heavy responses.

### Avoid Repeated Data
Do not repeatedly return identical URL metadata across nested responses.

## Development Token Targets

- Do not routinely inspect the entire repository
- Use `IMPLEMENTATION_STATUS.md` + relevant files instead of full scans
- Architecture decisions go in `docs/adr/` to avoid re-reasoning
