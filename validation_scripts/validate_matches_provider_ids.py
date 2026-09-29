# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Validate that /matches exposes impect_id and heimspiel_id on a deployed stack.

Ticket: Expose `impect_id` and `heimspiel_id` on the `/matches` endpoint.
Wilson MR: https://gitlab.com/skillcorner/software/wilson/-/merge_requests/2640

Before the fix, `matching=impect` and `matching=heimspiel` were silently ignored on
/matches: no error, and no id in the payload. The checks below, run against a live stack:

  1. `matching=impect` returns a populated `impect_id` on at least one match.
  2. `matching=heimspiel` returns a populated `heimspiel_id` on at least one match.
  3. Asking for both plus a pre-existing provider returns all three ids on one match.
  4. A provider that was not asked for stays out of the payload.

Competition edition 1659 is the default scope: it is the one the ticket uses as an
example, and it carries both providers.

Usage:
    WILSON_USER=... WILSON_PASSWORD=... \
        uv run validate_matches_provider_ids.py --base-url https://andrei.skillcorner.com
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import requests

DEFAULT_COMPETITION_EDITION = 1659
PAGE_SIZE = 200


class ValidationFailed(Exception):
    pass


@dataclass(frozen=True)
class MatchesEndpoint:
    base_url: str
    auth: tuple[str, str]
    competition_edition: int

    def list(self, matching: str) -> list[dict]:
        response = requests.get(
            f'{self.base_url}/api/matches/',
            params={
                'user': 'false',
                'matching': matching,
                'competition_edition': self.competition_edition,
                'limit': PAGE_SIZE,
            },
            auth=self.auth,
            timeout=120,
        )
        response.raise_for_status()
        results = response.json()['results']
        if not results:
            raise ValidationFailed(f'competition edition {self.competition_edition} returned no match at all')
        return results


def check_provider_id(endpoint: MatchesEndpoint, provider: str) -> tuple[int, str]:
    """`matching=<provider>` must expose a populated `<provider>_id`. Returns (match id, value)."""
    field = f'{provider}_id'
    matches = endpoint.list(provider)
    if field not in matches[0]:
        raise ValidationFailed(f'`matching={provider}` returned no `{field}` key — the field is not exposed')
    populated = [match for match in matches if match[field]]
    if not populated:
        raise ValidationFailed(f'`{field}` is exposed but null on all {len(matches)} matches scanned')
    match = populated[0]
    return match['id'], match[field]


def check_providers_together(endpoint: MatchesEndpoint, expected: dict[int, dict[str, str]]) -> int:
    """One request for three providers must return the same ids the single-provider ones did."""
    fields = ('impect_id', 'heimspiel_id', 'wyscout_id')
    for match in endpoint.list(','.join(field.removesuffix('_id') for field in fields)):
        if all(match.get(field) for field in fields):
            for field, value in expected.get(match['id'], {}).items():
                if match[field] != value:
                    raise ValidationFailed(
                        f'match {match["id"]}: combined request gave `{field}`={match[field]!r}, expected {value!r}'
                    )
            return match['id']
    raise ValidationFailed(f'no match carries all of {fields} in a single request')


def check_unrequested_ids_absent(endpoint: MatchesEndpoint) -> None:
    match = endpoint.list('wyscout')[0]
    leaked = [field for field in ('impect_id', 'heimspiel_id') if field in match]
    if leaked:
        raise ValidationFailed(f'`matching=wyscout` leaked fields that were not asked for: {leaked}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://andrei.skillcorner.com')
    parser.add_argument('--competition-edition', type=int, default=DEFAULT_COMPETITION_EDITION)
    args = parser.parse_args()

    user, password = os.environ.get('WILSON_USER'), os.environ.get('WILSON_PASSWORD')
    if not (user and password):
        print('WILSON_USER and WILSON_PASSWORD must be set', file=sys.stderr)
        return 2

    endpoint = MatchesEndpoint(
        base_url=args.base_url.rstrip('/'),
        auth=(user, password),
        competition_edition=args.competition_edition,
    )
    print(f'Validating {endpoint.base_url}/api/matches/ on competition edition {endpoint.competition_edition}')

    try:
        expected = {}
        for provider in ('impect', 'heimspiel'):
            match_id, provider_id = check_provider_id(endpoint, provider)
            expected.setdefault(match_id, {})[f'{provider}_id'] = provider_id
            print(f'  {provider + "_id":<14}✅  match {match_id} -> {provider_id}')

        combined_match_id = check_providers_together(endpoint, expected)
        print(f'  combined      ✅  impect + heimspiel + wyscout together on match {combined_match_id}')

        check_unrequested_ids_absent(endpoint)
        print('  scoping       ✅  unrequested provider ids stay out of the payload')
    except ValidationFailed as error:
        print(f'  ❌ {error}', file=sys.stderr)
        return 1

    print('All checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
