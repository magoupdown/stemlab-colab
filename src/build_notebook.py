# Monta o notebook StemLab.ipynb a partir de backend.py + app.html
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)
os.makedirs(OUT_DIR, exist_ok=True)

backend = open(os.path.join(HERE, 'backend.py'), encoding='utf-8').read()
app_html = open(os.path.join(HERE, 'app.html'), encoding='utf-8').read()
assert '"""' not in app_html, 'app.html não pode conter aspas triplas'

INTRO_MD = '# 🎧 StemLab 2.0 RC1 | separador de voz e instrumentos\n\nCole um **link do YouTube** (ou envie um arquivo do computador) e a inteligência artificial separa a música em **voz, playback, bateria, baixo, guitarra e piano**. Ouça o resultado em um **mixer** dentro da página e baixe cada faixa em WAV, FLAC ou MP3. Também dá para **baixar só o áudio** do YouTube em vários formatos e qualidades.\n\n**Como usar (2 cliques):**\n\n1. Rode a célula **1️⃣** — faça login na conta Google (obrigatório). Ela instala as dependências. O modelo começa a ser baixado quando o aplicativo abre.\n2. Rode a célula **2️⃣** — o aplicativo aparece logo abaixo. Cole o link e siga as etapas.\n\n> 💡 Ou use **Ambiente de execução ▸ Executar tudo** (`Ctrl+F9`).\n\n> ⚡ **O notebook solicita uma GPU T4, mas a disponibilidade depende do Colab.** Se o chip no topo do app mostrar *Sem GPU*, vá em **Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU** e rode as células de novo.\n\n**Vídeos privados, +18 ou só para membros:** dentro do app, abra a seção *Cookies da sua conta* e carregue o `cookies.txt` exportado do navegador uma única vez. Com o Drive conectado ele fica salvo em `Meu Drive/StemLab/cookies.txt`.\n\n> ⚠️ Uso **pessoal**. Respeite os termos do YouTube e os direitos autorais dos criadores. Nunca compartilhe seu arquivo de cookies.\n\n---\n*Desenvolvido por **@emersonms** - 2026*\n\n**Versão candidata revisada:** veja o relatório técnico ao final. Use uma sessão nova ao substituir a versão anterior. A qualidade de separação depende da gravação e do modelo; as faixas podem conter resíduos de outros instrumentos.\n'

