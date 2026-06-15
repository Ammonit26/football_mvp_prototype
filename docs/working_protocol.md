# Project Working Protocol

This protocol is part of the football_mvp_prototype project workflow.

It exists to prevent repeated diagnostic loops and accidental scope drift during repository, Excel, and MVP-layer work.

## Core Rule

Finish the current block before moving to another block.

Do not switch from implementation or Git-fix work into design planning unless the current block is explicitly closed.

## User Manual Work

When the user reports a result of manual inspection or manual editing, treat it as the current working fact unless there is direct evidence that contradicts it.

Do not repeatedly ask the user to prove the same manual result.

Correct handling:

1. accept the reported manual state;
2. identify what repository state must change next;
3. move toward commit and push;
4. verify the final result.

## Verification-First Boundary

Verification-first does not mean verifying the same fact indefinitely.

It means:

1. verify the relevant fact once;
2. record the result as the current state;
3. continue from that state;
4. only re-check if there is a concrete contradiction.

## Excel Workflow

For Excel changes:

1. identify the full set of intended changes;
2. apply changes as a batch where possible;
3. verify the exact intended cells changed;
4. verify no unrelated scope was changed;
5. run the relevant audit script;
6. commit only canonical tracked files;
7. push.

Do not patch one cell at a time unless the user explicitly asks for that.

## Git Workflow

Before Git commands, state the purpose of the command.

Use `git status` only to answer repository-state questions such as:

- which tracked files changed;
- which files are untracked;
- what is staged;
- whether the working tree is clean.

Do not use `git status` to challenge a user-reported manual edit. If Git does not see a reported edit, frame the problem as:

`The edit exists locally, but it is not reflected in the tracked canonical file in this checkout.`

Then resolve canonical-file mismatch, not the design/content question again.

## File Identity

Canonical file identity is the tracked project file, not a visually similar file name.

For Excel libraries in this project, distinguish:

- tracked canonical Excel files;
- temporary local copies;
- generated reports;
- untracked outputs.

Do not assume that two files with the same or similar name have the same content.

## Scope Control

At the start of each work segment, state:

- current block;
- current objective;
- not-in-scope items.

At the end of each block, state:

- what changed;
- verification result;
- commit hash if committed;
- next unfinished block.

## Project Rule

A design or data decision is not complete until it is reflected in canonical project documentation or canonical project data and committed/pushed to the repository.
