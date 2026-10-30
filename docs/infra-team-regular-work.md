---
repo: [devops]
mr: []
verified_at: 2026-10-29
---

# Infra team — what they do regularly (snapshot 2026-10-29)

Source: 833 GitLab MRs authored 2026-04-29 → 2026-10-29 in group `skillcorner`, plus #infrastructure / #infrastructure-requests on Slack. Re-run before trusting.

| Person | MRs | Main repos |
|---|---|---|
| Benjamin Kalfa | 482 | iamskcr 141, cognito-authent 79, skcr-darts 27, crossplane 24, argocd-configs 23, kueue 21 |
| Pierre Leroux | 197 | iamskcr 74, argocd/harbor 41, karpenter-nodepools 15, argocd-configs 12, airbyte 12 |
| Jean Lopin | 90 | iamskcr 26, salah 16, s3-shared-iac 13, runner-eks-private 8, cicd-deployment 5 |
| Paul Leroux | 64 | iamskcr 17, kube-monitoring 13, karpenter-nodepools 9, external-dns 5, loki 5 |

## Recurring (run-the-business)
- **IAM / access tickets** — `devops/awsidentity/iamskcr` is ~31% of all MRs (258). Per-person SSM/secret/S3/ECS RunTask/PassRole grants, CI roles for new Pulumi stacks, ESO/IRSA roles. Driven by #infrastructure-requests; also GitLab invites and API test accounts.
- **Cognito / SSO** (Benjamin) — new app clients per service, pool migration (customer/internal → unified `skillcorner` pool, JIT migration lambda), Envoy Gateway OIDC on internal tools.
- **Deploy/bump** — skcr-darts prod image bumps (~weekly), maldini-api image bumps, paulumi bumps in consumers.
- **Capacity & cost tuning** — Kueue CPU/GPU quotas, Karpenter nodepools (GPU sharing, timeslicing/MPS, consolidation), runner sizing (docker-large, BuildKit tiers), Harbor/Tempo memory; S3 versioning/size reviews.
- **Observability upkeep** (Paul, Pierre) — kube-monitoring KSM allowlists, Prometheus/Thanos/Loki fixes, Tempo datasource, alert routing to Slack.
- **Reviews** of other teams' infra MRs (s3-shared-iac, pulp-registry, …).

## Projects in the period
- Pulumi Cloud → self-managed S3 backend across repos (Jean, May–Jul; all).
- Harbor registry + pull-through for runners (Pierre).
- Rootless BuildKit runners, DinD removal, unprivileged runners (Paul → Jean).
- Crossplane spike + ADR 0004 (Benjamin).
- nginx/oauth2-proxy → Envoy Gateway + HTTPRoutes (Pierre, Benjamin).
- Dedicated RDS for mlflow/superset/darts + migration runbooks (Benjamin, Oct).
- ClickHouse operator/guardrails, GPU nodepools, ec2-factory, mcp-grafana, offboarding script.
