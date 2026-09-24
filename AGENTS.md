# Diretrizes e Instruções do Projeto para Agentes de IA

> **ATENÇÃO AGENTE DE IA**: Este arquivo define as restrições arquiteturais e operacionais obrigatórias para este repositório. Toda e qualquer ação de execução, criação de recursos ou automação deve seguir estritamente as regras abaixo.

---

## 1. Ambiente de Execução e Host

- **Host SO**: Windows 11 / Windows com Rancher Desktop instalado.
- **Cluster Kubernetes**: **k3s** rodando no ambiente WSL (versão k3s v1.36+).
- **Distribuição WSL Padrão**: **Ubuntu** (WSL 2).
- **Mapeamento de Caminho no WSL**:
  - Windows: `<workspace-root>`
  - WSL Ubuntu: `/mnt/c/<caminho-para-o-workspace>` (resolvido dinamicamente via `wslpath -u "$(pwd)"`)

---

## 2. Regra de Ouro: Execução de Comandos

> [!CAUTION]
> **NUNCA execute comandos de build, kubectl, helm, scripts ou ferramentas CLI diretamente no shell nativo do Windows (PowerShell/CMD) sem passar pelo WSL Ubuntu.**

### Como executar comandos:
Sempre direcione a execução através da distribuição `Ubuntu` do WSL:
```powershell
wsl -d Ubuntu -- bash -c "<comando>"
```
Ou ao interagir com ferramentas CLI (como `kubectl`, `helm`, `docker`, etc.):
```powershell
wsl -d Ubuntu -- kubectl <subcomando>
```

Se for executar múltiplos comandos sequenciais ou scripts que dependem de variáveis de ambiente do Linux:
```powershell
wsl -d Ubuntu -- bash -c "cd \$(wslpath -u \"\$(pwd)\") && <comandos>"
```

---

## 3. Verificação de Padrões e Mitigação de Desvios (Pre-Flight Checks)

Ao iniciar qualquer tarefa neste projeto ou antes de aplicar manifestos e operações no cluster:
1. **Verificar Conexão e Contexto do Cluster**:
   ```bash
   wsl -d Ubuntu -- kubectl cluster-info
   wsl -d Ubuntu -- kubectl get nodes
   ```
2. **Checar Namespaces e Pods Existentes**:
   ```bash
   wsl -d Ubuntu -- kubectl get namespaces
   ```
3. **Não alterar contextos externos**:
   O host possui o Rancher Desktop instalado. Certifique-se de que o contexto em uso no WSL Ubuntu seja o cluster k3s local pretendido e não conflite com outras configurações ou contextos externos.

---

## 4. Diretório de Instruções e Documentação do Projeto

Instruções detalhadas, runbooks e especificações técnicas estão organizados em:
- [`.agents/rules/k3s-wsl-environment.md`](.agents/rules/k3s-wsl-environment.md): Regras de comportamento e restrições automáticas do agente.
- [`.agents/instructions/k8s-cluster.md`](.agents/instructions/k8s-cluster.md): Detalhes técnicos da infraestrutura k3s no WSL.
- [`.agents/instructions/openmetadata-standards.md`](.agents/instructions/openmetadata-standards.md): Padrões de implantação do OpenMetadata e seus componentes (Elasticsearch/OpenSearch, PostgreSQL/MySQL, Airflow/Ingestion).
