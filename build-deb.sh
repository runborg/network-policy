#!/bin/bash
# Build script for network-policy Debian package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "Network Policy - Debian Package Builder"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -f "debian/control" ]; then
    echo "Error: debian/control not found. Run this script from the repository root."
    exit 1
fi

# Check for required tools
MISSING_TOOLS=()
for tool in dpkg-buildpackage debuild; do
    if ! command -v $tool &> /dev/null; then
        MISSING_TOOLS+=($tool)
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "Error: Missing required tools: ${MISSING_TOOLS[*]}"
    echo "Install with: sudo apt install build-essential devscripts debhelper"
    exit 1
fi

# Validate configuration if example exists
if [ -f "usr/share/doc/network-policy/example-config.toml" ]; then
    echo "Validating example configuration..."
    if command -v python3 &> /dev/null; then
        export PYTHONPATH="$SCRIPT_DIR/usr/local/lib/network-policy:$PYTHONPATH"
        python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/usr/local/lib/network-policy')
try:
    from config import load_config
    config = load_config('$SCRIPT_DIR/usr/share/doc/network-policy/example-config.toml')
    print('✓ Configuration validation passed')
except Exception as e:
    print(f'✗ Configuration validation failed: {e}')
    sys.exit(1)
" || {
            echo "Warning: Configuration validation failed, but continuing build..."
        }
    fi
fi

echo ""
echo "Building Debian package..."
echo ""

# Build package
dpkg-buildpackage -us -uc -b

echo ""
echo "========================================"
echo "Build completed successfully!"
echo "========================================"
echo ""
echo "Package location:"
ls -lh ../*.deb 2>/dev/null || echo "No .deb files found in parent directory"
echo ""
echo "To install:"
echo "  sudo dpkg -i ../network-policy_*.deb"
echo "  sudo apt-get install -f  # Fix dependencies if needed"
echo ""
