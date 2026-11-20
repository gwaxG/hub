---
repo: [wilson]
mr: []
verified_at: 2026-11-20
---

# Connect to the physical ClickHouse (prod)

The public URL `clickhouse.skillcorner.com` does not exist. Connection details live in a secret.

## Steps
1. Read the secret `/prod/wilson/CLICKHOUSE_CREDS` in `eu-central-1`. Use the AWS profile `Production.Skcr-Software-Common-Role`. The default credentials fail with "Unable to locate credentials".
2. Use the `public_host` field from the secret. It is `q1myvoucxx.us-east-1.aws.clickhouse.cloud` as of 2026-11-20. The `host` field is a VPC endpoint (`...vpce.aws.clickhouse.cloud`) and is only reachable from inside the VPC, which is what wilson uses.
3. Connect over HTTPS on port 8443. Use the `user` and `password` fields from the same secret.
4. Database: `football`. Physical tables: `physical_3_0_2`, `physical_3_0_3` (plus `*_refresh`), `physical_4_0_0`, `physical_scope`. The `_new` names from older docs do not exist on this cluster (checked 2026-11-20). Use SELECT only.

## Check with curl
Read the secret into shell variables so the password is never printed:

```bash
export AWS_PROFILE=Production.Skcr-Software-Common-Role
SECRET=$(aws secretsmanager get-secret-value --region eu-central-1 --secret-id /prod/wilson/CLICKHOUSE_CREDS --query SecretString --output text)
CH_HOST=$(echo "$SECRET" | jq -r .public_host)
CH_USER=$(echo "$SECRET" | jq -r .user)
CH_PASS=$(echo "$SECRET" | jq -r .password)
curl -s "https://$CH_HOST:8443/" -u "$CH_USER:$CH_PASS" --data-binary "SELECT version()"
```

## Traps
- The wilson client (`server/phys_clickhouse/client.py`) reads the `host` field, not `public_host`. That works only inside the VPC. From a laptop, use `public_host`.
- The field names in [physical-v4-icebergkamp-flow.md](physical-v4-icebergkamp-flow.md) match the secret, but its hostname is not written down. Do not hard-code the hostname. Read it from the secret.
- Non-prod environments fall back to dev credentials (`settings_base.py`). Only prod and dev clusters exist.
- Do not record the password in notes or chat.
