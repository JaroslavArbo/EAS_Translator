# EAS Translator

Prototype web translation engine for European Arboricultural Standards. Current MVP is focused on the locked **Tree Planting Standard** workflow:

- previous source standard: `02-Planting.pdf`
- current source standard: `TREE PLANTING STANDARDS 2nd edition 2026 FINAL.pdf`
- segment-based translation editor
- comparison of previous/current English source versions
- import of a previous translated edition
- automatic glossary extraction and glossary-assisted translation suggestions
- PDF preview with segment highlighting

## Important binary assets

The two PDF standards are large binary files and are not committed to this repository. Before running locally, copy them into:

```text
backend/storage/samples/02-Planting.pdf
backend/storage/samples/TREE PLANTING STANDARDS 2nd edition 2026 FINAL.pdf
```

## Run on macOS

```bash
cd ~/test/translator
chmod +x start_macos.sh
./start_macos.sh
```

Then open:

```text
http://127.0.0.1:8000/app/?v=19
```

## Notes

The prototype can use `OPENAI_API_KEY` for real AI suggestions. Without it, the app attempts a free Google Translate fallback for testing only. For production, use an official translation API.
