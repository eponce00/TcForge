# Maintaining this site

The site uses Material for MkDocs and the Markdown files in `docs/`.
Navigation and theme settings live in `mkdocs.yml` at the repository root.

## Preview locally

From the repository root, create a separate Python environment:

```powershell
python -m venv .venv-docs
.venv-docs\Scripts\python -m pip install -r requirements-docs.txt
.venv-docs\Scripts\python -m mkdocs serve
```

Open the local address printed by MkDocs. Changes to the documentation reload
automatically. On Linux or macOS, use `.venv-docs/bin/python` instead.

## Validate changes

```powershell
.venv-docs\Scripts\python -m mkdocs build --strict
```

The generated website is written to `site/`, which is excluded from Git.
Broken internal links, missing navigation pages, and invalid anchors fail the
build. Link to another guide using its relative `.md` path; use a full GitHub URL
when linking to source files outside `docs/`.

When adding a guide, add it to the `nav` section in `mkdocs.yml`.

## Publish with GitHub Pages

In the repository's **Settings → Pages**, select **GitHub Actions** as the source.
The `Documentation` workflow builds pull requests and publishes successful builds
from `main`. It can also be run manually from the Actions tab on `main`.
Pull requests and other branches cannot run its deployment job.

The published address is <https://eponce00.github.io/TcForge/>.
No personal access token or custom domain is required by the workflow. GitHub
provides the job-scoped deployment token through Actions.

To change the domain later, configure it in Pages settings and update `site_url`
in `mkdocs.yml` to match.
