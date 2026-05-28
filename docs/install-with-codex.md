# Codex で初期設定する

## 1. repo を clone

```sh
git clone https://github.com/<owner>/obsidian-bookmark-wiki-kit.git
cd obsidian-bookmark-wiki-kit
```

## 2. Codex へ依頼

```txt
このリポジトリを使って Obsidian bookmark wiki を初期設定してください。
vault は ~/Documents/wiki-private、Chrome ブックマークフォルダは AI Inbox でお願いします。
```

## 3. Codex が実行する内容

```sh
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py install-skill
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py init-vault --root ~/Documents/wiki-private --bookmark-folder "AI Inbox"
```

必要なら Git 初期化も行います。

```sh
cd ~/Documents/wiki-private
git init
git add .
git commit -m "Initialize Obsidian bookmark wiki"
```

## 4. 以後の依頼例

```txt
AI Inbox のブックマークを取り込んで
```

```txt
この wiki から react compiler を検索して
```

```txt
今日の daily review を作って
```
