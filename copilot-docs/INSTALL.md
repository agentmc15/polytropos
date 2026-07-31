# Installing the Copilot CLI bundle

This guide covers installing this repository's Copilot CLI skills and agents, what gets
copied where, and how to find them once installed.

## Install preview and install commands

Preview what an install would do without writing anything:

```bash
python3 bin/harness_select.py install --harness copilot --dry-run
```

Run the real install:

```bash
python3 bin/harness_select.py install --harness copilot
```

### Optional `--copilot-home DIR`

By default the installer targets the Copilot CLI's own home directory. Pass
`--copilot-home DIR` to target a different directory instead — useful for trying the
bundle in an isolated location before installing it into your real Copilot home.

## What is copied

The install copies two kinds of files:

- Every `*.agent.md` file under `copilot/.github/agents/` is copied to the Copilot home's `agents/` directory, keeping the same filename.
- Every file under `copilot/.github/skills/` is copied to the Copilot home's `skills/` directory, keeping the same relative path.

In both cases, every occurrence of the `{{POLYTROPOS_ROOT}}` placeholder in the
source text is replaced with this repository's own absolute path as the file is copied —
Copilot CLI has no `${CLAUDE_PLUGIN_ROOT}`-style variable to resolve a bundle's own
location at run time, so the placeholder has to become a literal path at install time
instead.

## In-session discovery

Once installed, use these commands inside a Copilot CLI session:

- `/skills reload` — picks up newly installed or changed skills without restarting the session.
- `/skills` — opens the skills management view, where installed skills can be toggled on or off.
- `/skills list` — lists every installed skill.
- `/skills info NAME` — shows one skill's frontmatter and source path (replace `NAME` with a skill's name).
- `/agent` — opens the agent picker to switch the session into one of the installed custom agents.

## Requesting a skill or agent explicitly

- **Explicit skill request:** type something like "Use the `/route` skill to pick a model for this task" in a prompt. A skill can also auto-load on its own when a request's wording matches its `description:` frontmatter — but neither path makes `/route` a native, user-defined slash command; see [`SAFETY.md`](SAFETY.md) for the exact honesty around this.
- **Agent one-shot dispatch:** run `copilot --agent AGENT_NAME -p "TASK"`, or pick the agent from the `/agent` picker. `AGENT_NAME` and `TASK` are placeholders — substitute the installed agent's name and your own prompt text.

## Personal-agent precedence and stale copies

Copilot CLI reads custom agents from both a project's own `.github/agents/` and the
user-level Copilot home's `agents/` directory, and on a name collision the user-level
(home-dir) copy wins. If you already have a personal agent with the same name as one in
this bundle, installing this bundle will shadow it everywhere that Copilot home is active.
Conversely, if you edit a skill or agent in this repository, the copy already installed in
your Copilot home is now stale until you re-run the install.

## Troubleshooting: literal placeholder text

If a skill or agent shows the literal text `{{POLYTROPOS_ROOT}}` instead of a real
path, the installed copy predates a repository change, or it was installed by hand instead
of through `bin/harness_select.py`. Re-run the real install command above to refresh it;
the installer always resolves the placeholder as it copies each file.
