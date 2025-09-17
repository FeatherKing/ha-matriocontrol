#!/bin/bash

# Setup script to install git hooks for version validation

echo "🔧 Setting up git hooks for version validation..."

# Create .githooks directory if it doesn't exist
mkdir -p .githooks

# Make the pre-commit hook executable
chmod +x .githooks/pre-commit

# Configure git to use the hooks directory
git config core.hooksPath .githooks

echo "✅ Git hooks configured successfully!"
echo ""
echo "The following hooks are now active:"
echo "  - pre-commit: Ensures manifest.json version is updated when integration files change"
echo ""
echo "To disable the hooks temporarily, run:"
echo "  git config core.hooksPath .git/hooks"
echo ""
echo "To re-enable the hooks, run:"
echo "  git config core.hooksPath .githooks"
