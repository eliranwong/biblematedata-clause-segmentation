# BibleMate Clause Segmentation

Clause-segmented Bible translations for all **66 books** across **24 translations**, generated solely from:
1. **`morphology` table** in `~/biblemate/data_custom/tagged_translations.sqlite` (`WordID` → `ClauseID` mapping for OT and NT).
2. **Word-tagged `Verses` tables** in `../biblematedata-data-custom/tagged_bibles/tagged_chapters_and_verses/*.bible` (and `public/*.bible`).

> **Note:** While this dataset is built directly from the two local sources above (with no build-time dependency on `OpenHebrewBible` or `OpenGNT`), the `ClauseID` values correspond directly to the clause segmentation of the **Hebrew/Aramaic OT** data in [OpenHebrewBible](https://github.com/eliranwong/OpenHebrewBible) and the **Greek NT** data in [OpenGNT](https://github.com/eliranwong/OpenGNT).

---

## Translations Included (24)

`ASV`, `BSB`, `CNETn`, `CNETsn`, `CUV`, `CUVn`, `CUVs`, `CUVsn`, `ESV2016`, `KJV`, `LCT`, `LEB`, `NASB1995`, `NASB2020`, `NET`, `NETn`, `NIV`, `NKJV`, `NLT2015`, `NRSV`, `RCUV`, `ULT`, `UST`, `WEB`

Remarks: Some materials are not provided in this repository for copyright reasons.

---

## Directory Structure & File Format

```text
biblematedata-clause-segmentation/
├── Option_A/                     # 1 row per ClauseID per testament
│   ├── ASV.tsv
│   ├── BSB.tsv
│   └── ... (24 .tsv files)
├── Option_B/                     # Sequential clause-boundary splitting in reading order
│   ├── ASV.tsv
│   ├── BSB.tsv
│   └── ... (24 .tsv files)
├── generate_clause_segmentation.py
└── README.md
```

Each `.tsv` file has 5 tab-separated columns:

| Column | Type | Description |
| :--- | :--- | :--- |
| `ClauseID` | `int` | Plain integer clause ID from `morphology`: `1`–`90562` for OT (`Book <= 39`, corresponding to [OpenHebrewBible](https://github.com/eliranwong/OpenHebrewBible)) and `1`–`26613` for NT (`Book > 39`, corresponding to [OpenGNT](https://github.com/eliranwong/OpenGNT)). |
| `Book` | `int` | Canonical book number (`1`–`39` OT, `40`–`66` NT). Distinguishes OT vs. NT `ClauseID`s. |
| `Chapter` | `int` | Chapter number. |
| `Verse` | `int` | Verse number (for cross-verse NT clauses in `Option_A`, the starting verse number). |
| `Translation` | `text` | Clause text preserving the original `<en id="wh...">` / `<zh id="wh...">` (OT) and `<en id="w...">` / `<zh id="w...">` (NT) word tags. |

---

## How the Segmentation Works

### 1. Word-to-Clause Resolution
- Every tagged span `<en id="wh...">` / `<zh id="wh...">` (OT) or `<en id="w...">` / `<zh id="w...">` (NT) in a verse's `Scripture` column is matched to its `WordID` in `morphology`:
  - `wh<WordID>` → `Book <= 39` (`426,581` Hebrew/Aramaic words → `90,562` clauses, aligned with [OpenHebrewBible](https://github.com/eliranwong/OpenHebrewBible))
  - `w<WordID>` → `Book > 39` (`138,013` Greek words → `26,612` distinct clauses across `1`–`26613`, aligned with [OpenGNT](https://github.com/eliranwong/OpenGNT))
- Using the `.bible` files rather than reconstructing from isolated cells in `morphology` preserves each translation's **natural word order, punctuation, and untagged connecting words**.

### 2. Section Headings vs. Canonical Psalm Superscriptions
- Obvious non-canonical section headings (such as plain-text headings at the start of verses in `NLT2015.bible`, e.g. `The Account of Creation ` or `Psalm 3 `) are stripped before segmentation.
- Canonical **Psalm superscriptions** (which are word-tagged inside `<en id="wh...">` / `<zh id="wh...">` in the `.bible` files) are **preserved** as part of the translation.

### 3. Untagged Gaps (Punctuation, Whitespace, and Untagged Words)
- Leading untagged text before the first tagged span in a verse attaches to the first clause; trailing untagged text after the last tagged span attaches to the last clause.
- Between two different `ClauseID`s:
  - If the gap contains whitespace outside XML tags, text before the first whitespace (e.g., closing punctuation `,`, `.`, `”`, `—`) attaches to the **preceding** clause; text after the whitespace (e.g., opening quotes `“` or untagged words) attaches to the **following** clause.
  - If there is no whitespace (e.g., Chinese `<zh>：「</zh>`), closing punctuation (`。`, `，`, `：`, `」`, etc.) attaches to the **preceding** clause and opening punctuation/untagged characters attach to the **following** clause.

### 4. Option A vs. Option B

#### `Option_A/` — Grouped by `ClauseID`
- Emits **strictly 1 row per `(Testament, ClauseID)`** in canonical order (`OT` first, then `NT`).
- **Non-contiguous intra-verse spans:** When a `ClauseID` is interrupted by another `ClauseID` within the same verse (e.g., due to English or Chinese word-order differences), its spans are joined with ` ... `.
- **Cross-verse NT clauses (36 cases in `morphology`):** Merged into a single row under the starting `Verse`, with `[v<Verse>] ` inserted before the text belonging to the subsequent verse(s). For example, Mark 7:21–22 (`ClauseID = 4614`) has `Verse = 21` and `[v22] ` before the v.22 words.

#### `Option_B/` — Sequential Clause-Boundary Splitting
- Processes each verse in **surface reading order**, splitting whenever the `ClauseID` changes.
- Preserves the translation's exact top-to-bottom word order without reordering or `...` joins; if a clause is interrupted by another clause, its `ClauseID` appears in multiple rows.

---

## Regeneration

Run:
```bash
python3 generate_clause_segmentation.py
```

---

## About the BibleMate AI Projects

This dataset extends [BibleMateData](https://github.com/eliranwong/biblematedata), which is part of the broader [BibleMate AI](https://github.com/eliranwong/biblemate) ecosystem, and is designed to work alongside:

- [BibleMate Web](https://github.com/eliranwong/biblemateweb) ([Web Demo](https://app.biblemate.ai))
- [BibleMate Agentic Workspace](https://github.com/eliranwong/biblemate-agentic-workspace)

The underlying Hebrew/Aramaic and Greek biblical materials are built on two open-source projects:

- [OpenHebrewBible](https://github.com/eliranwong/OpenHebrewBible)
- [OpenGNT](https://github.com/eliranwong/OpenGNT)
