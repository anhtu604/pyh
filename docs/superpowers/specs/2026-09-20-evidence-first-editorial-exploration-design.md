# Evidence-first editorial exploration

**Date:** 2026-09-20  
**Status:** proposed — concept approved; implementation awaits review of this specification

## Decision

After topic selection, the system must research and validate enough context to support a safe editorial conversation. It presents what is supported, uncertain, and risky, plus two or three possible angles. The doctor then expresses a personal editorial view. Only then may an author brief be confirmed and the existing full evidence workflow begin.

This informs the doctor; it never chooses the doctor’s medical position, writes a script, or satisfies a review gate. It supersedes the prior brief-before-research ordering where the two conflict. Medical and video gates remain unchanged.

## Main-path state change

```text
idea -> topic_selected -> orientation_research_in_progress
     -> awaiting_editorial_direction -> author_brief_ready
     -> research_in_progress -> evidence_ready -> draft_ready
     -> awaiting_medical_review -> medically_approved
     -> production_in_progress -> awaiting_video_review
     -> video_approved -> packaged -> published_manual
```

`orientation_research_in_progress` is resumable work. `awaiting_editorial_direction` is the new human boundary. After this design is implemented, direct `topic_selected -> author_brief_ready` is forbidden. Existing side states and resume targets stay unchanged.

The orientation run may advance only after its artifact validates. If sources are insufficient, inaccessible, or invalid, the state remains resumable and records the precise failure; it never rejects the topic or invents a conclusion.

## Artifact and source boundary

Each revision gains an orientation workspace:

```text
revisions/<revision>/orientation/
├── scope.yaml
├── search-log.yaml
├── candidates.jsonl
├── included-sources.yaml
├── excluded-sources.yaml
└── editorial-orientation.yaml
```

No copyrighted full text, credentials, audio, cache, or render is stored. Candidates are not evidence. A source enters `included-sources` only through an explicit validator that proves it is a selected candidate with a stable identity, provenance, and permitted access. Source IDs in the orientation must resolve to included sources from the same revision and run. DOI, PMID, numerical result, and quotation fields are validated or omitted—never guessed from a search result or a topic sheet.

`editorial-orientation.yaml` contains the topic question, intended audience, scope/exclusions, source-backed context points with limitations, unresolved questions, communication risks, and two or three editorial options. Each option holds a neutral frame, linked context where applicable, and questions for the doctor. Provenance distinguishes source-backed context from editorial suggestion.

It cannot contain a doctor position, medical recommendation, claim ledger, script, storyboard direction, approval, or publish instruction.

The fixed files above are retryable working outputs, not immutable history. Each
attempt additionally writes an append-only stage manifest and a run-scoped,
content-addressed completed orientation record. Only the completed record named
by the latest successful stage manifest is authoritative. A failed or partial
attempt cannot replace it. This preserves idempotent retry without treating a
mutable search log as immutable evidence.

## Transition contracts and failure handling

`topic_selected -> orientation_research_in_progress` requires the selected topic
card and a SHA-256 hash of its canonical content plus the canonical requested
orientation scope. `orientation_research_in_progress ->
awaiting_editorial_direction` requires the validated, run-scoped completed
orientation record and its output hash; validation binds the active revision,
topic/scope input hash, included-source identities, and the editorial-orientation
file. `awaiting_editorial_direction -> author_brief_ready` requires that same
validated orientation record plus the existing confirmed author brief and its
input hash.

An unconfirmed brief may be saved while awaiting editorial direction but cannot
advance state. Confirmation succeeds only from `awaiting_editorial_direction`;
confirmation from `topic_selected` is rejected after rollout.

Provider failures are recorded individually with provider, query/run identifier,
failure class, and safe error summary. They are distinct from a successful
zero-result search. A failed orientation attempt remains in
`orientation_research_in_progress` with its failed stage record and may retry.
The ordinary `blocked` side state may be entered only through an explicit
state-graph rule that preserves this state as its resume target. Partial,
stale, cross-revision, or invalid orientation output never reaches
`awaiting_editorial_direction`.

## Conversation contract

At `awaiting_editorial_direction`, the coordinator presents: (1) verified findings and limits, (2) unknowns or statements that are unsafe to make confidently, (3) communication risks and two or three distinct angles, then (4) an invitation for the doctor to state, revise, or reject an angle in their own words.

The assistant may make editorial suggestions only when labelled as such. It must not portray them as doctor experience or judgment. It asks for the doctor’s intended message, audience, and safe action before saving an unconfirmed author brief. Existing explicit brief confirmation remains the only transition to `author_brief_ready`.

ChatGPT/Codex may inspect artifacts, propose corrections, and flag source or communication gaps. Neither can confirm the author brief, medical gate, video gate, or publication on the doctor’s behalf.

## Coordinator behavior

| State | Visible next action | Stop condition |
| --- | --- | --- |
| `topic_selected` | Research and validate orientation sources | validated artifact or reported source failure |
| `orientation_research_in_progress` | Resume orientation research | the same |
| `awaiting_editorial_direction` | Discuss orientation and capture the doctor’s view | unconfirmed author brief |
| `author_brief_ready` | Start full evidence workflow | existing behavior |

The future orientation command is idempotent for unchanged inputs and hashes, and records a stage manifest under the existing immutable convention. It does not automatically promote preliminary sources into the later claim ledger; full research re-evaluates relevance and support for every claim.

## Compatibility and safety

No v1 project changes. Existing v2 projects at `author_brief_ready` or later continue unchanged. A v2 project at `topic_selected` becomes eligible for orientation research; nothing is automatically written and no revision is silently created. Schema remains v2 unless a later plan proves a versioned schema change necessary, in which case a migration plan and tests must precede coding.

The current “Men gan tăng và tự dùng thuốc bổ gan” project remains `topic_selected` until implementation is approved and deliberately run. Its Google Sheet is a topic signal, not verified evidence.

- The doctor authors/confirms the brief; orientation cannot substitute for it.
- The full evidence ledger remains mandatory before drafting; both review gates remain mandatory.
- No automatic publication is introduced.
- Insufficient evidence produces a limitation and a request to narrow, defer, or change the topic—not an inferred claim.

## Implementation acceptance tests

1. Reject direct `topic_selected -> author_brief_ready`; accept only the ordered transitions with required artifacts and canonical input/output hashes.
2. Reject unresolved/guessed/malformed source IDs, absent provenance, duplicate IDs, and fields impersonating doctor decisions or approvals.
3. Show orientation research at topic selection and request editorial direction only at the new human boundary.
4. Refuse full evidence/claim-ledger work before a confirmed author brief even if orientation sources exist.
5. With no suitable validated source, leave an actionable resumable failure record and make no unsupported transition; distinguish a zero-result provider from a provider error.
6. Preserve v1 and v2 behavior from `author_brief_ready` onward; adapt the v2 `topic_selected` fixture to the new action.
7. Reject stale output, changed topic/scope input, wrong active revision, partial files, cross-run IDs, and duplicate IDs before orientation becomes authoritative.
8. Prove side-state entry/exit (including `blocked`) is intentional for both new main states and medical/production revision routes remain unchanged.
9. Prove medical/video gate hashes and approval routes remain unaffected and orientation cannot publish.

## Review question

Before implementation, confirm this preserves doctor editorial agency, keeps orientation light rather than a duplicate full review, and is the intended route for the current topic.
