# Operational design: {req} {title}

<!-- Filled by the design-ops-designer. "unchanged" is a valid answer for a line. -->

## Work to build
<!-- One line per log, metric, alert, setting or job that needs code, labelled OPS-1, OPS-2 ...: the task planner
must give each one a task, and `sdlc plan` checks that it did. "none" if nothing needs building. -->
- OPS-1:

## Deployment
<!-- Where it runs, what changes in the deployment (new service, env vars, config, jobs). A deployment diagram for new infrastructure. -->

## Configuration and secrets
| Setting | Default | Secret? | Where set |
| --- | --- | --- | --- |

## Observability
- Logs: <!-- events and fields, levels, no personal data or secrets -->
- Metrics: <!-- RED/USE: rate, errors, duration; business metrics from the spec's success metrics -->
- Traces:
- Dashboards and alerts: <!-- alert, threshold, who is paged, runbook link -->

## Performance and scaling
<!-- Expected load, the spec's NFR targets, bottlenecks, caching, how it scales. -->

## Reliability and recovery
- Failure modes and behaviour:
- Backups and restore:
- Recovery objectives (RPO / RTO):
- Runbook: <!-- the steps on-call follows -->
