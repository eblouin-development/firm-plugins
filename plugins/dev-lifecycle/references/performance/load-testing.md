<!--
library: load-testing
versions-covered: "n/a (methodology, not a versioned library)"
last-verified: 2026-07-24
provenance: manual
sources: []
-->

# Load-test methodology

Load testing produces a capacity *estimate*, not a guarantee. Real traffic has a request mix, geography, and failure modes a synthetic script won't fully reproduce — report numbers as "observed under these conditions," not as a promised ceiling.

## Safety rules (non-negotiable)

- **Never target production, or any shared environment other users depend on, without explicit written sign-off from whoever owns it.** A load test is a self-inflicted denial-of-service if pointed at the wrong host.
- **Default target: local or a dedicated staging environment** that mirrors production sizing as closely as practical (same DB engine and rough data volume — a load test against an empty local DB tells you little about query performance at scale).
- **Never test third-party endpoints** (payment processors, email providers, partner APIs) — most providers treat unannounced load tests as abuse and may suspend the account. Mock or stub these in the test environment.
- **State the blast radius before running anything.** If there is any doubt about which environment a test will hit, stop and ask rather than firing requests.

## Method

1. **Establish a baseline.** Single-request latency (p50/p95/p99) for the endpoints under test, at rest, before adding concurrent load. Without this, a load-test number has no comparison point.
2. **Choose a realistic request mix.** Weight the test's request types by what production traffic actually looks like (from access logs or analytics if available) rather than hammering one endpoint uniformly — a read-heavy app tested with 100% writes measures the wrong thing.
3. **Ramp, don't spike.** Increase concurrent users/requests gradually and record latency and error rate at each step. The number that matters is where p95 latency or error rate crosses an unacceptable threshold — not the single highest number reached before the test tool itself became the bottleneck.
4. **Watch the resource, not just the client.** Correlate the load test with server-side metrics (CPU, memory, DB connections, queue depth) so the report can say *what* saturates first, not just *that* something did.
5. **Repeat, don't trust one run.** A single run can be skewed by a cold cache, a noisy neighbor, or a GC pause. Two or three runs, or note explicitly that only one run was feasible and the number is lower-confidence.

## Tooling

Use whatever the project already has configured; otherwise reach for a scriptable, open-source load generator appropriate to the stack (e.g. `k6`, `locust`, `autocannon`, `hey`) run from the operator's machine or CI against the target environment — never a hosted "attack" service pointed at a system you don't fully control.

## Reporting capacity numbers honestly

- State the environment the number came from (hardware/instance size, data volume, network) — the same number means something different on a laptop vs. a production-sized instance.
- State the request mix and ramp profile used.
- Give a range or a labeled ceiling ("held p95 < 300ms up to ~150 req/s in this environment; degraded past that"), not a bare single number presented as a guarantee.
- Flag anything that makes the estimate less trustworthy: empty/small test database, mocked downstream services, a single run, test environment undersized relative to production.
- If no load test could be run at all (no safe environment available, no tooling), say so plainly in the report's scope section rather than omitting the capacity question.
