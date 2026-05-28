# AGENTS.md instructions for obsidian-bookmark-wiki-kit

常に日本語で回答してください。

このリポジトリは、Chrome ブックマークを入口にして Obsidian Markdown vault へ Source Note / Knowledge Note を作るための再利用キットです。

基本方針:

- 個人の vault データ、ブックマーク、ログ、Source Note はこの repo に入れない。
- Skill は `skills/obsidian-knowledge-base/` に内包する。
- 初期設定は Codex が `init-vault` と `install-skill` を実行して行う。
- ブックマークフォルダ名の推奨デフォルトは `AI Inbox`。ユーザー指定があれば `.obsidian-kb.json` に保存する。
- 共有 repo 内に `/Users/<name>/...` のような個人パスをハードコードしない。
- X/Twitter 取得は Hermes helper がある場合だけ使い、なければ metadata note として保存する。
- YouTube は `yt-dlp` がある場合 transcript を試み、取れなければ `asr_required` にする。
