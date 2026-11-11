# Contributing

Use Conventional Commits for changes, for example `fix(auth): restore pending paper after login`.
The accepted types and formatting rules are defined in `.commitlintrc.json`.

Pull requests are squash-merged using their title as the commit title. CI validates
that title with the same commitlint configuration. This lets a branch retain its
working and upstream integration history while ensuring the resulting main-branch
commit follows the convention. Edit the PR title to correct a failed title check;
do not rewrite published integration history to satisfy the check.

Direct pushes to `develop` and `master` still validate their individual commit
messages. Before merging a PR, wait for its functional checks and title check to
pass, and use the validated title for the squash commit.
