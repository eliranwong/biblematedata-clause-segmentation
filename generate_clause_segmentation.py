#!/usr/bin/env python3
"""
Generate clause-segmented TSV files for all 24 tagged Bible translations
using:
  1. ~/biblemate/data_custom/tagged_translations.sqlite (morphology table)
  2. ../biblematedata-data-custom/tagged_bibles/tagged_chapters_and_verses/

Produces:
  - Option_A/<Translation>.tsv  (1 row per ClauseID per testament; non-contiguous spans joined with ' ... '; cross-verse NT clauses merged with '[v<Verse>] ')
  - Option_B/<Translation>.tsv  (sequential clause-boundary splitting in surface reading order)
"""

import argparse
import csv
import glob
import os
import re
import sqlite3
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MORPH_DB = os.path.expanduser("~/biblemate/data_custom/tagged_translations.sqlite")
DEFAULT_TAGGED_BIBLES_DIR = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "biblematedata-data-custom", "tagged_bibles", "tagged_chapters_and_verses")
)
DEFAULT_OUT_DIR = SCRIPT_DIR

TAG_RE = re.compile(r'(<(?:en|zh)\b[^>]*\bid="(wh?\d+)"[^>]*>.*?</(?:en|zh)>)')
STRIP_TAGS_RE = re.compile(r"<[^>]+>")

CLOSING_PUNCT = set(".,;:!?\"'”’)]}—–-。，、；：？！）」』）】〕〉》")
OPENING_PUNCT = set("\"'“‘([{「『（【〔〈《")


