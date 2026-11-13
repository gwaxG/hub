---
name: mr-description
description: Use when writing or filling a GitLab merge request description. Fill the team's MR template from the actual branch diff, accurately and concisely, so a human can scan it in under a minute.
---

# MR Description

Generate a concise GitLab merge request description from the actual branch diff.

Every factual claim must be supported by the diff, repository context,
verified tool output, or information explicitly provided by the user.

Prefer concise explanations of behavior and engineering decisions over
enumerating code changes.

If the repository contains `.gitlab/merge_request_templates/Default.md`,
use it. Otherwise, use `template.md` next to this skill.

Preserve the selected template's section headings and checkboxes.

## Steps

### 1. Gather facts

Use read-only Git commands.

- Determine the MR target branch from available GitLab metadata.
- Otherwise, inspect repository branches and conventions.
- Ask if the target branch is ambiguous.

Inspect:

- `git status --short`
- `git log --oneline <base>..HEAD`
- `git diff <base>...HEAD --stat`
- `git diff <base>...HEAD`

Inspect relevant files and surrounding code when necessary to understand
behavior, compatibility, or operational impact.

Use the merge base to identify changes introduced by the branch.

Do not silently include unrelated uncommitted changes.

Identify the ticket from the branch name, commit messages, or user input.
Do not invent ticket references.

### 2. Establish verification evidence

Distinguish:

- Tests added or modified in the diff.
- Tests actually executed and their results.
- CI results explicitly inspected.
- Environments explicitly tested.

Never infer successful execution from the existence of tests.

Do not execute tests unless requested.

### 3. Fill the template

Follow the section rules below.

Remove instructional HTML comments from the final output.

### 4. Output

Produce:

1. A conventional-commit-style title, maximum 72 characters.
2. The completed Markdown description.

Put both in a single code block, ready to paste into GitLab.

Do not create, update, or submit an MR remotely unless explicitly asked.

## Section rules

| Section | Rule |
|---|---|
| Why | 1–2 lines explaining the problem or goal, not the implementation. Reference the ticket or specification when available. |
| What changed | 2–6 concise bullets describing observable behavior. Explicitly mention relevant migrations, configuration changes, version bumps, and infrastructure changes. |
| How it was verified | Report tests added, commands actually executed, observed results, inspected CI results, and tested environments. If no verification evidence exists, write "Not verified". |
| Risk & rollback | Identify plausible failure modes, affected systems or users, observable symptoms, and recovery options. Distinguish verified rollback procedures from suggested ones. |
| Reviewer focus | Identify up to three areas requiring human judgment: complex logic, migrations, permissions, concurrency, public contracts, or architectural decisions. Otherwise write "Nothing special". |
| Authorship | Mark agent authorship only when supported by known information. Never mark human review as completed without explicit human confirmation. |

## Rules

- Truthfulness over completeness.
- Unknown information must remain unknown.
- Never fabricate tickets, tests, CI results, or deployment outcomes.
- Identify plausible technical risks without presenting speculation as fact.
- Do not claim rollback is safe without sufficient evidence.
- Describe behavioral changes rather than listing modified files.
- Do not restate the diff line by line.
- Avoid marketing language ("robust", "seamless", "powerful").
- Prefer short, specific statements.
- Scale descriptions to change complexity.
- A trivial change should not produce a lengthy description.
- Preserve the repository's MR template structure.
- Do not modify repository files.

## Internal libraries

For internal library packages such as:

- skcr-utils
- skcr-models
- data-provider-clients

Check:

- Whether a version bump is required by repository conventions.
- Whether dependency changes require updating `uv.lock`.
- Whether consumers need compatibility or migration considerations.

Mention relevant version and dependency changes in the description.

Flag missing required updates rather than silently assuming they exist.
