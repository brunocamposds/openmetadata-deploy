# Guia de Infraestrutura: K3s no WSL & Integração com Host

## Visão Geral do Ambiente

```
+-----------------------------------------------------------+
| Windows Host (Rancher Desktop instalado)                  |
| Workspace: C:\path\to\workspace                           |
+-----------------------------------------------------------+
                          |
                          v
+-----------------------------------------------------------+
| WSL 2 - Distribuição Ubuntu (Ativa e Padrão)              |
| Montagem: /mnt/c/path/to/workspace                        |
|                                                           |
| +-------------------------------------------------------+ |
| | Cluster K3s (v1.30+ - Control-plane local)            | |
| | StorageClass: local-path (rancher.io/local-path)     | |
| | CLI: kubectl, helm v4+                                | |
| +-------------------------------------------------------+ |
+-----------------------------------------------------------+
```

## Configuração do Cluster K3s

- **Node(s)**: Nó de control-plane local (Ready, k3s).
- **StorageClass Padrão**: `local-path` (`rancher.io/local-path`, `WaitForFirstConsumer`).
- **Helm**: Instalado na distribuição Ubuntu.
- **Kubeconfig**: Configurado e acessível nativamente pelo ambiente Ubuntu.

## Padrão Obrigatório de Execução

Todos os comandos de terminal devem ser executados pelo agente chamando o WSL Ubuntu:

```powershell
# Execução simples de kubectl
wsl -d Ubuntu -- kubectl get pods -A

# Execução no diretório do projeto
wsl -d Ubuntu -- bash -c "cd \$(wslpath -u \"\$(pwd)\") && <comando>"

# Execução de Helm
wsl -d Ubuntu -- helm list -A
```

## Checklist Pré-Execução (Mitigação de Erros)

Antes de realizar deploys ou alterações no cluster:
1. `wsl -d Ubuntu -- kubectl get nodes` (verificar se o nó está `Ready`).
2. `wsl -d Ubuntu -- kubectl config current-context` (garantir que está no contexto correto).
3. `wsl -d Ubuntu -- df -h` (validar se há espaço em disco suficiente no WSL).
