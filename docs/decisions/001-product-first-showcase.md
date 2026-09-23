# Decision: Lead with the Product

## Context

A technical reviewer needs to understand what the software does, run a reproducible example, and inspect its limits. Development conversations alone cannot establish product behavior.

## Decision

Lead with the research product, a runnable synthetic demonstration, and inspectable report artifacts. Present AI-assisted development as supporting engineering evidence with explicit acceptance boundaries. Keep the public interface focused on the command-line workflow; see [architecture](../architecture.md) and the illustrative synthetic [example report](../../reports/example/benchmark.md).

## Consequences

Public documents emphasize source provenance, deterministic checks, and honest limitations. Curated [AI case studies](../ai-assisted-development.md) link to tests and artifacts without publishing prompt transcripts, private planning material, or unsupported productivity claims. The product remains research software, not investment advice.

## Rejected alternatives

- An AI prompt diary: conversations do not replace runnable evidence and distract from the product.
- A full web application: hosting, accounts, and interface development expand scope without improving the current acceptance evidence.
