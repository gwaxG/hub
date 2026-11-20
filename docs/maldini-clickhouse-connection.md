---
repo: [maldini-api]
mr: []
verified_at: 2026-11-20
---

# Connect to maldini ClickHouse (prod)

maldini-api reads its ClickHouse settings from AWS, not from a fixed URL in code. Settings class: `ClickhouseSettings` in `maldini_api/settings.py`. Paths come from the Pires lookup (`/<env>/<project>/<field>`).

## Where the values live (eu-central-1)
- `HOST`: SSM parameter `/prod/clickhouse/HOST`. Value on 2026-11-20: `clickhouse.skillcorner.com`.
- `ADMIN_USER`: SSM parameter `/prod/clickhouse/ADMIN_USER`. Value on 2026-11-20: `admin`.
- `PASSWORD`: Secrets Manager secret `/prod/clickhouse/PASSWORD`. Present, about 40 characters. Not recorded here.

App settings: port 443, `secure=True`. The Pulumi role policy grants read on `/<env>/clickhouse/*` to the maldini role.

## Read the values (no password printed)
```bash
export AWS_PROFILE=Production.Skcr-Software-Common-Role
CH_HOST=$(aws ssm get-parameter --region eu-central-1 --name /prod/clickhouse/HOST --query Parameter.Value --output text)
CH_USER=$(aws ssm get-parameter --region eu-central-1 --name /prod/clickhouse/ADMIN_USER --query Parameter.Value --output text)
CH_PASS=$(aws secretsmanager get-secret-value --region eu-central-1 --secret-id /prod/clickhouse/PASSWORD --query SecretString --output text)
```

## Connect
```bash
clickhouse-client --host "$CH_HOST" --user "$CH_USER" --password "$CH_PASS" --secure --port 9440
```

## Open questions
- Not verified: an HTTPS request to `clickhouse.skillcorner.com` with these credentials. An automated check blocked it on 2026-11-20. The `public_host` used for wilson is a different hostname, `*.aws.clickhouse.cloud`. Check whether `clickhouse.skillcorner.com` is a proxy or an old name before relying on it.
- The SecretString may be JSON. If so, read `.password` with `jq`, as for the wilson secret.
- Access may be denied for the Common-Role profile. The maldini role is a different role.
- Do not record the password in notes or chat.
