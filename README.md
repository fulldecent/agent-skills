# William Entriken's agents skills

These are techniques my team uses to do their job.

## How to install

Here is how I install these skills because these are all my personal skills:

```sh
cd ~/Developer
git clone https://github.com/fulldecent/agent-skills.git
mkdir -p ~/.agents
ln -s ~/Developer/agent-skills/ ~/.agents/skills
```

You have a choice of how you may install:

- If you don't have your own skills, adopt my skills wholesale with the above approach.
- You may created your own skills repo, use a similar approach and curate my skills into your own repo.
- If you don't use a skills repo, you may copy/link individual skills into your `~/.agents/skills` directory.

## This folder is a symlink target

Other projects load these skills through `~/.agents/skills`. They must not write into this repository.

- invoke skill scripts by absolute path from the target project's working directory
- do not `cd` into this repo to "run the skill"
- project state (sqlite files, logs, screenshots, downloads) stays in the target project
- a relative `sqlite3 foo.db` after changing into this directory will create `foo.db` here. That is a bug in the calling skill. Delete the stray file and give that skill an absolute path under the target project

Site-specific browser playbooks that more than one project needs, such as Proton Mail, live in `web-browser/`. Do not copy them downstream.
