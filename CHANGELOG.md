## Relatório da revisão | StemLab 2.0 RC1

Versão candidata para teste, preparada em 07/09/2026. Mantém o aplicativo, o mixer, os modos de 2, 4 e 6 faixas, os downloads e a integração com Google Drive.

### Como testar

1. Abra o [StemLab no Colab](https://colab.research.google.com/github/magoupdown/stemlab-colab/blob/main/StemLab.ipynb).
2. Use uma sessão nova. Em **Ambiente de execução > Alterar o tipo de ambiente de execução**, selecione T4 GPU se disponível.
3. Execute a célula 1 e conclua a autenticação. Aguarde a instalação terminar.
4. Execute a célula 2. Comece com um arquivo local curto e o modo Voz + Playback.
5. Confira as faixas, o mixer, os formatos de saída e o ZIP. Depois teste um link do YouTube ao qual você tenha acesso.
6. Para reabrir a interface na mesma sessão, execute somente a célula 2. Para atualizar dependências, reinicie a sessão antes da célula 1.
7. A célula 3 exige marcar confirmar_limpeza e só limpa os arquivos temporários quando não há tarefas ativas. Depois dela, execute a célula 2 para renovar a interface.

### Problemas encontrados e correções implementadas

| Área | Problema anterior | Alteração |
|---|---|---|
| Arquivos | A comparação textual de prefixos aceitava pastas vizinhas e links simbólicos externos | Validação com caminho real e diretório comum nos downloads, prévias e servidor HTTP |
| HTTPS | Verificação de certificados desativada no yt-dlp | Verificação reativada |
| Links | Qualquer domínio contendo “youtube” era aceito | Lista explícita de domínios e validação do identificador de 11 caracteres |
| Upload | O bloco era gravado antes de verificar o limite | Base64 estrito e limite por bloco e por arquivo verificado antes da gravação |
| Upload incompleto | Arquivos incompletos podiam permanecer sem referência | Exclusão do arquivo incompleto na finalização |
| Cookies | HttpOnly era ignorado na contagem; importação sem validação estrutural | Validação Netscape, limite de tamanho, filtro de domínios e leitura de HttpOnly |
| Cookies locais | Permissões padrão do sistema | Permissão 0600 após importação local |
| Estado | Reexecutar o aplicativo descartava referências às tarefas e à fila | Estado, fila, servidor e trabalhador reutilizados na mesma sessão |
| Modelos | Download antecipado e separação podiam gravar simultaneamente | Exclusão mútua entre pré-download e separação |
| Modelos prontos | Presença de arquivo com prefixo semelhante indicava sucesso | Estado pronto registrado após operação bem-sucedida nesta sessão |
| Cancelamento | Leitura bloqueante dos logs e conversões sem cancelamento | Leitor separado, processo cancelável e encerramento com coleta do processo |
| Prazos | Conversões e separação podiam aguardar indefinidamente | Prazo de 30 minutos para conversões próprias e duas horas para separação |
| Limpeza | A célula opcional apagava arquivos mesmo durante processamento | Opção confirmar_limpeza desativada por padrão e rotina que recusa limpeza com tarefas em andamento |
| Drive | Nomes repetidos sobrescreviam exportações de outras tarefas | Subpasta com identificador da tarefa |
| Prévia | Existência do arquivo era interpretada como sucesso do FFmpeg | Verificação do retorno; prévia defeituosa removida e aviso exibido |
| Mixer | Falhas de reprodução eram ignoradas e o player mostrava “tocando” | Verificação das promessas e espera das prévias antes de reproduzir |
| Mixer encerrado | Retorno tardio de download podia recarregar áudio descartado | Estado de descarte interrompe carregamentos tardios |
| HTTP Range | Intervalos inválidos podiam gerar respostas inconsistentes | Validação de intervalos simples, abertos e sufixos; erro 416 para inválidos |
| Instalação | Falhas no instalador Deno eram ocultadas e FFmpeg só era mencionado | Instalação verificada, prazos e verificação do comando audio-separator |
| Diagnóstico | Versões pouco visíveis | Registro das versões instaladas ao final da preparação |
| Download | Erros de pós-processamento podiam ser ignorados | yt-dlp configurado para propagar falhas |
| Áudio intermediário | Conversão intermediária em PCM de 16 bits | PCM de 24 bits para reduzir quantização adicional; não recupera informação perdida |

### Verificação realizada

**30 verificações locais aprovadas**, além da compilação das células Python e análise de sintaxe do JavaScript com Node.

Foram verificados: URLs válidos e inválidos; bloqueio de travessia de diretórios e links simbólicos; importação HttpOnly; permissões dos cookies; rejeição de domínio alheio; limites de upload e Base64 inválido; descarte de upload incompleto; cancelamento de processo silencioso; fluxo de upload, fila, exportação e ZIP nos três modos; seis casos HTTP Range; limpeza com e sem tarefa ativa.

Nos fluxos de exportação, a separação foi **simulada explicitamente**, usando filtros e um sinal de teste de um segundo. O FFmpeg, o servidor HTTP, os arquivos exportados e os ZIPs foram executados de fato. A ponte Colab e o módulo yt-dlp foram substituídos por objetos de teste. Isso valida o fluxo de arquivos, mas não comprova a qualidade dos modelos nem a integração externa.

**Não executado neste ambiente:** instalação integral em Colab, autenticação Google, acesso ao YouTube, persistência no Drive, inferência real em GPU e interação visual no navegador. A versão recebe RC1 por esses testes de integração ainda dependerem do Colab.

### Limitações e próximos aperfeiçoamentos

- O mixer usa elementos de áudio independentes com correção periódica de posição. Não oferece sincronismo de amostra para avaliação de fase. Uma próxima versão pode usar Web Audio e buffers alinhados, considerando o custo de memória de músicas longas.
- As dependências são atualizadas na preparação. Suas versões são registradas, mas ainda não há um conjunto fixado e validado numa sessão real do Colab. Esse congelamento deve vir depois do teste de integração.
- O cancelamento das conversões próprias e do separador é monitorado. No yt-dlp, depende dos pontos de verificação e hooks; uma operação de rede ou pós-processamento interna pode demorar a devolver o controle.
- O download antecipado do modelo tem prazo próprio e continua mesmo se uma tarefa que o aguardava for cancelada.
- O pacote CPU do audio-separator foi mantido. Os modelos PyTorch dependem da instalação Torch/CUDA, e a detecção de GPU não comprova aceleração ONNX. Conferir o uso real de GPU durante o teste.
- A persistência de cookies no Drive foi mantida. A permissão 0600 se aplica à cópia local; ela não substitui as permissões de compartilhamento do Drive.
- As estimativas de tempo são aproximadas. O limite de duração não garante que um modelo caiba na memória disponível.
- FLAC e WAV preservam o sinal recebido na conversão, mas não transformam áudio comprimido do YouTube em uma fonte sem perdas.

### Documentação consultada

- [Audio Separator: instalação e opções da linha de comando](https://github.com/nomadkaraoke/python-audio-separator). Confirma os parâmetros usados pelo separador e a distinção entre ambientes de execução.
- [yt-dlp: configuração de JavaScript externo](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Documenta a necessidade de runtime compatível e o pacote de scripts incluído em yt-dlp[default].


## Mixagem personalizada de faixas

- Novo botão **Renderizar mixagem**, com WAV, FLAC e MP3 320 kbps.
- Qualquer combinação das faixas separadas, respeitando M, Solo e volumes; a faixa Original nunca entra no arquivo.
- Resumo das faixas incluídas antes de renderizar; rejeição de seleção vazia ou volumes inválidos.
- Renderização com FFmpeg a partir das faixas exportadas, soma sem normalização automática e limitador de picos com compensação de latência.
- Tarefa na fila, progresso de codificação, cancelamento, cópia opcional no Drive e retorno às faixas separadas.
- Verificação local: 15 casos de backend com arquivos reais e testes de seleção do mixer. Sinais em frequências distintas confirmam exclusão da faixa silenciada e proporção de volumes nos três formatos. WAV/FLAC também foram comparados amostra a amostra com a soma esperada. A inferência de IA e a interface dentro do Colab não foram executadas neste teste.
