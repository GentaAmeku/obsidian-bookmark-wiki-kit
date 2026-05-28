# Skill Development

Skill は repo 内に内包します。

```txt
skills/obsidian-knowledge-base/
├── SKILL.md
├── agents/openai.yaml
└── scripts/obsidian_kb.py
```

利用者環境へは `install-skill` でコピーします。

```sh
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py install-skill
```

配布 repo の Skill を更新した場合は、再度 `install-skill` してください。
