# Chrome Bookmarks

推奨フォルダ名は `AI Inbox` です。

```txt
Chrome Bookmarks
└── AI Inbox
    ├── https://example.com/article
    └── https://www.youtube.com/watch?v=...
    ├── https://example.com/report.pdf
    └── https://example.com/data.xlsx
```

スマホと PC で同じ Google アカウントの Chrome 同期を有効にすれば、スマホで追加した URL も PC 側の Chrome profile に同期されます。

CLI は macOS の Chrome bookmark file を読みます。

```txt
~/Library/Application Support/Google/Chrome/<Profile>/Bookmarks
```

複数 profile に同じ `AI Inbox` がある場合は、vault の `.obsidian-kb.json` で指定します。

```json
{
  "bookmark_folder": "AI Inbox",
  "chrome_profile": "Profile 1"
}
```
