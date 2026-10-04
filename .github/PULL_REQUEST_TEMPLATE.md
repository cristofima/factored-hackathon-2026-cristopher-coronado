## Purpose

<!-- What problem are we solving and why does this change exist? -->

## Changes by Scope

<!-- Describe relevant changes grouped by scope. Keep only scopes that apply. -->

- **Agent**:
- **Identity**:
- **Responses BFF**:
- **Frontend**:
- **Business API**:
- **Data**:
- **Evaluation/CI**:
- **Infra**:
- **Docs**:

## Type of Change

<!-- Mark all that apply. -->

- [ ] Feature (`feat`)
- [ ] Bug fix (`fix`)
- [ ] Refactor (`refactor`)
- [ ] Performance (`perf`)
- [ ] Tests (`test`)
- [ ] Documentation (`docs`)
- [ ] Build/Dependencies (`build`)
- [ ] CI (`ci`)
- [ ] Chore (`chore`)

## Compatibility and Risk

<!-- Mark one compatibility status only when supported by evidence or author
confirmation. Absence of ! or BREAKING CHANGE does not prove compatibility.
Describe affected contracts, routes, authentication/ownership, data migrations,
or deployment requirements, including mitigation or migration steps. -->

- [ ] Breaking change
- [ ] No breaking change confirmed
- [ ] Pending confirmation

<!-- Add relevant risks and limitations; do not infer "no risk" from commit history. -->

<!-- Please prefix your PR title with one of the following:
  * `feat`: A new feature
  * `fix`: A bug fix
  * `docs`: Documentation only changes
  * `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
  * `refactor`: A code change that neither fixes a bug nor adds a feature
  * `perf`: A code change that improves performance
  * `test`: Adding missing tests or correcting existing tests
  * `build`: Changes that affect the build system or external dependencies (example scopes: gulp, broccoli, npm)
  * `ci`: Changes to our CI configuration files and scripts (example scopes: Travis, Circle, BrowserStack, SauceLabs)
  * `chore`: Other changes that don't modify src or test files
  * `revert`: Reverts a previous commit
  * !: A breaking change is indicated with a `!` after the listed prefixes above, e.g. `feat!`, `fix!`, `refactor!`, etc.
-->

## Validation

<!-- Keep recommended checks separate from observed results. Commit messages,
historical memory, and test configuration are not execution evidence for this HEAD.
Use AGENTS.md and component guides for focused validation commands. -->

### Recommended Checks

<!-- List exact commands and manual scenarios relevant to the affected behavior.
These are instructions, not claims that checks were executed. -->

### Available Results

Validation evidence was not supplied for this draft.

<!-- Replace the sentence above only with verified results. For each result, record:
command/check | status | environment | tested commit | result or evidence link.
Include exact commands with their outcomes, warnings, and coverage limitations.
Statuses: Passed, Failed, Not run, Blocked, Evidence unavailable, Not applicable.
"Not run" requires knowledge that the check was not executed; otherwise use
"Evidence unavailable". Explain blocked checks and non-applicability.
Add manual checks, screenshots/recordings for relevant UI changes, and CI run or
artifact links here when available; do not add empty subsections or default to N/A.
Distinguish local, CI, and hosted results. Tests or protocol smoke do not establish
real-data parity, end-to-end authorization, or hosted identity transport.
Never include credentials, tokens, customer data, or links to local-only handoffs. -->

## Checklist

<!-- Author attestations: do not check these from commit-history inference. -->

- [ ] Tests were added or updated for changed behavior, or a clear coverage limitation is provided
- [ ] No secrets, passwords, tokens, or sensitive customer data were added to code/logs/config/evidence
- [ ] Documentation was updated when behavior or workflows changed

## Related Issues

<!-- Include explicit issue references from commit footers or supplied context.
Omit this section if none are available. -->

## Limitations and Follow-up

<!-- Include documented remaining verification gates, rollout requirements, or
reviewer-relevant limitations. Missing evidence does not close an existing gate.
Omit this section if no additional limitations are documented. -->
