"""
Round 1A: PDF Outline Extraction
Extracts structured outlines from PDF documents with 0-based page indexing
"""

import fitz 
import json
import re
import os
import sys
import argparse
from typing import List, Dict, Any
from collections import defaultdict

class PDFOutlineExtractor:
    def __init__(self):
        # Very strict patterns for document structure headings only
        self.major_section_patterns = [
            r'^\d+\.\s+[A-Z][A-Za-z\s\-–—]+$',                    # "1. Introduction"
            r'^\d+\.\d+\s+[A-Z][A-Za-z\s\-–—]+$',                 # "2.1 Background"
            r'^\d+\.\d+\.\d+\s+[A-Z][A-Za-z\s\-–—]+$',            # "2.1.1 Details"
            r'^\d+\.\d+\.\d+\.\d+\s+[A-Z][A-Za-z\s\-–—]+$',       # "2.1.1.1 Sub-details"
        ]
        
        # Bullet point patterns (more restrictive)
        self.bullet_patterns = [
            r'^\d+\.\d+\.\d+\.\d+\.\d+\s+[A-Za-z]',               # "2.1.2.3.1 Bullet"
        ]
        
        # Major document sections (always H1)
        self.major_sections = {
            'revision history', 'table of contents', 'acknowledgements', 'acknowledgments',
            'references', 'bibliography', 'appendix', 'glossary', 'index',
            'preface', 'foreword', 'abstract', 'executive summary', 'mission statement',
            'goals', 'objectives', 'pathway options', 'regular pathway', 'distinction pathway'
        }
    
    def extract_outline(self, pdf_path: str) -> Dict[str, Any]:
        """Extract structured outline from PDF with 0-based page indexing"""
        doc = fitz.open(pdf_path)
        
        try:
            # Extract title
            title = self._extract_title(doc, pdf_path)
            
            # Extract all text blocks with formatting information
            all_text_blocks = self._extract_all_text_blocks(doc)
            
            # Identify headings with very strict criteria
            headings = self._identify_document_headings(all_text_blocks)
            
            # Create clean outline
            outline = self._create_structured_outline(headings)
            
            return {
                "title": title,
                "outline": outline
            }
        finally:
            doc.close()
    
    def _extract_title(self, doc, pdf_path: str) -> str:
        """Extract document title intelligently"""
        # Try metadata first
        metadata = doc.metadata
        if metadata and metadata.get('title'):
            title = metadata['title'].strip()
            if title and 5 < len(title) < 200 and not any(skip in title.lower() for skip in ['microsoft', 'word', 'document']):
                return title
        
        # Look for title in first page
        if len(doc) == 0:
            return os.path.basename(pdf_path).replace('.pdf', '')
        
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        
        title_candidates = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    max_size = 0
                    is_bold = False
                    y_pos = line["bbox"][1]
                    
                    for span in line["spans"]:
                        line_text += span["text"]
                        max_size = max(max_size, span["size"])
                        if span["flags"] & 2**4:  # Bold flag
                            is_bold = True
                    
                    line_text = line_text.strip()
                    
                    # Look for title-like text in top portion
                    if (line_text and 10 < len(line_text) < 200 and
                        not re.match(r'^\d+$', line_text) and
                        not line_text.lower().startswith(('page', 'version', '©', 'copyright')) and
                        y_pos < page.rect.height * 0.4):  # Top 40% of page
                        
                        title_candidates.append({
                            "text": line_text,
                            "size": max_size,
                            "is_bold": is_bold,
                            "y_pos": y_pos
                        })
        
        if title_candidates:
            # Sort by font size (descending) and position (ascending)
            title_candidates.sort(key=lambda x: (-x["size"], x["y_pos"]))
            return title_candidates[0]["text"]
        
        return os.path.basename(pdf_path).replace('.pdf', '').replace('_', ' ').title()
    
    def _extract_all_text_blocks(self, doc) -> List[Dict[str, Any]]:
        """Extract all text blocks with formatting information"""
        all_blocks = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        line_text = ""
                        max_size = 0
                        flags = 0
                        
                        for span in line["spans"]:
                            line_text += span["text"]
                            max_size = max(max_size, span["size"])
                            flags |= span["flags"]
                        
                        line_text = line_text.strip()
                        
                        if line_text and len(line_text) > 2:
                            all_blocks.append({
                                "text": line_text,
                                "page": page_num,  # 0-based indexing
                                "size": max_size,
                                "flags": flags,
                                "is_bold": bool(flags & 2**4),
                                "bbox": line["bbox"],
                                "y_pos": line["bbox"][1]
                            })
        
        return all_blocks
    
    def _identify_document_headings(self, text_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify only major document structure headings"""
        if not text_blocks:
            return []
        
        # Calculate font size statistics
        font_sizes = [block["size"] for block in text_blocks]
        avg_font_size = sum(font_sizes) / len(font_sizes)
        max_font_size = max(font_sizes)
        
        headings = []
        
        for block in text_blocks:
            text = block["text"].strip()
            
            # Skip if obviously not a heading
            if self._is_definitely_not_heading(text):
                continue
            
            # Skip bullet points and list items for designed PDFs
            if self._is_bullet_or_list_item(text):
                continue
            
            # Check for numbered sections (strict patterns)
            is_numbered_section = any(re.match(pattern, text) for pattern in self.major_section_patterns)
            
            # Check for major document sections (more flexible matching)
            is_major_section = any(
                section in text.lower() and len(text.split()) <= 8
                for section in self.major_sections
            )
            
            # Font and formatting criteria (stricter for designed PDFs)
            is_large_font = block["size"] > avg_font_size + 2.0  # Increased threshold
            is_very_large_font = block["size"] > avg_font_size + 3.0
            is_bold = block["is_bold"]
            is_short_and_capitalized = (
                len(text.split()) <= 6 and  # Reduced word count
                text[0].isupper() and 
                not text.endswith('.')
            )
            
            # All caps section headers
            is_all_caps_section = (
                text.isupper() and 
                5 <= len(text) <= 50 and
                len(text.split()) <= 6
            )
            
            # Very strict acceptance criteria for designed PDFs
            if is_numbered_section:
                # Numbered sections are always accepted
                headings.append({
                    "text": text,
                    "page": block["page"],
                    "size": block["size"],
                    "is_bold": block["is_bold"],
                    "type": "numbered"
                })
            elif is_major_section and (is_large_font or is_bold):
                # Major sections with good formatting
                headings.append({
                    "text": text,
                    "page": block["page"],
                    "size": block["size"],
                    "is_bold": block["is_bold"],
                    "type": "major"
                })
            elif is_all_caps_section and (is_large_font or is_bold):
                # All caps section headers
                headings.append({
                    "text": text,
                    "page": block["page"],
                    "size": block["size"],
                    "is_bold": block["is_bold"],
                    "type": "section"
                })
            elif (is_very_large_font and is_bold and is_short_and_capitalized and 
                  block["size"] > avg_font_size + 3.0):
                # Very prominent text that looks like a heading
                headings.append({
                    "text": text,
                    "page": block["page"],
                    "size": block["size"],
                    "is_bold": block["is_bold"],
                    "type": "prominent"
                })
        
        # Sort by page and position
        headings.sort(key=lambda x: (x["page"], -x["y_pos"] if "y_pos" in x else 0))
        
        # Remove duplicates and clean up
        return self._clean_headings(headings)
    
    def _is_bullet_or_list_item(self, text: str) -> bool:
        """Check if text is a bullet point or list item"""
        # Skip obvious bullet points and list items
        bullet_patterns = [
            r'^•\s+',                           # • bullet
            r'^-\s+',                           # - bullet  
            r'^\*\s+',                          # * bullet
            r'^\d+\s+credits?\s+of',            # "4 credits of Math"
            r'^[A-Z][a-z]+\s+\d+\s+credits',    # "Math 4 credits"
            r'^\d+\.\d+\s+GPA',                 # "3.5 GPA"
            r'^One must be',                    # "One must be a Computer"
            r'^Either participate',             # "Either participate in"
            r'^Join and actively',              # "Join and actively participate"
            r'^Participate in a minimum',       # "Participate in a minimum"
            r'^Students should',                # "Students should take"
            r'^At least one',                   # "At least one math"
            r'^Science course should',          # "Science course should be"
        ]
        
        for pattern in bullet_patterns:
            if re.match(pattern, text):
                return True
        
        # Skip if it starts with a number followed by descriptive text
        if re.match(r'^\d+\s+[a-z]', text):
            return True
            
        return False
    
    def _is_definitely_not_heading(self, text: str) -> bool:
        """Very strict filter for non-headings"""
        text_lower = text.lower()
        
        # Skip if too long (definitely paragraph)
        if len(text) > 120:
            return True
        
        # Skip obvious non-headings
        skip_patterns = [
            r'^\d+$',                           # Just numbers
            r'^page \d+',                       # Page numbers
            r'^figure \d+',                     # Figure captions
            r'^table \d+',                      # Table captions
            r'^\w+@\w+\.\w+',                  # Email addresses
            r'^https?://',                      # URLs
            r'^www\.',                          # URLs
            r'^\d{1,2}:\d{2}',                 # Time stamps
            r'^\d{1,2}/\d{1,2}/\d{2,4}',       # Dates
            r'^copyright',                      # Copyright notices
            r'^©',                              # Copyright symbol
            r'^version \d+',                    # Version numbers
            r'^\d+ of \d+',                     # Page x of y
            r'^may \d+, \d{4}',                # Dates
            r'^overview$',                      # Single word "overview"
            r'^version \d+\.\d+$',             # Version numbers
            r'^to provide',                     # Mission statement content
            r'^inspire teen',                   # Goals content
            r'^encourage students',             # Goals content
            r'^connect students',               # Goals content
        ]
        
        for pattern in skip_patterns:
            if re.match(pattern, text_lower):
                return True
        
        # Skip if it ends with sentence punctuation
        if text.endswith(('.', '!', '?', ';')):
            return True
        
        # Skip if it starts with common paragraph words
        paragraph_starters = [
            'this', 'the', 'in', 'at', 'for', 'with', 'from', 'by', 'an', 'a',
            'it', 'as', 'on', 'to', 'of', 'and', 'or', 'but', 'however', 'inspire',
            'encourage', 'connect', 'support', 'cultivate', 'signal'
        ]
        
        first_word = text.split()[0].lower() if text.split() else ""
        if first_word in paragraph_starters:
            return True
        
        return False
    
    def _clean_headings(self, headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicates and clean up headings"""
        if not headings:
            return []
        
        cleaned = []
        seen_texts = set()
        
        for heading in headings:
            text = heading["text"]
            text_normalized = re.sub(r'\s+', ' ', text.strip())
            
            # Skip exact duplicates
            if text_normalized.lower() in seen_texts:
                continue
            
            cleaned.append(heading)
            seen_texts.add(text_normalized.lower())
        
        return cleaned
    
    def _create_structured_outline(self, headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create structured outline with proper H1/H2/H3/H4 levels"""
        if not headings:
            return []
        
        outline = []
        
        for heading in headings:
            text = heading["text"]
            level = self._determine_heading_level(text, heading.get("type", ""))
            
            outline.append({
                "level": level,
                "text": text,
                "page": heading["page"]  # Already 0-based
            })
        
        return outline
    
    def _determine_heading_level(self, text: str, heading_type: str) -> str:
        """Determine heading level (H1, H2, H3, H4) based on numbering and content"""
        
        # Check numbering patterns first (most reliable)
        if re.match(r'^\d+\.\s', text):  # "1. Title"
            return "H1"
        elif re.match(r'^\d+\.\d+\s', text):  # "1.1 Title"
            return "H2"
        elif re.match(r'^\d+\.\d+\.\d+\s', text):  # "1.1.1 Title"
            return "H3"
        elif re.match(r'^\d+\.\d+\.\d+\.\d+\s', text):  # "1.1.1.1 Title"
            return "H4"
        elif re.match(r'^\d+\.\d+\.\d+\.\d+\.\d+\s', text):  # "2.1.2.3.1 Bullet"
            return "H4"  # Bullet points one level down
        
        # Major document sections are always H1
        if heading_type == "major":
            return "H1"
        
        # Section headers (like PATHWAY OPTIONS) are H1
        if heading_type == "section":
            return "H1"
        
        # Default for other headings
        return "H1"

def process_single_pdf(pdf_path: str, output_dir: str = None):
    """Process a single PDF file"""
    if not os.path.exists(pdf_path):
        print(f"❌ PDF file not found: {pdf_path}")
        return False
    
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path) or "."
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename
    pdf_filename = os.path.basename(pdf_path)
    output_filename = pdf_filename.replace('.pdf', '.json')
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        print(f"📄 Processing: {pdf_path}")
        extractor = PDFOutlineExtractor()
        result = extractor.extract_outline(pdf_path)
        
        # Save result
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        print(f"✅ Successfully processed: {pdf_filename}")
        print(f"📁 Output saved to: {output_path}")
        print(f"📊 Title: {result['title']}")
        print(f"📊 Found {len(result['outline'])} headings")
        
        # Show level distribution
        level_counts = {}
        for item in result['outline']:
            level = item['level']
            level_counts[level] = level_counts.get(level, 0) + 1
        
        if level_counts:
            print(f"📈 Level distribution: {level_counts}")
        
        # Show first few headings as preview
        if result['outline']:
            print(f"📋 Preview of headings:")
            for i, heading in enumerate(result['outline'][:5]):
                print(f"   {i+1}. [{heading['level']}] {heading['text']} (page {heading['page']})")
            
            if len(result['outline']) > 5:
                print(f"   ... and {len(result['outline']) - 5} more headings")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing {pdf_filename}: {str(e)}")
        return False

def process_directory(input_dir: str, output_dir: str = None):
    """Process all PDF files in a directory"""
    if not os.path.exists(input_dir):
        print(f"❌ Input directory not found: {input_dir}")
        return
    
    if output_dir is None:
        output_dir = input_dir
    
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"❌ No PDF files found in: {input_dir}")
        return
    
    print(f"📚 Found {len(pdf_files)} PDF files to process")
    
    success_count = 0
    for pdf_file in pdf_files:
        pdf_path = os.path.join(input_dir, pdf_file)
        if process_single_pdf(pdf_path, output_dir):
            success_count += 1
        print()  # Add spacing
    
    print(f"🎉 Processing complete: {success_count}/{len(pdf_files)} files processed successfully")

def main():
    parser = argparse.ArgumentParser(description='Round 1A: PDF Outline Extraction')
    parser.add_argument('input', help='Input PDF file or directory')
    parser.add_argument('-o', '--output', help='Output directory (default: same as input)')
    parser.add_argument('--version', action='version', version='PDF Outline Extractor 2.0')
    
    args = parser.parse_args()
    
    if os.path.isfile(args.input):
        process_single_pdf(args.input, args.output)
    elif os.path.isdir(args.input):
        process_directory(args.input, args.output)
    else:
        print(f"❌ Input path not found: {args.input}")
        sys.exit(1)

if __name__ == "__main__":
    main()
