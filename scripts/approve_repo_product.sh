#!/usr/bin/env bash
# ==============================================================================
# Wrapper CI/CD de Aprovação / Ativação de Produto de Dados (Governance as Code)
# ==============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REPO_TARGET="${1:-}"

if [ -z "${REPO_TARGET}" ]; then
    echo "Uso: $0 <caminho_do_repositorio>"
    echo "Exemplo: $0 repos/sist-cdb"
    exit 1
fi

shift
export PYTHONUNBUFFERED=1
python3 -u "${SCRIPT_DIR}/approve_data_product_ci.py" "${REPO_TARGET}" "$@"
