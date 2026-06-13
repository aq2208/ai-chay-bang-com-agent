#!/usr/bin/env python3
"""
Obsidian Vault Data Generator for Browser Viewer

What is this for:
    This script scans all Markdown (.md) files in this directory (the Obsidian vault)
    and packages them into a single JavaScript file (`docs_data.js`). This bundle is loaded
    by `viewer.html` to visualize, search, and navigate your team's documentation
    completely offline inside your browser, bypassing CORS restrictions.

Obsidian Official:
    You can also visualize this documentation using the official Obsidian app.
    Download it from: https://obsidian.md/
    Once installed, select "Open folder as vault" and select this 'docs' directory.

How to run and view:
    1. Run this generator script:
       python3 generate_data.py
    2. Open the HTML viewer in your web browser:
       open "/Users/lap15864-local/temp/claw-a-thon/ai-chay-bang-com-agent/docs/viewer.html"
       Or click: file:///Users/lap15864-local/temp/claw-a-thon/ai-chay-bang-com-agent/docs/viewer.html
"""

import os
import json
from pathlib import Path

def generate_vault_data():
    docs_dir = Path(__file__).parent.resolve()
    vault_data = {}
    
    # Files to ignore
    ignore_files = {
        'generate_data.py',
        'viewer.html',
        'docs_data.js'
    }
    
    print(f"Scanning markdown files in vault: {docs_dir}")
    
    for path in docs_dir.rglob('*.md'):
        # Get path relative to the docs directory
        rel_path = path.relative_to(docs_dir)
        
        # Skip hidden files/directories (like .obsidian)
        if any(part.startswith('.') for part in rel_path.parts):
            continue
            
        if rel_path.name in ignore_files:
            continue
            
        print(f" - Found: {rel_path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Store with standard forward slashes as keys
            key = str(rel_path).replace(os.path.sep, '/')
            vault_data[key] = content
        except Exception as e:
            print(f" Error reading {rel_path}: {e}")

    # Output file path
    output_path = docs_dir / 'docs_data.js'
    
    # Wrap JSON object in a global variable for viewer.html
    js_content = f"window.VAULT_DATA = {json.dumps(vault_data, indent=2, ensure_ascii=False)};\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    print(f"\nSuccessfully compiled vault data to {output_path}!")
    print(f"Open your browser to: file://{docs_dir}/viewer.html")

if __name__ == '__main__':
    generate_vault_data()
