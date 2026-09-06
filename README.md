# 🎧 StemLab — separador de voz e instrumentos (Google Colab)

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/magoupdown/stemlab-colab/blob/main/StemLab.ipynb)

**👆 Clique no botão acima para abrir o app direto no Google Colab.** Depois rode a célula 1️⃣ (login Google + instalação) e a célula 2️⃣ (abre o aplicativo).

Notebook do Google Colab com **interface de página web** que usa inteligência artificial para separar uma música em faixas:

- 🎤 **Voz + Playback** (2 faixas) — modelo BS-Roformer, o mais preciso para voz. Ideal para karaokê, estudo de canto e playbacks.
- 🥁 **Banda** (4 faixas) — voz, bateria, baixo e outros, com o Demucs afinado (htdemucs_ft).
- 🎸 **Completo** (6 faixas) — voz, bateria, baixo, guitarra, piano e outros (htdemucs_6s).
- ▶ **Fonte**: link do YouTube (vídeo, YouTube Music, Shorts) **ou** arquivo do computador (MP3, WAV, FLAC, M4A, OGG, OPUS, AIFF, MP4/WEBM, até 250 MB).
- 🎛 **Mixer no navegador**: ouça o resultado, silencie (M) ou isole (S) cada faixa, ajuste o volume e compare com o original antes de baixar.
- 💾 **Formatos de saída**: WAV, FLAC ou MP3 320 kbps. Botão "Baixar" por faixa, ZIP com tudo e cópia opcional para o Google Drive.
- ⬇ **Só baixar o áudio** do YouTube, sem separar: MP3, M4A/AAC, OPUS, FLAC, WAV ou original, com escolha de qualidade e capa embutida.
- 🔐 **Login Google obrigatório** e **cookies da conta** para vídeos privados, +18 ou só para membros (salvos no Drive entre sessões).
- 📥 **Fila contínua**: enquanto uma música processa, prepare a próxima. Progresso em tempo real por etapa (baixar, modelo, separar na GPU, exportar), tempo estimado e cancelamento.
- 📱 Responsivo, tema claro/escuro, animações e mensagens de erro traduzidas com orientação do que fazer.

## Como usar

1. Abra o notebook pelo botão acima. Ele já vem com **GPU T4** selecionada (gratuita no Colab).
2. Rode a célula **1️⃣**: faça login na conta Google. A célula instala o `yt-dlp` e o `audio-separator` (1 a 3 minutos).
3. Rode a célula **2️⃣**: o aplicativo aparece abaixo. Cole o link ou envie um arquivo, escolha o modo e clique em **Separar faixas**.
4. Na primeira separação de cada modo, o modelo de IA é baixado (uma vez por sessão). O modelo de voz já começa a baixar em segundo plano assim que o app abre.

Tempo típico na GPU T4 para uma música de 4 minutos: cerca de 4 a 7 minutos no modo Voz + Playback (o BS-Roformer é pesado, mas é o mais preciso).

## Limites e observações

- A separação aceita áudios de **até 25 minutos** (acima disso a memória da GPU gratuita estoura).
- Se o chip do topo mostrar **Sem GPU**, vá em *Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU* e rode as células novamente.
- O YouTube às vezes pede "confirme que você não é um robô" em servidores. Carregar os cookies da sua conta resolve.
- Arquivos temporários ficam em `/content/stemlab` enquanto a sessão estiver ativa. A célula 3️⃣ limpa essa pasta.
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
