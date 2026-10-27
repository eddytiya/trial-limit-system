# Publish to GitHub from Windows CMD

These commands use Git and GitHub CLI (`gh`). Install both and reopen CMD if
either command is unavailable. The repository name below is `trial-limit-system`.

```cmd
cd /d "C:\Users\biswajit.das\Desktop\Trial limit System"
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Initial commit: Trial Limit System"
gh auth login
gh api user --jq .login
gh repo create eddytiya/trial-limit-system --private --source=. --remote=origin --push
```

During `gh auth login`, select GitHub.com, HTTPS, and browser authentication.
Confirm the displayed account is `eddytiya` before creating the repository.
The creation command creates a private repository and pushes the initial commit.
Review staged files before committing; `.gitignore` excludes local snapshots,
mapping records, generated reports, credentials, and Python caches.

If Git asks for your identity, set your own name and a GitHub-verified email
or your GitHub-provided no-reply email, then retry the commit:

```cmd
git config user.name "YOUR NAME"
git config user.email "YOUR VERIFIED OR GITHUB NO-REPLY EMAIL"
```

If you create an empty repository on the GitHub website instead, skip
`gh repo create` and run:

```cmd
git remote add origin https://github.com/eddytiya/trial-limit-system.git
git push -u origin main
```

For later updates:

```cmd
git add .
git diff --cached --stat
git commit -m "Describe your changes"
git push
```

Local data is intentionally absent from a fresh clone. Install
`app/requirements.txt`, start the dashboard, and upload the required exports.
For configured-file views, place the original files in `input/` and update
`app/config.json` paths. Restore authorized mapping records into `mapped/`
when using views that depend on approved mappings. Historical analysis scripts
may require private snapshots and machine-specific dependencies.