def load_word_to_clause(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ot_map = {}
    nt_map = {}
    cur.execute("SELECT Book, WordID, ClauseID FROM morphology")
    for book, wid, cid in cur.fetchall():
        if book <= 39:
            ot_map[wid] = cid
        else:
            nt_map[wid] = cid
    conn.close()
    return ot_map, nt_map


def strip_nlt_section_heading(verse_text):
    """
    In NLT2015.bible, non-canonical section headings appear as plain text
    at the start of a verse before the first <en id="..."> tag
    (e.g., 'The Account of Creation ', 'Psalm 3 ').
    Canonical Psalm superscriptions are inside <en id="wh..."> tags and are preserved.
    """
    m = TAG_RE.search(verse_text)
    if not m or m.start() == 0:
        return verse_text
    prefix = verse_text[: m.start()]
    if "<" in prefix:
        return verse_text
    stripped = prefix.rstrip()
    if not stripped:
        return verse_text
    # Section headings end with a letter/digit (no sentence/clause punctuation)
    # and do not end with quotes or dashes.
    if stripped[-1].isalnum() and len(prefix) > len(stripped):
        return verse_text[m.start() :]
    return verse_text


def split_gap(gap):
    """
    Split an untagged gap between two adjacent ClauseIDs into (left_part, right_part).
    """
    if not gap:
        return "", ""

    # If there is whitespace outside XML tags, split at the first whitespace run.
    in_tag = False
    ws_start = None
    ws_end = None
    for i, ch in enumerate(gap):
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag and ch.isspace():
            if ws_start is None:
                ws_start = i
        else:
            if ws_start is not None:
                ws_end = i
                break

    if ws_start is not None:
        left = gap[:ws_start]
        right = gap[ws_end:] if ws_end is not None else ""
        return left, right

    # No whitespace (common in Chinese, e.g. '<zh>：「</zh>' or '<zh>，</zh>').
    # If the gap is purely closing punctuation (even wrapped in <zh>...</zh>), keep on left.
    plain = STRIP_TAGS_RE.sub("", gap)
    if plain and all(c in CLOSING_PUNCT for c in plain):
        return gap, ""
    if plain and all(c in OPENING_PUNCT for c in plain):
        return "", gap

    # Mixed closing + opening punctuation (e.g. '<zh>：「</zh>'):
    # Split plain characters if wrapped in a single <zh>...</zh> or plain text.
    if gap.startswith("<zh>") and gap.endswith("</zh>") and "<" not in gap[4:-5]:
        inner = gap[4:-5]
        split_idx = 0
        while split_idx < len(inner) and inner[split_idx] in CLOSING_PUNCT:
            split_idx += 1
        left_inner = inner[:split_idx]
        right_inner = inner[split_idx:]
        left = f"<zh>{left_inner}</zh>" if left_inner else ""
        right = f"<zh>{right_inner}</zh>" if right_inner else ""
        return left, right

    # Default: if it starts with closing punct, put leading closing punct on left
    split_idx = 0
    while split_idx < len(gap) and gap[split_idx] in CLOSING_PUNCT:
        split_idx += 1
    return gap[:split_idx], gap[split_idx:]


def tokenize_verse(verse_text, ot_map, nt_map, is_nlt=False):
    if is_nlt:
        verse_text = strip_nlt_section_heading(verse_text)

    matches = list(TAG_RE.finditer(verse_text))
    if not matches:
        return []

    # Build raw segments: alternating (is_tag, text, cid)
    raw = []
    pos = 0
    for m in matches:
        if m.start() > pos:
            raw.append((False, verse_text[pos : m.start()], None))
        wid_str = m.group(2)
        if wid_str.startswith("wh"):
            wid = int(wid_str[2:])
            cid = ot_map.get(wid)
        else:
            wid = int(wid_str[1:])
            cid = nt_map.get(wid)
        raw.append((True, m.group(1), cid))
        pos = m.end()
    if pos < len(verse_text):
        raw.append((False, verse_text[pos:], None))

    # Assign untagged gaps to adjacent ClauseIDs, then merge contiguous same-ClauseID runs.
    # First, find runs of tagged items and gaps between them.
    tagged_indices = [i for i, item in enumerate(raw) if item[0] and item[2] is not None]
    if not tagged_indices:
        return []

    # Accumulate (cid, text_parts) in reading order
    runs = []  # list of [cid, list_of_strings]

    # Leading untagged text before first tagged item
    first_idx = tagged_indices[0]
    first_cid = raw[first_idx][2]
    leading = "".join(item[1] for item in raw[:first_idx]).lstrip()
    runs.append([first_cid, [leading, raw[first_idx][1]] if leading else [raw[first_idx][1]]])

    for k in range(len(tagged_indices) - 1):
        i1 = tagged_indices[k]
        i2 = tagged_indices[k + 1]
        cid1 = raw[i1][2]
        cid2 = raw[i2][2]
        gap = "".join(item[1] for item in raw[i1 + 1 : i2])

        if cid1 == cid2:
            if gap:
                runs[-1][1].append(gap)
            runs[-1][1].append(raw[i2][1])
        else:
            left_gap, right_gap = split_gap(gap)
            if left_gap:
                runs[-1][1].append(left_gap)
            new_parts = []
            if right_gap:
                new_parts.append(right_gap)
            new_parts.append(raw[i2][1])
            runs.append([cid2, new_parts])

    # Trailing untagged text after last tagged item
    last_idx = tagged_indices[-1]
    trailing = "".join(item[1] for item in raw[last_idx + 1 :]).rstrip()
    if trailing:
        runs[-1][1].append(trailing)

    return [(cid, "".join(parts).strip()) for cid, parts in runs if "".join(parts).strip()]


def process_bible(bible_path, ot_map, nt_map):
    name = os.path.splitext(os.path.basename(bible_path))[0]
    is_nlt = name == "NLT2015"

    conn = sqlite3.connect(bible_path)
    cur = conn.cursor()
    cur.execute("SELECT Book, Chapter, Verse, Scripture FROM Verses ORDER BY Book, Chapter, Verse")
    rows = cur.fetchall()
    conn.close()

    option_b_rows = []
    # Option A: keyed by (testament_idx, cid) -> list of (book, ch, v, text)
    # where testament_idx is 0 for OT (Book <= 39), 1 for NT (Book > 39)
    option_a_groups = defaultdict(list)

    for book, ch, v, scripture in rows:
        if not scripture:
            continue
        runs = tokenize_verse(scripture, ot_map, nt_map, is_nlt=is_nlt)
        if not runs:
            continue
        testament_idx = 0 if book <= 39 else 1
        for cid, text in runs:
            option_b_rows.append((cid, book, ch, v, text))
            option_a_groups[(testament_idx, cid)].append((book, ch, v, text))

    # Build Option A rows
    option_a_rows = []
    for (testament_idx, cid), spans in sorted(option_a_groups.items()):
        start_book, start_ch, start_v, _ = spans[0]
        # Group spans by verse so we can join intra-verse non-contiguous spans with ' ... '
        # and prefix subsequent verses with '[v<Verse>] '
        by_verse = []
        for b, c, v, txt in spans:
            if not by_verse or by_verse[-1][0] != (b, c, v):
                by_verse.append(((b, c, v), [txt]))
            else:
                by_verse[-1][1].append(txt)

        verse_chunks = []
        for idx, ((b, c, v), parts) in enumerate(by_verse):
            joined = " ... ".join(parts)
            if idx == 0:
                verse_chunks.append(joined)
            else:
                verse_chunks.append(f"[v{v}] {joined}")

        full_text = " ".join(verse_chunks)
        option_a_rows.append((cid, start_book, start_ch, start_v, full_text))

    return name, option_a_rows, option_b_rows


def write_tsv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(["ClauseID", "Book", "Chapter", "Verse", "Translation"])
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Generate clause-segmented TSV files for tagged Bible translations.")
    parser.add_argument("--morph-db", default=DEFAULT_MORPH_DB, help="Path to tagged_translations.sqlite")
    parser.add_argument(
        "--tagged-bibles-dir",
        default=DEFAULT_TAGGED_BIBLES_DIR,
        help="Directory containing tagged *.bible files",
    )
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output directory for Option_A and Option_B")
    args = parser.parse_args()

    ot_map, nt_map = load_word_to_clause(args.morph_db)
    bible_files = sorted(
        glob.glob(os.path.join(args.tagged_bibles_dir, "*.bible"))
        + glob.glob(os.path.join(args.tagged_bibles_dir, "public", "*.bible"))
    )
    print(f"Found {len(bible_files)} .bible files.")
    for bf in bible_files:
        name, opt_a, opt_b = process_bible(bf, ot_map, nt_map)
        write_tsv(os.path.join(args.out_dir, "Option_A", f"{name}.tsv"), opt_a)
        write_tsv(os.path.join(args.out_dir, "Option_B", f"{name}.tsv"), opt_b)
        print(f"  {name}: Option_A={len(opt_a)} rows, Option_B={len(opt_b)} rows")


if __name__ == "__main__":
    main()
