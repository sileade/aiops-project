#!/usr/bin/env python3
"""
HTML Report Parser - Extract Key Takeaways to Markdown

This script parses the AIOps Resilience Demo HTML report and extracts
the "Key Takeaways" (Ключевые выводы) section into a Markdown file.

Usage:
    python scripts/extract_key_takeaways.py [input_html] [output_md]
    
Examples:
    python scripts/extract_key_takeaways.py
    python scripts/extract_key_takeaways.py reports/resilience_demo_report.html
    python scripts/extract_key_takeaways.py report.html output/takeaways.md
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup


class KeyTakeawaysExtractor:
    """Extract Key Takeaways section from HTML report."""
    
    def __init__(self, html_path: str):
        self.html_path = Path(html_path)
        self.soup: Optional[BeautifulSoup] = None
        self.takeaways: List[Dict[str, str]] = []
        self.report_title: str = ""
        self.report_date: str = ""
        
    def load_html(self) -> bool:
        """Load and parse the HTML file."""
        if not self.html_path.exists():
            print(f"❌ Error: File not found: {self.html_path}")
            return False
            
        try:
            with open(self.html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.soup = BeautifulSoup(content, 'html.parser')
            print(f"✅ Loaded HTML file: {self.html_path}")
            return True
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False
    
    def extract_metadata(self) -> None:
        """Extract report title and date from header."""
        if not self.soup:
            return
            
        # Extract title
        title_elem = self.soup.find('h1')
        if title_elem:
            self.report_title = title_elem.get_text(strip=True)
            
        # Extract date
        date_elem = self.soup.find('p', class_='date')
        if date_elem:
            self.report_date = date_elem.get_text(strip=True)
        else:
            # Fallback: look for date pattern in header
            header = self.soup.find('header', class_='header')
            if header:
                for p in header.find_all('p'):
                    text = p.get_text(strip=True)
                    if '📅' in text or 'дата' in text.lower() or 'date' in text.lower():
                        self.report_date = text
                        break
    
    def extract_key_takeaways(self) -> bool:
        """Extract the Key Takeaways section."""
        if not self.soup:
            return False
            
        # Find the Key Insights / Ключевые выводы section
        # Look for section title containing "Key" or "Ключевые"
        section = None
        
        # Method 1: Find by section title text
        for section_title in self.soup.find_all(['h2', 'h3'], class_='section-title'):
            title_text = section_title.get_text(strip=True).lower()
            if 'ключевые' in title_text or 'key' in title_text or 'выводы' in title_text or 'insights' in title_text:
                section = section_title.find_parent('section')
                break
        
        # Method 2: Find insights-grid directly
        if not section:
            insights_grid = self.soup.find('div', class_='insights-grid')
            if insights_grid:
                section = insights_grid.find_parent('section')
        
        if not section:
            print("⚠️ Warning: Could not find Key Takeaways section")
            return False
            
        # Extract insight cards
        insight_cards = section.find_all('div', class_='insight-card')
        
        if not insight_cards:
            # Fallback: look for any cards with h4 and p
            insight_cards = section.find_all('div', recursive=True)
            insight_cards = [card for card in insight_cards if card.find('h4') and card.find('p')]
        
        for card in insight_cards:
            h4 = card.find('h4')
            p = card.find('p')
            
            if h4 and p:
                title = h4.get_text(strip=True)
                description = p.get_text(strip=True)
                
                # Extract emoji if present
                emoji = ""
                for char in title:
                    if ord(char) > 127:  # Non-ASCII, likely emoji
                        emoji = char
                        break
                
                self.takeaways.append({
                    'title': title,
                    'description': description,
                    'emoji': emoji
                })
        
        print(f"✅ Extracted {len(self.takeaways)} key takeaways")
        return len(self.takeaways) > 0
    
    def extract_scenarios_summary(self) -> List[Dict[str, str]]:
        """Extract summary of test scenarios."""
        scenarios = []
        
        if not self.soup:
            return scenarios
            
        scenario_cards = self.soup.find_all('div', class_='scenario-card')
        
        for card in scenario_cards:
            # Get scenario number
            number_elem = card.find('div', class_='scenario-number')
            number = number_elem.get_text(strip=True) if number_elem else ""
            
            # Get title
            title_elem = card.find('h3')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Get subtitle
            subtitle_elem = card.find('span', class_='subtitle')
            subtitle = subtitle_elem.get_text(strip=True) if subtitle_elem else ""
            
            # Get status
            status_elem = card.find('span', class_='scenario-status')
            status = status_elem.get_text(strip=True) if status_elem else ""
            
            if title:
                scenarios.append({
                    'number': number,
                    'title': title,
                    'subtitle': subtitle,
                    'status': status
                })
        
        return scenarios
    
    def generate_markdown(self, include_scenarios: bool = True) -> str:
        """Generate Markdown content from extracted data."""
        lines = []
        
        # Header
        lines.append("# Key Takeaways - AIOps Resilience Demo")
        lines.append("")
        
        # Metadata
        if self.report_title:
            lines.append(f"> **Source:** {self.report_title}")
        if self.report_date:
            lines.append(f"> **Report Date:** {self.report_date}")
        lines.append(f"> **Extracted:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Table of Contents
        lines.append("## Table of Contents")
        lines.append("")
        lines.append("1. [Key Takeaways](#key-takeaways)")
        if include_scenarios:
            lines.append("2. [Test Scenarios Summary](#test-scenarios-summary)")
        lines.append("")
        
        # Key Takeaways Section
        lines.append("---")
        lines.append("")
        lines.append("## Key Takeaways")
        lines.append("")
        
        if self.takeaways:
            for i, takeaway in enumerate(self.takeaways, 1):
                lines.append(f"### {i}. {takeaway['title']}")
                lines.append("")
                lines.append(takeaway['description'])
                lines.append("")
        else:
            lines.append("*No key takeaways found in the report.*")
            lines.append("")
        
        # Scenarios Summary
        if include_scenarios:
            scenarios = self.extract_scenarios_summary()
            
            lines.append("---")
            lines.append("")
            lines.append("## Test Scenarios Summary")
            lines.append("")
            
            if scenarios:
                # Table header
                lines.append("| # | Scenario | Description | Status |")
                lines.append("|---|----------|-------------|--------|")
                
                for scenario in scenarios:
                    status_icon = "✅" if "успешно" in scenario['status'].lower() or "success" in scenario['status'].lower() else "⚠️"
                    lines.append(f"| {scenario['number']} | {scenario['title']} | {scenario['subtitle']} | {status_icon} |")
                
                lines.append("")
            else:
                lines.append("*No scenarios found in the report.*")
                lines.append("")
        
        # Quick Reference
        lines.append("---")
        lines.append("")
        lines.append("## Quick Reference")
        lines.append("")
        lines.append("### Configuration (.env)")
        lines.append("")
        lines.append("```bash")
        lines.append("# Enable LLM Fallback")
        lines.append("ENABLE_LLM_FALLBACK=true")
        lines.append("OLLAMA_BASE_URL=http://ollama:11434/v1")
        lines.append("")
        lines.append("# Enable Caching")
        lines.append("ENABLE_CACHING=true")
        lines.append("CACHE_TTL_ANALYSIS=600")
        lines.append("")
        lines.append("# Circuit Breaker Settings")
        lines.append("CB_FAILURE_THRESHOLD=3")
        lines.append("CB_TIMEOUT=60")
        lines.append("```")
        lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*This document was automatically generated from the HTML report.*")
        lines.append("")
        
        return "\n".join(lines)
    
    def save_markdown(self, output_path: str) -> bool:
        """Save the generated Markdown to a file."""
        try:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            
            markdown_content = self.generate_markdown()
            
            with open(output, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"✅ Saved Markdown to: {output}")
            return True
        except Exception as e:
            print(f"❌ Error saving file: {e}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract Key Takeaways from HTML report to Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python extract_key_takeaways.py
  python extract_key_takeaways.py reports/custom_report.html
  python extract_key_takeaways.py report.html output/takeaways.md
        """
    )
    
    parser.add_argument(
        'input_html',
        nargs='?',
        default='reports/resilience_demo_report.html',
        help='Path to input HTML report (default: reports/resilience_demo_report.html)'
    )
    
    parser.add_argument(
        'output_md',
        nargs='?',
        default=None,
        help='Path to output Markdown file (default: reports/key_takeaways.md)'
    )
    
    parser.add_argument(
        '--no-scenarios',
        action='store_true',
        help='Exclude test scenarios summary from output'
    )
    
    parser.add_argument(
        '--print',
        action='store_true',
        dest='print_output',
        help='Print Markdown to stdout instead of saving to file'
    )
    
    args = parser.parse_args()
    
    # Determine paths
    script_dir = Path(__file__).parent.parent
    input_path = Path(args.input_html)
    
    if not input_path.is_absolute():
        input_path = script_dir / input_path
    
    if args.output_md:
        output_path = Path(args.output_md)
        if not output_path.is_absolute():
            output_path = script_dir / output_path
    else:
        output_path = script_dir / 'reports' / 'key_takeaways.md'
    
    # Process
    print("=" * 50)
    print("HTML Report Parser - Key Takeaways Extractor")
    print("=" * 50)
    print()
    
    extractor = KeyTakeawaysExtractor(str(input_path))
    
    if not extractor.load_html():
        sys.exit(1)
    
    extractor.extract_metadata()
    
    if not extractor.extract_key_takeaways():
        print("⚠️ Warning: No key takeaways extracted, generating empty report")
    
    if args.print_output:
        print()
        print("=" * 50)
        print("Generated Markdown:")
        print("=" * 50)
        print()
        print(extractor.generate_markdown(include_scenarios=not args.no_scenarios))
    else:
        if extractor.save_markdown(str(output_path)):
            print()
            print("✅ Extraction complete!")
            print(f"   Input:  {input_path}")
            print(f"   Output: {output_path}")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