SETUP_PY = '#@title 1️⃣ Preparar o ambiente e entrar com a conta Google  { display-mode: "form" }\n#@markdown Clique no ▶ à esquerda. Uma janela do Google vai pedir autorização — isso é obrigatório para usar o app. A instalação leva de 1 a 3 minutos.\nconectar_google_drive = True  #@param {type:"boolean"}\n#@markdown *Com o Drive conectado, os cookies ficam salvos entre sessões e as faixas podem ser copiadas para o Drive.*\n\nimport os, sys, shutil, subprocess, json, time\nif globals().get(\'_STEMLAB_STATE\'):\n    raise RuntimeError(\'O ambiente já foi preparado. Para atualizar dependências, reinicie a sessão. Para reabrir a interface, execute somente a célula 2.\')\nfrom IPython.display import HTML, display, clear_output\n\ndef _box(msg, kind=\'info\'):\n    cor = {\'info\': \'#3b82f6\', \'ok\': \'#22c55e\', \'warn\': \'#f59e0b\', \'err\': \'#ef4444\'}[kind]\n    display(HTML(f\'<div style="font-family:system-ui,sans-serif;font-size:14px;padding:10px 14px;margin:6px 0;border-radius:10px;\'\n                 f\'border-left:4px solid {cor};background:{cor}14;color:inherit">{msg}</div>\'))\n\n# ---------- 1. Login Google (obrigatório) ----------\n_box(\'🔐 Aguardando login na conta Google… aceite a janela que abriu.\')\ntry:\n    from google.colab import auth\n    auth.authenticate_user()\nexcept Exception as e:\n    raise SystemExit(f\'Login cancelado ou falhou: {e}. Rode a célula novamente e conclua o login.\')\n\nUSER_EMAIL = None\ntry:\n    import google.auth, google.auth.transport.requests, requests\n    _creds, _ = google.auth.default()\n    _creds.refresh(google.auth.transport.requests.Request())\n    USER_EMAIL = requests.get(\'https://www.googleapis.com/oauth2/v3/userinfo\',\n                              headers={\'Authorization\': f\'Bearer {_creds.token}\'}, timeout=15).json().get(\'email\')\nexcept Exception:\n    pass\nUSER_EMAIL = USER_EMAIL or \'Conta Google conectada\'\n\n# ---------- 2. Google Drive (opcional) ----------\nDRIVE_OK = False\nif conectar_google_drive:\n    try:\n        from google.colab import drive\n        drive.mount(\'/content/drive\', force_remount=False)\n        DRIVE_OK = os.path.isdir(\'/content/drive/MyDrive\')\n    except Exception as e:\n        _box(f\'Drive não conectado: {e}\', \'warn\')\n\n# ---------- 3. GPU ----------\nGPU_NAME = None\ntry:\n    import torch\n    if torch.cuda.is_available():\n        GPU_NAME = torch.cuda.get_device_name(0)\nexcept Exception:\n    pass\nif GPU_NAME:\n    _box(f\'⚡ GPU detectada: <b>{GPU_NAME}</b>\', \'ok\')\nelse:\n    _box(\'⚠️ <b>Nenhuma GPU nesta sessão.</b> A separação vai ficar muito lenta. Vá em <b>Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU</b> e rode esta célula de novo.\', \'warn\')\n\n# ---------- 4. Dependências ----------\n_box(\'📦 Instalando yt-dlp, o separador de faixas (audio-separator) e o runtime JavaScript… 1 a 3 min\')\n_t0 = time.time()\n_r = subprocess.run([sys.executable, \'-m\', \'pip\', \'install\', \'-q\', \'-U\', \'yt-dlp[default]\', \'audio-separator[cpu]\', \'audioread\'],\n                    capture_output=True, text=True, timeout=900)\nif _r.returncode != 0:\n    _box(\'Falha ao instalar as dependências. Copie a mensagem abaixo e envie para suporte.\', \'err\')\n    print(_r.stderr[-3000:])\n    raise SystemExit(\'pip falhou\')\nif not shutil.which(\'ffmpeg\') or not shutil.which(\'ffprobe\'):\n    subprocess.run([\'apt-get\', \'update\', \'-qq\'], check=True, timeout=300)\n    subprocess.run([\'apt-get\', \'install\', \'-y\', \'-qq\', \'ffmpeg\'], check=True, timeout=300)\nif not shutil.which(\'deno\'):\n    subprocess.run([\'curl\', \'-fSL\', \'--max-time\', \'120\', \'https://deno.land/install.sh\',\n                    \'-o\', \'/tmp/stemlab_deno_install.sh\'], check=True, timeout=150)\n    subprocess.run([\'sh\', \'/tmp/stemlab_deno_install.sh\'],\n                   env=dict(os.environ, DENO_INSTALL=\'/usr/local\'),\n                   stdin=subprocess.DEVNULL, check=True, timeout=300)\nos.environ[\'PATH\'] += \':/usr/local/bin\'\nif not shutil.which(\'deno\'):\n    raise RuntimeError(\'Deno não foi encontrado. Reinicie a sessão e tente preparar o ambiente novamente.\')\nsubprocess.run([\'deno\', \'--version\'], check=True, capture_output=True, timeout=15)\nimport yt_dlp\ntry:\n    import audio_separator\n    SEP_VERSION = getattr(audio_separator, \'__version__\', None) or \'ok\'\nexcept Exception as e:\n    raise RuntimeError(\'O separador não pôde ser importado. Reinicie a sessão e execute novamente a preparação.\') from e\n\nclear_output()\n_box(f\'✅ <b>Login OK</b> — {USER_EMAIL}\', \'ok\')\n_box((\'✅ <b>Google Drive conectado</b> — cookies e faixas podem ser salvos em <code>Meu Drive/StemLab</code>\' if DRIVE_OK\n      else \'ℹ️ Google Drive <b>não conectado</b> — os cookies valerão só nesta sessão.\'), \'ok\' if DRIVE_OK else \'info\')\n_box((f\'⚡ GPU: <b>{GPU_NAME}</b>\' if GPU_NAME else \'⚠️ <b>Sem GPU</b> — ative em Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU\'), \'ok\' if GPU_NAME else \'warn\')\n_box(f\'✅ yt-dlp <b>{yt_dlp.version.__version__}</b> · separador {"<b>instalado</b>" if SEP_VERSION else "<b>NÃO instalado</b>"} · ffmpeg {"OK" if shutil.which("ffmpeg") else "NÃO encontrado"} · \'\n     f\'deno {"OK" if shutil.which("deno") else "não instalado"} · instalação em {int(time.time()-_t0)} s\', \'ok\' if SEP_VERSION else \'err\')\n_box(\'👉 Agora rode a célula <b>2️⃣ Abrir o aplicativo</b>. O modelo de IA principal começa a ser baixado em segundo plano assim que o app abrir.\', \'info\')\n\nfrom importlib.metadata import version\nENVIRONMENT_VERSIONS = {p: version(p) for p in (\'yt-dlp\', \'audio-separator\', \'torch\')}\n_cli_check = subprocess.run([\'audio-separator\', \'--help\'], capture_output=True, text=True, timeout=120)\nif _cli_check.returncode or \'--custom_output_names\' not in _cli_check.stdout:\n    raise RuntimeError(\'O comando audio-separator não está operacional ou é incompatível. Reinicie a sessão.\')\nprint(\'StemLab 2.0 RC1 | Versões instaladas:\', ENVIRONMENT_VERSIONS)\n'

