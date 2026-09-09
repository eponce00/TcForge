# Contributing

Issues and focused pull requests are welcome.

## Before making a change

Read the [programming standards](docs/1-Programming-Standards.md) and [architecture guide](docs/2-Architecture.md) before changing library contracts.

For changes to public interfaces or architecture, open an issue describing the problem and proposed behavior first. Keep pull requests focused on one change and update the affected documentation and examples.

## Validation

Build the solution in TwinCAT XAE and run relevant PLC tests on a suitable test runtime. Record the TwinCAT build, target, and test results. If compilation or runtime testing was unavailable, state that explicitly; source review alone does not establish runtime qualification.

## Reporting an issue

Include a minimal reproduction, expected and actual behavior, relevant versions, and sanitized logs. Remove credentials, private project code, and sensitive machine or network details before posting.

## Pull requests

Explain the problem, the resulting behavior, and how you validated it. Call out compatibility changes and any validation that remains incomplete.
