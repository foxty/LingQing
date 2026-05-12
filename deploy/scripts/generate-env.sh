#!/bin/bash
# Generate .env file from template by substituting environment variables
# Usage: ./generate-env.sh <template> <output>
#
# Template patterns (both supported):
#   KEY=<env:ENV_VAR-default_value>      (preferred)
#   KEY=<env:ENV_VAR->                   (default is empty string)
#   KEY=<env:ENV_VAR>                    (required, no default)
#   KEY=<secret:...>                     (legacy, backward compatible)
#   - If ENV_VAR exists in environment, use its value
#   - Else if default_value provided (including empty), use it
#   - Else fail with error
#
# Examples:
#   TENANT_APP_DB_PASSWORD=<env:DB_PASSWORD-mydefault>
#   OPTIONAL_TOKEN=<env:OPTIONAL_TOKEN->      (empty default)
#   CORS_ORIGINS=<env:CORS_ORIGINS-http://localhost>

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

template=${1}
output=${2}

# Validate parameters
if [[ -z "$template" ]] || [[ -z "$output" ]]; then
    echo -e "${RED}Error: Both template and output paths are required${NC}"
    echo "Usage: $0 <template> <output>"
    exit 1
fi

# Check template exists
if [[ ! -f "$template" ]]; then
    echo -e "${RED}Error: Template file not found: $template${NC}"
    exit 1
fi

echo -e "${YELLOW}Generating env file from template...${NC}"
echo "Template: $template"
echo "Output: $output"

# Copy template to output
cp "$template" "$output"

# Process each line looking for:
#   <env:KEY-default>
#   <env:KEY->
#   <env:KEY>
# and legacy <secret:...> variants
errors=0
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$line" ]] && continue
    
    # Check if line contains <env:...> or legacy <secret:...>
    # Optional default segment syntax: -default_value
    if [[ $line =~ \<(env|secret):([A-Za-z_][A-Za-z0-9_]*)(-([^\>]*))?\> ]]; then
        placeholder_kind="${BASH_REMATCH[1]}"
        env_key="${BASH_REMATCH[2]}"
        default_segment="${BASH_REMATCH[3]}"
        default_value="${BASH_REMATCH[4]}"
        
        # Get value from environment or use default.
        # <env:VAR-default> and <env:VAR-> use '-' default semantics (only when unset).
        # <env:VAR> is required and must be non-empty.
        env_value="${!env_key-}"
        if [[ -n "$default_segment" ]]; then
            env_value="${!env_key-$default_value}"
        elif [[ -z "$env_value" ]]; then
            echo -e "${RED}✗ Missing required env var: $env_key (no default provided)${NC}"
            errors=$((errors + 1))
            continue
        fi
        
        # Replace in output file (escape special chars for sed)
        pattern="<${placeholder_kind}:${env_key}${default_segment}>"
        escaped_pattern=$(printf '%s\n' "$pattern" | sed -e 's/[\/&]/\\&/g')
        escaped_value=$(printf '%s\n' "$env_value" | sed -e 's/[\/&]/\\&/g')
        
        sed -i.bak "s|${escaped_pattern}|${escaped_value}|g" "$output"
        rm -f "${output}.bak"
    fi
done < "$template"

# Check for any remaining unsubstituted placeholders (excluding commented lines)
unsubstituted=$(grep -Ev '^\s*#' "$output" | grep -E '<(env|secret):' || true)
if [[ -n "$unsubstituted" ]]; then
    echo -e "${RED}Error: Unsubstituted placeholders found in output:${NC}"
    echo "$unsubstituted" | sed "s/^/  /"
    errors=$((errors + 1))
fi

# Exit with error if any env vars were missing
if [[ $errors -gt 0 ]]; then
    echo -e "${RED}Error: Failed to generate env file ($errors issue(s))${NC}"
    rm -f "$output"
    exit 1
fi

echo -e "${GREEN}✓ Successfully generated $output${NC}"
