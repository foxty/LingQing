#!/bin/bash
# Build JavaScript SDK from shared source and output to routers/sdk for serving
# This script ONLY builds the frontend JS SDK, not the Python SDK.

set -e

# Get project root (parent of scripts directory)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Building LingQing JavaScript SDK..."
echo "Project root: $PROJECT_ROOT"

# Source and destination paths
SOURCE_DIR="$PROJECT_ROOT/apps/shared/sdk/js-api"
DEST_DIR="$PROJECT_ROOT/apps/tenant_app_service/routers/sdk"

echo "Source: $SOURCE_DIR/src/lq-sdk.v1.0.ts"
echo "Dest: $DEST_DIR/lq-sdk.v1.0.js"

# Check source exists
if [ ! -f "$SOURCE_DIR/src/lq-sdk.v1.0.ts" ]; then
    echo "Error: Source file not found at $SOURCE_DIR/src/lq-sdk.v1.0.ts"
    exit 1
fi

# Install dependencies if needed
cd "$SOURCE_DIR"
if [ ! -d "node_modules" ]; then
    echo "Installing TypeScript and esbuild..."
    npm install
fi

# Clean destination directory (remove old artifacts)
echo "Cleaning destination..."
rm -rf "$DEST_DIR/components"
rm -f "$DEST_DIR"/*.d.ts "$DEST_DIR"/*.d.ts.map

# Bundle with esbuild (includes all components in single file)
echo "Bundling SDK with esbuild..."
npx esbuild src/lq-sdk.v1.0.ts \
    --bundle \
    --format=iife \
    --platform=browser \
    --target=es2020 \
    --outfile="$DEST_DIR/lq-sdk.v1.0.js"

# Generate unified declaration file (all types inlined, no imports)
echo "Generating unified type declarations..."

# Step 1: Generate declarations to temp directory
TEMP_DIR=$(mktemp -d)
npx tsc --emitDeclarationOnly --declaration --declarationMap false --outDir "$TEMP_DIR"

# Step 2: Concatenate all .d.ts files into one (main + components)
cat "$TEMP_DIR/lq-sdk.v1.0.d.ts" > "$DEST_DIR/lq-sdk.v1.0.d.ts"
for component_dts in "$TEMP_DIR"/components/*.d.ts; do
    if [ -f "$component_dts" ]; then
        echo "" >> "$DEST_DIR/lq-sdk.v1.0.d.ts"
        cat "$component_dts" >> "$DEST_DIR/lq-sdk.v1.0.d.ts"
    fi
done

# Step 3: Remove import/re-export statements and inline the types
# This makes the .d.ts self-contained for agent consumption
python3 << PYEOF
import re

dts_file = "$DEST_DIR/lq-sdk.v1.0.d.ts"
with open(dts_file, 'r') as f:
    lines = f.readlines()

# Filter out import/export-from lines
cleaned_lines = []
for line in lines:
    stripped = line.strip()
    # Skip import statements referencing components
    if stripped.startswith('import ') and './components/' in stripped:
        continue
    # Skip export ... from statements referencing components  
    if (stripped.startswith('export {') or stripped.startswith('export type {')) and './components/' in stripped:
        continue
    cleaned_lines.append(line)

with open(dts_file, 'w') as f:
    f.writelines(cleaned_lines)

print('✓ Declarations inlined successfully')
PYEOF

# Cleanup temp directory
rm -rf "$TEMP_DIR"

echo "✓ SDK built successfully"
echo "  Output: $DEST_DIR/lq-sdk.v1.0.js"
echo "  Declarations: $DEST_DIR/lq-sdk.v1.0.d.ts (self-contained, no imports)"