APP_PY_HEAD = r'''#@title 2️⃣ Abrir o aplicativo  { display-mode: "form" }
#@markdown Clique no ▶. A interface aparece logo abaixo. Se o ambiente for reiniciado, rode a célula 1 e depois esta.
import os as _os
from IPython.display import HTML as _HTML, display as _display

def _erro(msg):
    _display(_HTML(f'<div style="font-family:system-ui,sans-serif;padding:14px 16px;border-radius:12px;border-left:4px solid #ef4444;'
                   f'background:#ef444414;font-size:14px">⛔ <b>{msg}</b></div>'))

_pronto = True
if 'USER_EMAIL' not in globals():
    _erro('Execute primeiro a célula 1️⃣ (login na conta Google).'); _pronto = False
else:
    try:
        import google.auth as _ga; _ga.default()
    except Exception:
        _erro('Login na conta Google necessário. Rode a célula 1️⃣ novamente.'); _pronto = False
    try:
        import audio_separator as _as
    except Exception:
        _erro('O separador de faixas não está instalado. Rode a célula 1️⃣ novamente e aguarde a instalação terminar.'); _pronto = False

if _pronto:
'''

CLEAN_PY = '#@title 3️⃣ (Opcional) Limpar arquivos temporários com segurança { display-mode: "form" }\n#@markdown Não limpa durante tarefas ativas. Preserva os modelos, os cookies e as cópias do Drive.\nconfirmar_limpeza = False  #@param {type:"boolean"}\nif not confirmar_limpeza:\n    print(\'Limpeza desativada. Marque confirmar_limpeza e execute esta célula para apagar temporários.\')\nelif \'cb_cleanup\' not in globals():\n    print(\'Execute a célula 2 antes de usar a limpeza.\')\nelse:\n    _cleanup_result = cb_cleanup().data\n    if not _cleanup_result.get(\'ok\'):\n        print(\'⚠️ \' + _cleanup_result.get(\'error\', \'Não foi possível limpar.\'))\n    else:\n        print(\'✅ Arquivos temporários e histórico limpos. Execute a célula 2 para renovar a interface.\')\n'

def indent(code, n=4):
    return '\n'.join((' ' * n + l) if l.strip() else l for l in code.splitlines())

APP_PY_TAIL = r'''
if _pronto:
    try:
        _display(_HTML(APP_HTML))
    except Exception as _e:
        import traceback as _tb
        _erro('Falha ao abrir o aplicativo. Copie a mensagem abaixo e envie para suporte.')
        print(_tb.format_exc())
'''
app_cell = (APP_PY_HEAD + '    try:\n' + indent(backend, 8) + '\n\n' + indent('APP_HTML = r"""' + app_html + '"""', 8)
            + '\n    except Exception as _e:\n        import traceback as _tb\n        _pronto = False\n'
            + '        _erro(\'Erro ao preparar o aplicativo. Copie a mensagem abaixo e envie para suporte.\')\n'
            + '        print(_tb.format_exc())\n' + APP_PY_TAIL)

def cell(kind, src, **meta):
    lines = src.splitlines(keepends=True)
    c = {'cell_type': kind, 'metadata': meta, 'source': lines}
    if kind == 'code':
        c.update({'execution_count': None, 'outputs': []})
    return c

nb = {
    'nbformat': 4, 'nbformat_minor': 0,
    'metadata': {
        'colab': {'name': 'StemLab.ipynb', 'provenance': [], 'toc_visible': True, 'gpuType': 'T4'},
        'accelerator': 'GPU',
        'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
        'language_info': {'name': 'python'},
    },
    'cells': [
        cell('markdown', INTRO_MD, id='intro'),
        cell('code', SETUP_PY, id='setup', cellView='form'),
        cell('code', app_cell, id='app', cellView='form'),
        cell('code', CLEAN_PY, id='clean', cellView='form'),
        cell('markdown', open(os.path.join(HERE, '..', 'CHANGELOG.md'), encoding='utf-8').read(), id='changes'),
    ],
}
out = os.path.join(OUT_DIR, 'StemLab.ipynb')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
for c in nb['cells']:
    if c['cell_type'] == 'code':
        compile(''.join(c['source']), c['metadata']['id'], 'exec')
print('notebook gerado:', out, f'({os.path.getsize(out)//1024} KB)')

