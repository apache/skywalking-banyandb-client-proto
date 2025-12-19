#!/usr/bin/env python3
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Proto File Sync Script for Apache SkyWalking BanyanDB

This script syncs proto files from the Apache SkyWalking BanyanDB repository
and intelligently merges multiple remote files into consolidated local files.
"""

import argparse
import os
import re
import sys
from typing import Dict, List, Set, Tuple
from urllib.request import urlopen
from urllib.error import URLError

# ANSI color codes for terminal output
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'

# Configuration: Module mapping
MODULES = {
    'common': {'files': 'all'},
    'database': {'files': ['schema.proto', 'rpc.proto']},
    'measure': {'files': 'all'},
    'model': {'files': 'all'},
    'property': {'files': ['property.proto', 'rpc.proto']},
    'stream': {'files': 'all'},
    'trace': {'files': 'all'}
}

# Exclusion list: Messages and RPCs to exclude from merged files
# Organized by module. Each module can have 'messages' and 'rpcs' lists.
EXCLUDE_LIST = {
    'common': {
        'messages': [],
        'rpcs': []
    },
    'database': {
        'messages': [],
        'rpcs': []
    },
    'measure': {
        'messages': ['DeleteExpiredSegmentsRequest', 'DeleteExpiredSegmentsResponse', 'InternalWriteRequest'],
        'rpcs': ['DeleteExpiredSegments']
    },
    'model': {
        'messages': [],
        'rpcs': []
    },
    'property': {
        'messages': ['InternalUpdateRequest', 'InternalDeleteRequest', 'InternalQueryResponse', 'InternalRepairRequest', 'InternalRepairResponse'],
        'rpcs': []
    },
    'stream': {
        'messages': ['DeleteExpiredSegmentsRequest', 'DeleteExpiredSegmentsResponse', 'InternalWriteRequest'],
        'rpcs': ['DeleteExpiredSegments']
    },
    'trace': {
        'messages': ['DeleteExpiredSegmentsRequest', 'DeleteExpiredSegmentsResponse', 'InternalWriteRequest'],
        'rpcs': ['DeleteExpiredSegments']
    }
}

# Skip patterns: Patterns and options to skip during proto parsing
# - line_prefixes: Lines starting with these strings will be skipped
# - line_contains: Lines containing these strings will be skipped
# - option_blocks: Option blocks that require brace tracking (multi-line)
# - import_contains: Import statements containing these strings will be skipped
SKIP_PATTERNS = {
    'line_prefixes': [
        'option go_package',
    ],
    'line_contains': [
        'option (grpc.gateway.protoc_gen_openapiv2.options.openapiv2_swagger)',
    ],
    'option_blocks': [
        'option (google.api.http)',
    ],
    'import_contains': [
        'google/api/annotations.proto',
        'protoc-gen-openapiv2/options/annotations.proto',
    ],
}

# GitHub repository configuration
GITHUB_REPO = "apache/skywalking-banyandb"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
REMOTE_PROTO_PATH = "api/proto/banyandb"


def fetch_directory_listing(branch: str, module: str) -> List[str]:
    """
    Fetch the list of proto files in a remote directory using GitHub API.
    Falls back to a predefined list if API fails.
    """
    # Try GitHub API first
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{REMOTE_PROTO_PATH}/{module}/v1?ref={branch}"
    
    try:
        import json
        with urlopen(api_url) as response:
            data = json.loads(response.read().decode('utf-8'))
            proto_files = [item['name'] for item in data if item['name'].endswith('.proto')]
            return sorted(proto_files)
    except Exception as e:
        print(f"{Colors.YELLOW}Warning: Could not fetch directory listing via API: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Trying common file names...{Colors.RESET}")
        
        # Fallback: Try common file names
        common_names = ['rpc.proto', 'write.proto', 'query.proto', 'schema.proto', 
                       'topn.proto', 'model.proto', 'common.proto']
        found_files = []
        for filename in common_names:
            url = f"{GITHUB_RAW_BASE}/{GITHUB_REPO}/{branch}/{REMOTE_PROTO_PATH}/{module}/v1/{filename}"
            try:
                with urlopen(url) as response:
                    if response.status == 200:
                        found_files.append(filename)
            except:
                pass
        
        if found_files:
            return sorted(found_files)
        else:
            raise Exception(f"Could not determine proto files for module '{module}'")


def fetch_proto_file(branch: str, module: str, filename: str) -> str:
    """Fetch a single proto file from GitHub."""
    url = f"{GITHUB_RAW_BASE}/{GITHUB_REPO}/{branch}/{REMOTE_PROTO_PATH}/{module}/v1/{filename}"
    
    try:
        with urlopen(url) as response:
            return response.read().decode('utf-8')
    except URLError as e:
        raise Exception(f"Failed to fetch {url}: {e}")


def parse_proto_file(content: str) -> Dict[str, any]:
    """
    Parse a proto file into structured components.
    Returns a dict with: license, syntax, java_package, package, imports, body
    """
    lines = content.split('\n')
    result = {
        'license': [],
        'syntax': None,
        'java_package': None,
        'package': None,
        'imports': [],
        'body': []
    }
    
    license_done = False
    syntax_done = False
    package_done = False
    in_http_option = False
    brace_depth = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect license header - collect all consecutive comment lines from the start
        if not license_done:
            # Check if this is a comment line (// or /* */ style)
            is_comment = (stripped.startswith('//') or 
                         stripped.startswith('/*') or 
                         (stripped.startswith('*') and i > 0 and '/*' in lines[i-1]))
            
            if is_comment:
                result['license'].append(line)
                continue
            elif not stripped:
                # Empty line after comments - license is done
                license_done = True
                continue
            else:
                # Non-comment, non-empty line - license must have ended
                license_done = True
                # Fall through to process this line
        
        # Skip empty lines after license but before syntax
        if license_done and not syntax_done and not stripped:
            continue
        
        # Parse syntax
        if not syntax_done and stripped.startswith('syntax ='):
            result['syntax'] = line
            syntax_done = True
            continue
        
        # Parse java_package option
        if stripped.startswith('option java_package'):
            if not result['java_package']:
                result['java_package'] = line
            continue
        
        # Skip lines matching line_prefixes patterns
        if any(stripped.startswith(prefix) for prefix in SKIP_PATTERNS['line_prefixes']):
            continue
        
        # Skip lines matching line_contains patterns
        if any(pattern in stripped for pattern in SKIP_PATTERNS['line_contains']):
            continue
        
        # Track and skip option blocks (multi-line options requiring brace tracking)
        # Check if we're starting a new option block (can appear after syntax)
        if syntax_done:
            for option_pattern in SKIP_PATTERNS['option_blocks']:
                if option_pattern in stripped:
                    # Always skip the line when we detect the pattern
                    brace_depth = stripped.count('{') - stripped.count('}')
                    if brace_depth > 0:
                        # Multi-line option, start tracking
                        in_http_option = True
                    # For single-line options, brace_depth <= 0, so we just skip and continue
                    continue
            
            if in_http_option:
                # We're inside an option block, track braces
                brace_depth += stripped.count('{') - stripped.count('}')
                if brace_depth <= 0:
                    # Reached the end of the option block
                    in_http_option = False
                continue
        
        # Parse package declaration
        if not package_done and stripped.startswith('package '):
            result['package'] = line
            package_done = True
            continue
        
        # Parse imports (skip patterns in import_contains)
        if stripped.startswith('import '):
            if not any(pattern in line for pattern in SKIP_PATTERNS['import_contains']):
                result['imports'].append(line)
            continue
        
        # Everything else is body (skip if we're in an option block being tracked)
        if syntax_done and package_done and not in_http_option:
            result['body'].append(line)
    
    return result


def transform_import_path(import_line: str) -> str:
    """
    Transform import paths from old format to new merged format.
    banyandb/{module}/v1/{file}.proto -> banyandb/v1/banyandb-{module}.proto
    
    Example:
      import "banyandb/common/v1/common.proto"; -> import "banyandb/v1/banyandb-common.proto";
      import "banyandb/model/v1/query.proto"; -> import "banyandb/v1/banyandb-model.proto";
    """
    import re
    
    # Pattern to match: banyandb/{module}/v1/{file}.proto
    # Extract the module name and replace the entire path
    def replace_import(match):
        module = match.group(1)
        return f'banyandb/v1/banyandb-{module}.proto'
    
    # Replace the path pattern in the import statement
    new_line = re.sub(
        r'banyandb/([^/]+)/v1/[^"]+\.proto',
        replace_import,
        import_line
    )
    
    return new_line


def filter_excluded_definitions(body_lines: List[str], exclude_messages: List[str], exclude_rpcs: List[str]) -> List[str]:
    """
    Filter out excluded messages and RPCs from the body.
    
    Args:
        body_lines: The body lines to filter
        exclude_messages: List of message names to exclude
        exclude_rpcs: List of RPC names to exclude
    
    Returns:
        Filtered body lines with excluded definitions removed
    """
    if not body_lines or (not exclude_messages and not exclude_rpcs):
        return body_lines
    
    result = []
    i = 0
    skip_until_close = False
    brace_depth = 0
    
    while i < len(body_lines):
        line = body_lines[i]
        stripped = line.strip()
        
        # Check if we're currently skipping a definition
        if skip_until_close:
            # Track brace depth to know when the definition ends
            brace_depth += stripped.count('{') - stripped.count('}')
            
            if brace_depth <= 0:
                # Definition ended, stop skipping
                skip_until_close = False
                brace_depth = 0
            
            i += 1
            continue
        
        # Check for excluded messages
        if exclude_messages and stripped.startswith('message '):
            # Extract message name
            match = re.match(r'message\s+(\w+)', stripped)
            if match:
                message_name = match.group(1)
                if message_name in exclude_messages:
                    # Start skipping this message definition
                    skip_until_close = True
                    brace_depth = stripped.count('{') - stripped.count('}')
                    i += 1
                    continue
        
        # Check for excluded RPCs
        if exclude_rpcs and stripped.startswith('rpc '):
            # Extract RPC name
            match = re.match(r'rpc\s+(\w+)', stripped)
            if match:
                rpc_name = match.group(1)
                if rpc_name in exclude_rpcs:
                    # Check if this is a single-line RPC (ends with ;) or multi-line (has {)
                    if stripped.endswith(';'):
                        # Single-line RPC, skip just this line
                        i += 1
                        continue
                    elif '{' in stripped:
                        # Multi-line RPC, start skipping
                        skip_until_close = True
                        brace_depth = stripped.count('{') - stripped.count('}')
                        i += 1
                        continue
        
        # Keep this line
        result.append(line)
        i += 1
    
    return result


def remove_options_from_rpc_blocks(body_lines: List[str]) -> List[str]:
    """
    Remove option lines from inside RPC method blocks and convert to single-line RPCs if only options remain.
    Removes lines matching patterns in SKIP_PATTERNS['option_blocks'] from within RPC definitions.
    Converts:
      rpc Query(QueryRequest) returns (QueryResponse) {
        option (google.api.http) = {...};
      }
    to:
      rpc Query(QueryRequest) returns (QueryResponse);
    """
    if not body_lines:
        return body_lines
    
    result = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        stripped = line.strip()
        
        # Check if this is an RPC line ending with {
        if 'rpc ' in stripped and stripped.endswith('{'):
            rpc_line = line
            j = i + 1
            block_content = []
            option_count = 0
            
            # Scan through the RPC block and collect non-option lines
            while j < len(body_lines):
                block_line = body_lines[j]
                block_stripped = block_line.strip()
                
                # Check if we hit another RPC or service/message definition (malformed block)
                if (block_stripped.startswith('rpc ') or 
                    block_stripped.startswith('service ') or 
                    block_stripped.startswith('message ')):
                    # Malformed RPC block (no proper closing brace), convert to single-line
                    rpc_single_line = rpc_line.rstrip().rstrip('{').rstrip()
                    result.append(rpc_single_line + ';')
                    # Continue from this line (don't skip it)
                    i = j
                    break
                
                # Check if we've reached a closing brace
                if block_stripped == '}':
                    # This could be the RPC block's closing brace OR the service's closing brace
                    # If we only found options (and empty lines), it's likely the RPC's closing brace
                    # If we found no options at all, it might be the service's closing brace (malformed RPC)
                    
                    has_non_empty_content = any(line.strip() for line in block_content)
                    
                    if option_count > 0 or has_non_empty_content:
                        # We found content in this block, so this } belongs to the RPC
                        if has_non_empty_content:
                            # Keep the block with non-option content
                            result.append(rpc_line)
                            result.extend(block_content)
                            result.append(block_line)
                        else:
                            # Only had options (now removed), convert to single-line
                            rpc_single_line = rpc_line.rstrip().rstrip('{').rstrip()
                            result.append(rpc_single_line + ';')
                        i = j + 1
                    else:
                        # No options and no content found, this } likely belongs to service (malformed RPC)
                        rpc_single_line = rpc_line.rstrip().rstrip('{').rstrip()
                        result.append(rpc_single_line + ';')
                        # Don't consume the }, continue from it
                        i = j
                    break
                
                # Check if this line is an option we want to remove
                is_skip_option = any(pattern in block_stripped for pattern in SKIP_PATTERNS['option_blocks'])
                
                if is_skip_option:
                    option_count += 1
                else:
                    # Keep lines that are not skippable options (including empty lines)
                    block_content.append(block_line)
                
                j += 1
            else:
                # Reached end of file without closing brace, convert to single-line
                rpc_single_line = rpc_line.rstrip().rstrip('{').rstrip()
                result.append(rpc_single_line + ';')
                i += 1
            continue
        
        result.append(line)
        i += 1
    
    return result


def cleanup_empty_rpc_blocks(body_lines: List[str]) -> List[str]:
    """
    Remove empty {} blocks from RPC definitions.
    Converts:
      rpc Query(QueryRequest) returns (QueryResponse) {
      }
    to:
      rpc Query(QueryRequest) returns (QueryResponse);
    """
    if not body_lines:
        return body_lines
    
    result = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        stripped = line.strip()
        
        # Check if this is an RPC line ending with {
        if 'rpc ' in stripped and stripped.endswith('{'):
            # Look ahead to see if the next non-empty line is just }
            j = i + 1
            # Skip empty lines
            while j < len(body_lines) and not body_lines[j].strip():
                j += 1
            
            if j < len(body_lines) and body_lines[j].strip() == '}':
                # Found empty RPC block, remove the { and the }
                # Replace the rpc line to remove the { at the end
                rpc_line = line.rstrip().rstrip('{').rstrip()
                result.append(rpc_line + ';')
                # Skip the closing }
                i = j + 1
                continue
        
        result.append(line)
        i += 1
    
    return result


def merge_proto_files(proto_contents: List[str], current_module: str = None, exclude_messages: List[str] = None, exclude_rpcs: List[str] = None) -> str:
    """
    Intelligently merge multiple proto files into one.
    - Keep one license header
    - Keep one syntax declaration
    - Keep one java_package option
    - Keep one package declaration
    - Merge and deduplicate imports
    - Concatenate all body content
    """
    if not proto_contents:
        return ""
    
    parsed_files = [parse_proto_file(content) for content in proto_contents]
    
    # Build the merged content
    merged = []
    
    # 1. License header (from first file)
    if parsed_files[0]['license']:
        merged.extend(parsed_files[0]['license'])
        merged.append('')
    
    # 2. Syntax declaration (from first file)
    if parsed_files[0]['syntax']:
        merged.append(parsed_files[0]['syntax'])
        merged.append('')
    
    # 3. Java package option (from first file)
    if parsed_files[0]['java_package']:
        merged.append(parsed_files[0]['java_package'])
        merged.append('')
    
    # 4. Package declaration (from first file)
    if parsed_files[0]['package']:
        merged.append(parsed_files[0]['package'])
        merged.append('')
    
    # 5. Merge, transform, and deduplicate imports
    all_imports: Set[str] = set()
    for parsed in parsed_files:
        for imp in parsed['imports']:
            # Transform the import path to the new merged file format
            transformed_imp = transform_import_path(imp.strip())
            
            # Filter out self-imports (imports that reference the same module being merged)
            if current_module and f'banyandb/v1/banyandb-{current_module}.proto' in transformed_imp:
                continue
            
            all_imports.add(transformed_imp)
    
    if all_imports:
        # Sort imports: google first, then validate, then banyandb
        sorted_imports = sorted(all_imports, key=lambda x: (
            0 if 'google/' in x else (1 if 'validate/' in x else 2),
            x
        ))
        merged.extend(sorted_imports)
        merged.append('')
    
    # 6. Concatenate bodies
    for i, parsed in enumerate(parsed_files):
        if parsed['body']:
            # Remove leading empty lines from body
            body_lines = parsed['body']
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            
            # Remove trailing empty lines from body
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            
            # Filter out patterns defined in SKIP_PATTERNS (secondary filter for body content)
            body_lines = [line for line in body_lines 
                         if not any(line.strip().startswith(prefix) for prefix in SKIP_PATTERNS['line_prefixes'])
                         and not any(pattern in line.strip() for pattern in SKIP_PATTERNS['line_contains'])]
            
            # Filter out excluded messages and RPCs
            if exclude_messages or exclude_rpcs:
                body_lines = filter_excluded_definitions(
                    body_lines, 
                    exclude_messages or [], 
                    exclude_rpcs or []
                )
            
            # Remove option blocks from inside RPC methods
            body_lines = remove_options_from_rpc_blocks(body_lines)
            
            # Clean up empty RPC blocks
            body_lines = cleanup_empty_rpc_blocks(body_lines)
            
            if body_lines:
                if i > 0:
                    # Add separator between files
                    merged.append('')
                merged.extend(body_lines)
    
    # Remove trailing empty lines
    while merged and not merged[-1].strip():
        merged.pop()
    
    # Ensure file ends with newline
    return '\n'.join(merged) + '\n'


def sync_module(branch: str, module: str, config: Dict, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Sync a single module.
    Returns (changed, message) tuple.
    """
    print(f"{Colors.CYAN}Processing module: {module}{Colors.RESET}")
    
    # Determine which files to fetch
    if config['files'] == 'all':
        try:
            proto_files = fetch_directory_listing(branch, module)
        except Exception as e:
            return False, f"{Colors.RED}Error: {e}{Colors.RESET}"
    else:
        proto_files = config['files']
    
    print(f"  Files to sync: {', '.join(proto_files)}")
    
    # Fetch all proto files
    fetched_contents = []
    for filename in proto_files:
        try:
            print(f"  Fetching {filename}...", end=' ')
            content = fetch_proto_file(branch, module, filename)
            fetched_contents.append(content)
            print(f"{Colors.GREEN}✓{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗{Colors.RESET}")
            return False, f"{Colors.RED}Error fetching {filename}: {e}{Colors.RESET}"
    
    # Get exclusion lists for this module
    exclude_config = EXCLUDE_LIST.get(module, {})
    exclude_messages = exclude_config.get('messages', [])
    exclude_rpcs = exclude_config.get('rpcs', [])
    
    if exclude_messages or exclude_rpcs:
        print(f"  Applying exclusions: {len(exclude_messages)} messages, {len(exclude_rpcs)} RPCs")
    
    # Merge proto files
    print(f"  Merging {len(fetched_contents)} files...")
    merged_content = merge_proto_files(
        fetched_contents, 
        current_module=module,
        exclude_messages=exclude_messages,
        exclude_rpcs=exclude_rpcs
    )
    
    # Determine output path
    output_path = f"proto/banyandb/v1/banyandb-{module}.proto"
    
    # Check if file exists and compare
    file_exists = os.path.exists(output_path)
    changed = False
    
    if file_exists:
        with open(output_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
        changed = existing_content != merged_content
    else:
        changed = True
    
    if changed:
        print(f"  {Colors.YELLOW}Changes detected{Colors.RESET}")
        
        if not dry_run:
            # Write the merged file
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            status = "updated" if file_exists else "created"
            print(f"  {Colors.GREEN}✓ File {status}: {output_path}{Colors.RESET}")
        else:
            print(f"  {Colors.BLUE}[DRY RUN] Would update: {output_path}{Colors.RESET}")
    else:
        print(f"  {Colors.GREEN}✓ No changes needed{Colors.RESET}")
    
    return changed, output_path


def main():
    parser = argparse.ArgumentParser(
        description='Sync proto files from Apache SkyWalking BanyanDB repository'
    )
    parser.add_argument(
        '--branch',
        default='main',
        help='Branch or tag to sync from (default: main)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without writing files'
    )
    parser.add_argument(
        '--module',
        action='append',
        help='Sync only specific module(s). Can be specified multiple times.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts'
    )
    
    args = parser.parse_args()
    
    # Determine which modules to sync
    modules_to_sync = MODULES
    if args.module:
        modules_to_sync = {k: v for k, v in MODULES.items() if k in args.module}
        if not modules_to_sync:
            print(f"{Colors.RED}Error: No valid modules specified{Colors.RESET}")
            print(f"Valid modules: {', '.join(MODULES.keys())}")
            sys.exit(1)
    
    # Display configuration
    print(f"{Colors.BOLD}=== Proto File Sync ==={Colors.RESET}")
    print(f"Repository: {GITHUB_REPO}")
    print(f"Branch: {args.branch}")
    print(f"Modules: {', '.join(modules_to_sync.keys())}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    # Confirmation prompt
    if not args.force and not args.dry_run:
        response = input(f"{Colors.YELLOW}Proceed with sync? [y/N]: {Colors.RESET}")
        if response.lower() not in ['y', 'yes']:
            print("Cancelled.")
            sys.exit(0)
        print()
    
    # Sync each module
    results = []
    for module, config in modules_to_sync.items():
        changed, message = sync_module(args.branch, module, config, args.dry_run)
        results.append((module, changed, message))
        print()
    
    # Summary
    print(f"{Colors.BOLD}=== Summary ==={Colors.RESET}")
    changed_count = sum(1 for _, changed, _ in results if changed)
    
    for module, changed, message in results:
        status = f"{Colors.YELLOW}CHANGED{Colors.RESET}" if changed else f"{Colors.GREEN}UNCHANGED{Colors.RESET}"
        print(f"  {module}: {status}")
    
    print()
    if args.dry_run:
        print(f"{Colors.BLUE}Dry run complete. {changed_count} file(s) would be updated.{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}Sync complete. {changed_count} file(s) updated.{Colors.RESET}")


if __name__ == '__main__':
    main()

