"""Request matches, then resolve each one's Heimspiel MatchMatching.

Flow:
    1. List SkillCorner matches (public client `get_matches`).
    2. For each match id, call `get_match_matching(skillcorner_match_id=...)`.
       That endpoint returns ALL providers for the match (it has no provider
       filter), so we keep only the `heimspiel` entry ourselves.

Note: `/api/match_matchings/?matches=` (the provider-id -> skillcorner-id
direction) does NOT support heimspiel — its PROVIDERS set is hardcoded and
excludes it. The `skillcorner_match_id=` direction used here has no such
restriction, so it works.

Usage:
    SKILLCORNER_ENV=dev uv run server/../docs/heimspiel_match_matchings.py \
        --competition-edition 456
"""

from __future__ import annotations

import argparse

from skillcorner_private.client import SkillcornerPrivateClient

HEIMSPIEL = 'heimspiel'


def heimspiel_id_for_match(client: SkillcornerPrivateClient, match_id: int) -> str | None:
    """Return the Heimspiel provider_match_id for a match, or None if unmatched."""
    resp = client.get_match_matching(skillcorner_match_id=match_id)
    for matching in resp.get('match_matchings', []):
        if matching['provider'] == HEIMSPIEL:
            return matching['provider_match_id']
    return None


def collect(client: SkillcornerPrivateClient, **match_filters) -> dict[int, str]:
    """Map SkillCorner match id -> Heimspiel match id for matches that have one."""
    matches = client.get_matches(**match_filters)  # public client, paginates internally
    result = {}
    for match in matches:
        heimspiel_id = heimspiel_id_for_match(client, match['id'])
        if heimspiel_id is not None:
            result[match['id']] = heimspiel_id
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', default=None, help='SkillCorner env (defaults to $SKILLCORNER_ENV)')
    parser.add_argument('--competition-edition', type=int, action='append', dest='competition_edition')
    parser.add_argument('--competition', type=int, action='append')
    parser.add_argument('--season', type=int, action='append')
    args = parser.parse_args()

    filters = {k: v for k, v in vars(args).items() if k != 'env' and v is not None}

    client = SkillcornerPrivateClient(env=args.env)
    mapping = collect(client, **filters)

    for skcr_id, heimspiel_id in mapping.items():
        print(f'{skcr_id}\t{heimspiel_id}')
    print(f'\n{len(mapping)} matches with a Heimspiel matching.')


if __name__ == '__main__':
    main()
