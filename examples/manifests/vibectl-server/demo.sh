#!/usr/bin/env bash
set -euo pipefail

echo "🎯 vibectl-server Kubernetes Demo Selector"
echo "============================================"
echo ""
echo "Choose your certificate management approach:"
echo ""
echo "1. 🏭 CA Management Demo (Private Certificate Authority)"
echo "   • Best for: Internal networks, air-gapped environments"
echo "   • Features: Private CA, self-contained, no internet required"
echo "   • Namespace: vibectl-server-ca"
echo ""
echo "2. 🔰 ACME Management Demo (TLS-ALPN-01, Let's Encrypt Compatible)"
echo "   • Best for: Internet-facing deployments, automatic renewal"
echo "   • Features: Pebble test server, TLS-ALPN-01 challenges, simplified deployment"
echo "   • Benefits: Single container, no HTTP port, secure challenge handling"
echo "   • Namespace: vibectl-server-acme"
echo ""
echo "3. 🌐 ACME Management Demo (HTTP-01, Let's Encrypt Compatible)"
echo "   • Best for: Testing HTTP-01 challenge flow, traditional web deployments"
echo "   • Features: Pebble test server, HTTP-01 challenges, dual-port deployment"
echo "   • Benefits: Standard HTTP challenge, easier debugging, web-compatible"
echo "   • Namespace: vibectl-server-acme-http"
echo ""
echo "4. 🧹 Cleanup all demos"
echo ""
echo "For detailed comparison, see docs/llm-proxy-server.md"
echo ""

# Check that we're in the project root
if [[ ! -f "pyproject.toml" || ! -d "vibectl" ]]; then
    echo "❌ Error: Please run this script from the project root:"
    echo "   ./examples/manifests/vibectl-server/demo.sh"
    echo ""
    echo "Current directory: $(pwd)"
    exit 1
fi

read -p "Select option (1-4): " choice

case $choice in
    1)
        echo ""
        echo "🏭 Starting CA Management Demo..."
        echo "================================="
        exec ./examples/manifests/vibectl-server/demo-ca.sh
        ;;
    2)
        echo ""
        echo "🔰 Starting ACME Management Demo (TLS-ALPN-01)..."
        echo "==============================================="
        exec ./examples/manifests/vibectl-server/demo-acme.sh
        ;;
    3)
        echo ""
        echo "🌐 Starting ACME Management Demo (HTTP-01)..."
        echo "============================================"
        exec ./examples/manifests/vibectl-server/demo-acme-http.sh
        ;;
    4)
        echo ""
        echo "🧹 Cleaning up all demo environments..."
        echo "======================================"
        echo ""
        echo "🔍 Checking for existing demo namespaces..."

        # Check for CA demo
        if kubectl get namespace vibectl-server-ca >/dev/null 2>&1; then
            echo "🗑️  Removing CA demo namespace..."
            kubectl delete namespace vibectl-server-ca
            echo "✅ CA demo cleaned up"
        else
            echo "ℹ️  No CA demo namespace found"
        fi

        # Check for ACME demo (TLS-ALPN-01)
        if kubectl get namespace vibectl-server-acme >/dev/null 2>&1; then
            echo "🗑️  Removing ACME (TLS-ALPN-01) demo namespace..."
            kubectl delete namespace vibectl-server-acme
            echo "✅ ACME (TLS-ALPN-01) demo cleaned up"
        else
            echo "ℹ️  No ACME (TLS-ALPN-01) demo namespace found"
        fi

        # Check for ACME HTTP-01 demo
        if kubectl get namespace vibectl-server-acme-http >/dev/null 2>&1; then
            echo "🗑️  Removing ACME (HTTP-01) demo namespace..."
            kubectl delete namespace vibectl-server-acme-http
            echo "✅ ACME (HTTP-01) demo cleaned up"
        else
            echo "ℹ️  No ACME (HTTP-01) demo namespace found"
        fi

        # Clean up temporary files
        echo ""
        echo "🧹 Cleaning up temporary files..."
        rm -f /tmp/vibectl-demo-ca-bundle.crt
        rm -f /tmp/vibectl-demo-acme-cert.pem
        rm -f /tmp/vibectl-demo-pebble-ca-http.crt
        echo "✅ Temporary files cleaned up"

        echo ""
        echo "🎉 All demo environments cleaned up successfully!"
        echo ""
        ;;
    *)
        echo ""
        echo "❌ Invalid option. Please select 1-4."
        echo ""
        exec "$0"
        ;;
esac
