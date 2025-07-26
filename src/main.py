import fitz
import json
import re
import os
import sys
import argparse
from typing import List, Dict, Any

class PDFOutlineExtractor:
    def __init__(self):
        # Patterns to identify and level numbered headings.
        self.level_patterns = [
            (re.compile(r'^\d+\.\d+\.\d+\s'), 3),
            (re.compile(r'^\d+\.\d+\s'), 2),
            (re.compile(r'^\d+\.\s'), 1),
        ]
        
        # Patterns to specifically identify list items.
        self.list_item_patterns = [
            re.compile(r'^\s*[\*\-•]\s+'),
            re.compile(r'^\s*[a-z]\)\s+'),
            re.compile(r'^\s*\(\d+\)\s+'),
            re.compile(r'^\s*\d+\)\s+'), # NEW: Catches "1)", "2)"
        ]
        
        # Patterns to filter out junk text.
        self.junk_patterns = [
            re.compile(r'^\s*page\s*\d+', re.IGNORECASE),
            re.compile(r'©|copyright|\u00A9', re.IGNORECASE),
            re.compile(r'.+\s*\.{3,}\s*\d+\s*$'), 
            # NEW: More robust date patterns
            re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}', re.IGNORECASE),
        ]
        self.paragraph_starters = {'this', 'the', 'in', 'at', 'for', 'with', 'from', 'by', 'an', 'a', 'it', 'as', 'on', 'to', 'of', 'and', 'or', 'but', 'however'}

    def extract_outline(self, pdf_path: str) -> Dict[str, Any]:
        doc = fitz.open(pdf_path)
        try:
            title = self._extract_title(doc, pdf_path)
            text_blocks = self._extract_text_blocks(doc)
            classified_blocks = self._classify_blocks(text_blocks)
            outline = self._assign_levels_by_structure(classified_blocks)
            final_outline = self._deduplicate_outline(outline)
            return {"title": title, "outline": final_outline}
        finally:
            doc.close()

    def _extract_title(self, doc: fitz.Document, pdf_path: str) -> str:
        if doc.metadata and doc.metadata.get('title'):
            title = doc.metadata['title'].strip()
            if len(title) > 5 and 'untitled' not in title.lower(): return title
        return os.path.basename(pdf_path).replace('.pdf', '').replace('_', ' ').title()

    def _extract_text_blocks(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        blocks = []
        for page_num, page in enumerate(doc):
            if page_num >= 50: break
            page_height = page.rect.height if page.rect.height > 0 else 1.0
            raw_blocks = page.get_text("dict", flags=fitz.TEXT_INHIBIT_SPACES)["blocks"]
            for block in raw_blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        line_text = "".join(span["text"] for span in line["spans"]).strip()
                        if line_text:
                            blocks.append({
                                "text": line_text, "page": page_num + 1,
                                "y_pos": line["bbox"][1], "x_pos": line["bbox"][0],
                                "page_height": page_height
                            })
        return blocks

    def _is_ignorable_line(self, text: str, y_pos: float, page_height: float, page_num: int) -> bool:

        # A filter to remove junk text before classification.
        if any(p.search(text) for p in self.junk_patterns): return True

        # Be more aggressive on the first page (page_num == 1)
        margin = 0.20 if page_num == 1 else 0.11
        if y_pos < page_height * margin or y_pos > page_height * (1 - margin): return True
        if text.strip().isdigit(): return True
        if text.endswith('.') and len(text.split()) > 10: return True
        return False

    def _classify_blocks(self, text_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Classifies each block as a HEADING, LIST_ITEM, or junk.
        candidates = []
        for block in text_blocks:
            text = block['text'].strip()
            if self._is_ignorable_line(text, block['y_pos'], block['page_height'], block['page']):
                continue

            block_type = None
            word_count = len(text.split())

            # Check for list items first.
            if any(p.match(text) for p in self.list_item_patterns):
                block_type = "LIST_ITEM"
            
            # Differentiate numbered headings from numbered list items.
            numbered_match = re.match(r'^(\d+(\.\d+)*)\.?\s+(.*)', text)
            if not block_type and numbered_match:
                content = numbered_match.group(3)
                # If content starts with a lowercase letter, it's a list item.
                if content and (content[0].islower() or len(text.split()) > 10):
                    block_type = "LIST_ITEM"
                else: # Otherwise, it's a heading.
                    block_type = "HEADING"
            
            # If not a list item or numbered heading, check for un-numbered headings.
            if not block_type:
                starts_like_paragraph = word_count > 0 and text.split()[0].lower() in self.paragraph_starters
                if not starts_like_paragraph:
                    if (text.isupper() and 1 <= word_count <= 6) or \
                       (text.istitle() and 1 <= word_count <= 8 and text.endswith(':')) or \
                       (text.istitle() and 1 <= word_count <= 4): # Stricter rule for titles without colons
                        block_type = "HEADING"
            
            if block_type:
                block['type'] = block_type
                candidates.append(block)
                
        candidates.sort(key=lambda x: (x["page"], x["y_pos"]))
        return candidates

    def _assign_levels_by_structure(self, classified_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Assigns H1-H3 levels using a stateful, context-aware model.
        if not classified_blocks: return []
        
        outline = []
        indent_stack = [] 
        last_heading_level = 0
        
        for block in classified_blocks:
            text = block['text']
            x_pos = round(block['x_pos'])
            current_level = 0
            
            if block['type'] == 'LIST_ITEM':
                current_level = min(last_heading_level + 1, 3)
            
            elif block['type'] == 'HEADING':
                is_numbered = False
                for pattern, level in self.level_patterns:
                    if pattern.match(text):
                        current_level, is_numbered = level, True
                        break
                if not is_numbered and re.match(r'^\d+\.\s', text):
                    current_level, is_numbered = 1, True

                if not is_numbered:
                    while indent_stack and x_pos < indent_stack[-1] - 5:
                        indent_stack.pop()
                    if not indent_stack or x_pos > indent_stack[-1] + 5:
                        if len(indent_stack) < 3:
                            indent_stack.append(x_pos)
                    current_level = len(indent_stack) if len(indent_stack) > 0 else 1
                else: 
                    indent_stack = [x_pos] * current_level

            if current_level > 0:
                final_level = max(1, min(current_level, 3))
                outline.append({"level": f"H{final_level}", "text": text, "page": block["page"]})
                if block['type'] == 'HEADING':
                    last_heading_level = final_level
        return outline

    def _deduplicate_outline(self, outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Removes duplicate headings that have the same text, level, AND page number.
        deduped_outline = []
        seen_tuples = set()
        for heading in outline:
            normalized_text = re.sub(r'\s+', ' ', heading['text']).strip().lower()
            heading_key = (normalized_text, heading['page'], heading['level'])
            if heading_key not in seen_tuples:
                deduped_outline.append(heading)
                seen_tuples.add(heading_key)
        return deduped_outline


def main():
    parser = argparse.ArgumentParser(description='A general, high-precision PDF outline extractor for H1-H3 headings.')
    parser.add_argument('input', help='Path to an input PDF file or a directory.')
    parser.add_argument('-o', '--output', help='Output directory (Default: same as input).')
    parser.add_argument('--version', action='version', version='PDF Outline Extractor (Definitive Final)')
    args = parser.parse_args()
    
    input_path = args.input
    output_dir = args.output

    if os.path.isfile(input_path):
        process_single_pdf(input_path, output_dir)
    elif os.path.isdir(input_path):
        print(f"📚 Processing all PDF files in directory: {input_path}")
        for filename in os.listdir(input_path):
            if filename.lower().endswith('.pdf'):
                file_path = os.path.join(input_path, filename)
                process_single_pdf(file_path, output_dir if output_dir else input_path)
    else:
        print(f"❌ Input path is not a valid file or directory: {input_path}")
        sys.exit(1)

def process_single_pdf(pdf_path: str, output_dir: str = None):
    if output_dir is None: output_dir = os.path.dirname(pdf_path) or "."
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, os.path.basename(pdf_path).replace('.pdf', '.json'))
    
    print(f"📄 Processing: {pdf_path}")
    try:
        extractor = PDFOutlineExtractor()
        result = extractor.extract_outline(pdf_path)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✅ Success! Found {len(result['outline'])} headings for '{result['title']}'.")
        print(f"   -> Saved to: {output_path}\n")
    except Exception as e:
        print(f"❌ Error processing {pdf_path}: {e}\n")

if __name__ == "__main__":
    main()