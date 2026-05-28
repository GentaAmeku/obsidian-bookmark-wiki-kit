# Obsidian Bookmark Wiki Kit

Chrome ブックマークを「AI に読ませたい URL キュー」として使い、Obsidian + Markdown に Source Note / Knowledge Note を蓄積するための再利用キットです。

この repo は vault そのものではなく、以下を配布します。

- Codex Skill: `skills/obsidian-knowledge-base/`
- vault 雛形: `vault-template/`
- 初期設定ドキュメント: `docs/`
- ローカル CLI: `obsidian_kb.py`

## 推奨する使い方

```sh
git clone https://github.com/GentaAmeku/obsidian-bookmark-wiki-kit.git
cd obsidian-bookmark-wiki-kit
```

その後、Codex に依頼します。

```txt
このリポジトリを使って Obsidian bookmark wiki を初期設定してください。
vault は ~/Documents/wiki-private、Chrome ブックマークフォルダは AI Inbox でお願いします。
```

Codex は概ね次を実行します。

```sh
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py install-skill
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py init-vault --root ~/Documents/wiki-private --bookmark-folder "AI Inbox"
```

## ブックマーク運用

Chrome のブックマークに `AI Inbox` フォルダを作り、Zenn、Qiita、YouTube など、AI に読ませたいデータ元サイトをブックマークします。

取り込みや検索は、ユーザーがコマンドを直接実行するのではなく、Codex Skill 経由で依頼する運用を推奨します。

ブックマーク取り込みの依頼例:

```txt
$obsidian-knowledge-base AI Inbox のブックマークを取り込んで
```

単一 URL 取り込みの依頼例:

```txt
$obsidian-knowledge-base このURLをSource Note化して: https://example.com/article
```

検索の依頼例:

```txt
$obsidian-knowledge-base この wiki から react compiler を検索して
```

CLI は Skill 内部で使う実行手段として同梱しています。必要な場合だけ手動実行できます。

## vault 設定

各 vault の `.obsidian-kb.json` で設定します。

```json
{
  "bookmark_folder": "AI Inbox",
  "chrome_profile": "",
  "language": "ja",
  "auto_commit": false,
  "auto_push": false,
  "x_provider": "hermes"
}
```

`chrome_profile` が空なら、全 Chrome profile から `bookmark_folder` を探します。複数 profile に同名フォルダがある場合は `chrome_profile` を指定してください。

## 状態

この kit はローカル filesystem + Codex Skill ベースです。MCP / vector DB / RAG はまだ必須にしていません。
