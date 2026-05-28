# Multiple Vaults

用途が違う情報は vault を分けることを推奨します。

例:

```txt
wiki-private/
wiki-work/
wiki-research/
```

それぞれに `.obsidian-kb.json` を置きます。

```json
{
  "bookmark_folder": "AI Inbox",
  "chrome_profile": "Profile 1",
  "language": "ja"
}
```

仕事用と個人用で Google アカウントを分ける場合は、Chrome profile も分けて `chrome_profile` を固定してください。
