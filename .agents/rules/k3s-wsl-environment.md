# Regras de Execução e Ambiente: WSL Ubuntu & K3s

## Diretiva Primária
Qualquer comando executado via ferramenta `run_command` DEVE ser roteado obrigatoriamente através do WSL na distribuição `Ubuntu`.

## Comandos Permitidos vs. Proibidos

- **PROIBIDO**: Executar comandos nativos no PowerShell/CMD que assumam binários Linux locais do Windows (ex: `kubectl apply ...`, `helm install ...`, `bash ...`).
- **OBRIGATÓRIO**: Prefixar com `wsl -d Ubuntu -- <comando>` ou encapsular com `wsl -d Ubuntu -- bash -c "<script>"`.

## Diretório de Trabalho (CWD)
- Ao executar comandos no WSL, o diretório de trabalho deve respeitar o diretório atual do repositório:
  `cd $(wslpath -u "$(pwd)")`

## Mitigação de Falhas e Validação Contínua
1. Antes de iniciar qualquer pipeline ou aplicação de manifestos/charts Helm, valide o estado do cluster:
   `wsl -d Ubuntu -- kubectl get nodes`
2. Certifique-se de que manifestos do Kubernetes utilizem storage classes e recursos suportados pelo k3s (`local-path`, etc.).
3. Em caso de dúvidas sobre portas ou exposição de serviços, consulte as diretrizes em `.agents/instructions/`.
