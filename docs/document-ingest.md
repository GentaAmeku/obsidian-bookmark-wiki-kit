# Document Ingest with MarkItDown

PDF、Excel、Word、PowerPoint などのファイル URL は MarkItDown で Markdown に変換してから Source Note 化できます。

## Supported Extensions

```txt
.pdf
.xlsx
.xls
.docx
.pptx
.csv
```

## Install

```sh
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py install-deps
```

## Flow

```txt
bookmark URL
↓
download file with size limit
↓
convert with MarkItDown
↓
write extracted markdown to assets/extracted/
↓
write summarized Source Note to sources/documents/
```

## Notes

- Source Note には全文を置かず、要約・要点・短い引用を置く。
- 変換済み Markdown は `assets/extracted/` に保存する。
- 元ファイルは default では vault に保存しない。
- スキャン PDF や画像中心のファイルは標準変換だけでは不十分な場合がある。
- OCR や Azure Document Intelligence は必要になってから検討する。
