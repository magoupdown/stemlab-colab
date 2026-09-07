# 🎧 StemLab — separador de voz e instrumentos (Google Colab)

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/magoupdown/stemlab-colab/blob/main/StemLab.ipynb)

**Versão atual: 2.0 RC1.** Correções de validação de arquivos, uploads, cancelamento, modelos e mixer. Consulte o [relatório de alterações e testes](CHANGELOG.md). Para migrar da versão anterior, abra uma sessão nova. Os 30 testes locais usam separação simulada; GPU, YouTube e Drive ainda precisam de validação de integração no Colab.

**👆 Clique no botão acima para abrir o app direto no Google Colab.** Depois rode a célula 1️⃣ (login Google + instalação) e a célula 2️⃣ (abre o aplicativo).

Notebook do Google Colab com **interface de página web** que usa inteligência artificial para separar uma música em faixas:

- 🎤 **Voz + Playback** (2 faixas) — modelo BS-Roformer, voltado à separação de voz. Ideal para karaokê, estudo de canto e playbacks.
- 🥁 **Banda** (4 faixas) — voz, bateria, baixo e outros, com o Demucs afinado (htdemucs_ft).
- 🎸 **Completo** (6 faixas) — voz, bateria, baixo, guitarra, piano e outros (htdemucs_6s).
- ▶ **Fonte**: link do YouTube (vídeo, YouTube Music, Shorts) **ou** arquivo do computador (MP3, WAV, FLAC, M4A, OGG, OPUS, AIFF, MP4/WEBM, até 1 GB (1024 MB)).
- 🎛 **Mixer no navegador**: ouça o resultado, silencie (M) ou isole (S) cada faixa, ajuste o volume e compare com o original antes de baixar.
- 💾 **Formatos de saída**: WAV, FLAC ou MP3 320 kbps. Botão "Baixar" por faixa, ZIP com tudo e cópia opcional para o Google Drive.
- ⬇ **Só baixar o áudio** do YouTube, sem separar: MP3, M4A/AAC, OPUS, FLAC, WAV ou original, com escolha de qualidade e capa embutida.
- 🔐 **Login Google obrigatório** e **cookies da conta** para vídeos privados, +18 ou só para membros (salvos no Drive entre sessões).
- 📥 **Fila contínua**: enquanto uma música processa, prepare a próxima. Progresso em tempo real por etapa (baixar, modelo, separar na GPU, exportar), tempo estimado e cancelamento.
- 📱 Responsivo, tema claro/escuro, animações e mensagens de erro traduzidas com orientação do que fazer.

## Como usar

1. Abra o notebook pelo botão acima. Ele solicita **GPU T4**, cuja disponibilidade depende do Colab.
2. Rode a célula **1️⃣**: faça login na conta Google. A célula instala o `yt-dlp` e o `audio-separator` (1 a 3 minutos).
3. Rode a célula **2️⃣**: o aplicativo aparece abaixo. Cole o link ou envie um arquivo, escolha o modo e clique em **Separar faixas**.
4. Na primeira separação de cada modo, o modelo de IA é baixado (uma vez por sessão). O modelo de voz já começa a baixar em segundo plano assim que o app abre.

O tempo depende do modelo, da duração do áudio e dos recursos disponíveis. A revisão 2.0 RC1 ainda não foi cronometrada em uma GPU real.

## Limites e observações

- A separação aceita áudios de **até 25 minutos** (limite operacional; não garante memória suficiente para todos os modelos).
- Se o chip do topo mostrar **Sem GPU**, vá em *Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU* e rode as células novamente.
- O YouTube às vezes pede "confirme que você não é um robô" em servidores. Cookies de uma conta com acesso podem ajudar, mas não garantem que o servidor aceite a conexão.
- Arquivos temporários ficam em `/content/stemlab` enquanto a sessão estiver ativa. A célula 3️⃣ exige marcar `confirmar_limpeza` e limpa áudios, resultados e histórico somente sem tarefas ativas; preserva modelos, cookies e cópias no Drive.
- Uso pessoal. Respeite os termos do YouTube e os direitos dos criadores.

## Estrutura

```
stemlab-colab/
├── StemLab.ipynb           ← o notebook pronto para o Colab
├── README.md
└── src/
    ├── backend.py          ← funções Python (yt-dlp, upload, audio-separator, fila, servidor de prévias)
    ├── app.html            ← interface (HTML/CSS/JS) chamando o Python pela ponte do Colab
    ├── build_notebook.py   ← gera o .ipynb a partir dos dois arquivos acima
    └── dev_server.py       ← servidor local para testar a interface fora do Colab (STEMLAB_MOCK=1 simula a IA)
```

Para editar, altere `src/backend.py` ou `src/app.html` e rode:

```bash
python src/build_notebook.py .
```

Modelos usados via [audio-separator](https://github.com/nomadkaraoke/python-audio-separator): `model_bs_roformer_ep_317_sdr_12.9755.ckpt`, `htdemucs_ft.yaml` e `htdemucs_6s.yaml`.

---

**Desenvolvido por [@emersonms](https://github.com/magoupdown) - 2026**



## Mixagem personalizada

Após separar, use **M** para excluir qualquer faixa, **S** para ouvir e incluir somente as faixas em Solo, e os volumes para ajustar a combinação. Em **Renderizar mixagem**, escolha WAV, FLAC ou MP3 e gere um único acompanhamento. Por exemplo, voz e piano, banda sem baixo ou somente instrumentos sem voz. O Original é apenas uma referência de escuta e nunca é incluído.

A renderização usa os arquivos das faixas, não as prévias MP3 do mixer. Os arquivos separados continuam disponíveis. A mixagem entra na fila, pode ser cancelada e tem opção de cópia no Drive. Depois de pronta, use **Voltar às faixas** para criar outra combinação. O formato escolhido não recupera qualidade perdida em fontes já comprimidas.

## Tela inteira e smartphone

Use **Tela inteira**, no topo, para expandir a interface; use **Restaurar** ou Esc para voltar. Quando o navegador ou a permissão do Colab não permitir tela inteira, o aplicativo amplia dentro da célula, com a mesma opção de restauração. A reprodução e as tarefas continuam na sessão atual.

O layout adapta etapas, botões, mixer e controles de mixagem a telas estreitas, com alvos de toque maiores. No smartphone, abra pelo mesmo link do Colab e execute as células 1 e 2. A disponibilidade de tela inteira depende do navegador e das permissões da página.
