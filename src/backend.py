# ============================================================
#  StemLab — backend (roda dentro do Google Colab)
#  Expõe funções Python para a interface web via
#  google.colab.output.register_callback / kernel.invokeFunction
# ============================================================
import os, re, json, time, uuid, shutil, threading, socketserver, http.server
import urllib.parse, traceback, queue, subprocess, base64, sys

import yt_dlp
from IPython.display import JSON

# ---------- caminhos ----------
BASE_DIR      = '/content/stemlab'
WORK_DIR      = os.path.join(BASE_DIR, 'work')       # áudio de origem (wav) e uploads
OUT_DIR       = os.path.join(BASE_DIR, 'out')        # resultados por tarefa (servidos ao navegador)
MODELS_DIR    = os.path.join(BASE_DIR, 'models')     # modelos de IA baixados
COOKIES_PATH  = os.path.join(BASE_DIR, 'cookies.txt')
DRIVE_MYDRIVE = '/content/drive/MyDrive'
DRIVE_ROOT    = os.path.join(DRIVE_MYDRIVE, 'StemLab')
FILE_PORT     = 8766
MAX_UPLOAD_MB = 250
MAX_DURATION  = 25 * 60   # 25 min: acima disso a GPU gratuita costuma estourar a memória
MOCK          = bool(os.environ.get('STEMLAB_MOCK'))  # modo de teste local sem GPU/modelos
for _d in (WORK_DIR, OUT_DIR, MODELS_DIR):
    os.makedirs(_d, exist_ok=True)

STATE = {
    'jobs': {}, 'sources': {}, 'uploads': {},
    'user': globals().get('USER_EMAIL') or 'Conta Google conectada',
    'js_runtime': None, 'gpu': None, 'prefetch': {},
}

# ---------- modos de separação ----------
STEM_PT = {'Vocals': 'Voz', 'Instrumental': 'Playback', 'Drums': 'Bateria', 'Bass': 'Baixo',
           'Guitar': 'Guitarra', 'Piano': 'Piano', 'Other': 'Outros'}
STEM_ICON = {'Vocals': '🎤', 'Instrumental': '🎹', 'Drums': '🥁', 'Bass': '🎸', 'Guitar': '🎸', 'Piano': '🎹', 'Other': '🎼'}
STEM_COLOR = {'Vocals': '#f472b6', 'Instrumental': '#38bdf8', 'Drums': '#fb923c', 'Bass': '#a78bfa',
              'Guitar': '#facc15', 'Piano': '#34d399', 'Other': '#94a3b8'}
MODES = {
    '2stem': {'label': 'Voz + Playback', 'model': 'model_bs_roformer_ep_317_sdr_12.9755.ckpt',
              'stems': ['Vocals', 'Instrumental'], 'factor': 1.2, 'base': 30},
    '4stem': {'label': 'Banda (4 faixas)', 'model': 'htdemucs_ft.yaml',
              'stems': ['Vocals', 'Drums', 'Bass', 'Other'], 'factor': 1.2, 'base': 40},
    '6stem': {'label': 'Completo (6 faixas)', 'model': 'htdemucs_6s.yaml',
              'stems': ['Vocals', 'Drums', 'Bass', 'Guitar', 'Piano', 'Other'], 'factor': 0.5, 'base': 30},
}
OUT_FORMATS = {'wav': 'WAV', 'flac': 'FLAC', 'mp3': 'MP3'}

# ---------- utilidades ----------
def _drive_on():
    return os.path.isdir(DRIVE_MYDRIVE)

def _detect_js_runtime():
    if STATE['js_runtime'] is not None:
        return STATE['js_runtime']
    rt = {}
    for name in ('deno', 'node', 'bun'):
        p = shutil.which(name)
        if p:
            rt = {name: {'path': p}}
            break
    STATE['js_runtime'] = rt
    return rt

def _gpu_info(force=False):
    if STATE['gpu'] is not None and not force:
        return STATE['gpu']
    info = {'available': False, 'name': None, 'memory_gb': None, 'mock': MOCK}
    try:
        import torch
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info.update({'available': True, 'name': p.name, 'memory_gb': round(p.total_memory / 1024 ** 3, 1)})
    except Exception:
        pass
    STATE['gpu'] = info
    return info

def _friendly_error(msg):
    m = (msg or '').lower()
    if 'sign in to confirm' in m or 'not a bot' in m or ('bot' in m and 'confirm' in m):
        return ('O YouTube pediu confirmação de que você não é um robô. Isso é comum em servidores do Colab. '
                'Carregue os cookies da sua conta na seção "Cookies" e tente novamente.')
    if 'private video' in m or 'this video is private' in m:
        return 'Vídeo privado. Carregue os cookies de uma conta com acesso para usá-lo.'
    if 'members-only' in m or 'join this channel' in m:
        return 'Conteúdo exclusivo para membros. Carregue os cookies da conta que é membro do canal.'
    if 'age' in m and ('restrict' in m or 'confirm your age' in m or 'inappropriate' in m):
        return 'Vídeo com restrição de idade. Carregue os cookies da sua conta para confirmar a idade.'
    if 'video unavailable' in m or 'video is unavailable' in m or 'not available' in m:
        return 'Vídeo indisponível (removido, bloqueado na região ou link inválido).'
    if 'unsupported url' in m or 'is not a valid url' in m:
        return 'Este link não é reconhecido. Cole um link de vídeo do YouTube.'
    if 'requested format is not available' in m:
        return 'O formato escolhido não está disponível para este vídeo. Tente outro.'
    if 'http error 429' in m or 'too many requests' in m:
        return 'O YouTube limitou as requisições (429). Aguarde alguns minutos ou use cookies.'
    if 'live' in m and ('is a live' in m or 'not yet' in m or 'premiere' in m):
        return 'Transmissões ao vivo ou estreias ainda não disponíveis não podem ser processadas.'
    if 'out of memory' in m or 'cuda error' in m:
        return 'A memória da GPU estourou. Tente uma música mais curta ou o modo "Voz + Playback".'
    return re.sub(r'^\s*ERROR:\s*', '', msg or 'Erro desconhecido').strip()[:400]

class _SilentLogger:
    """Engole a saída do yt-dlp, mas guarda erros para reportar na interface."""
    def __init__(self): self.errors, self.warnings = [], []
    def debug(self, msg):   pass
    def info(self, msg):    pass
    def warning(self, msg): self.warnings.append(str(msg))
    def error(self, msg):   self.errors.append(str(msg))

def _base_opts():
    o = {
        'quiet': True, 'no_warnings': True, 'noprogress': True, 'nocheckcertificate': True,
        'extractor_retries': 3, 'retries': 5, 'fragment_retries': 5, 'socket_timeout': 30,
        'geo_bypass': True, 'logger': _SilentLogger(),
    }
    if os.path.exists(COOKIES_PATH):
        o['cookiefile'] = COOKIES_PATH
    rt = _detect_js_runtime()
    if rt:
        o['js_runtimes'] = rt
    return o

def _fmt_size(b):
    if not b: return None
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024: return f'{b:.0f} {unit}' if unit == 'B' else f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} TB'

def _hms(sec):
    sec = int(round(sec or 0)); h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

def _thumb(info):
    t = info.get('thumbnail')
    if not t and info.get('thumbnails'):
        t = info['thumbnails'][-1].get('url')
    if not t and info.get('id'):
        t = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
    return t

def _safe_name(s, n=90):
    s = yt_dlp.utils.sanitize_filename(str(s or 'audio'), restricted=False)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:n] or 'audio'

def _parse_video_id(url):
    u = url.strip()
    if not re.match(r'^https?://', u, re.I):
        u = 'https://' + u
    p = urllib.parse.urlparse(u)
    host = p.netloc.lower().replace('www.', '').replace('m.', '').replace('music.', '')
    qs = urllib.parse.parse_qs(p.query)
    if host == 'youtu.be':
        vid = p.path.strip('/').split('/')[0] or None
    elif 'youtube' in host:
        vid = (qs.get('v') or [None])[0]
        if not vid:
            m = re.match(r'^/(shorts|live|embed|v)/([A-Za-z0-9_-]{11})', p.path)
            vid = m.group(2) if m else None
    else:
        raise ValueError('unsupported url: apenas links do YouTube são aceitos.')
    if not vid:
        if (qs.get('list') or [None])[0]:
            raise ValueError('Este link é de uma playlist. O StemLab trabalha com uma música por vez: abra o vídeo e copie o link dele.')
        raise ValueError('unsupported url: não encontrei um vídeo nesse link.')
    return vid

def _ffprobe_duration(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0

# ---------- cookies ----------
def _json_cookies_to_netscape(items):
    lines = ['# Netscape HTTP Cookie File', '# gerado pelo StemLab', '']
    for c in items:
        dom = c.get('domain') or '.youtube.com'
        flag = 'TRUE' if dom.startswith('.') else 'FALSE'
        path = c.get('path') or '/'
        secure = 'TRUE' if c.get('secure') else 'FALSE'
        exp = c.get('expirationDate') or c.get('expires') or c.get('expiry') or 0
        try: exp = int(float(exp))
        except Exception: exp = 0
        lines.append('\t'.join([dom, flag, path, secure, str(exp), str(c.get('name', '')), str(c.get('value', ''))]))
    return '\n'.join(lines) + '\n'

def _header_cookies_to_netscape(header):
    header = re.sub(r'^\s*cookie\s*:\s*', '', header.strip(), flags=re.I)
    items = []
    for part in header.split(';'):
        if '=' in part:
            n, v = part.strip().split('=', 1)
            items.append({'domain': '.youtube.com', 'path': '/', 'secure': True,
                          'expirationDate': int(time.time()) + 365 * 86400, 'name': n.strip(), 'value': v.strip()})
    return _json_cookies_to_netscape(items)

def _normalize_cookies(text):
    t = text.strip().lstrip('﻿')
    if not t:
        raise ValueError('Arquivo de cookies vazio.')
    if t.startswith('[') or t.startswith('{'):
        data = json.loads(t)
        if isinstance(data, dict):
            data = data.get('cookies') or data.get('items') or list(data.values())
        return _json_cookies_to_netscape(data)
    if '\t' in t:
        if not t.startswith('#'):
            t = '# Netscape HTTP Cookie File\n' + t
        return t + '\n'
    if '=' in t and ';' in t and '\n' not in t.strip():
        return _header_cookies_to_netscape(t)
    raise ValueError('Formato de cookies não reconhecido. Use um arquivo cookies.txt (formato Netscape) ou JSON exportado por extensão.')

def _cookie_summary():
    if not os.path.exists(COOKIES_PATH):
        return {'found': False}
    names, total = set(), 0
    with open(COOKIES_PATH, encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('#') or not line.strip(): continue
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 7 and ('youtube.com' in parts[0] or 'google.com' in parts[0]):
                total += 1
                names.add(parts[5])
    logged = bool(names & {'SID', '__Secure-3PSID', 'SAPISID', '__Secure-3PAPISID', 'LOGIN_INFO'})
    src = 'drive' if os.path.exists(os.path.join(DRIVE_ROOT, 'cookies.txt')) else 'sessao'
    return {'found': True, 'total': total, 'logged_in': logged, 'source': src,
            'updated': time.strftime('%d/%m/%Y %H:%M', time.localtime(os.path.getmtime(COOKIES_PATH)))}

def cb_save_cookies(text, persist_drive=True):
    try:
        content = _normalize_cookies(text)
        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        saved_drive = False
        if persist_drive and _drive_on():
            os.makedirs(DRIVE_ROOT, exist_ok=True)
            shutil.copy(COOKIES_PATH, os.path.join(DRIVE_ROOT, 'cookies.txt'))
            saved_drive = True
        s = _cookie_summary(); s['saved_drive'] = saved_drive
        return JSON({'ok': True, 'cookies': s})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

def cb_clear_cookies(also_drive=False):
    try:
        if os.path.exists(COOKIES_PATH): os.remove(COOKIES_PATH)
        if also_drive:
            p = os.path.join(DRIVE_ROOT, 'cookies.txt')
            if os.path.exists(p): os.remove(p)
        return JSON({'ok': True, 'cookies': _cookie_summary()})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_test_cookies():
    try:
        if not os.path.exists(COOKIES_PATH):
            return JSON({'ok': False, 'error': 'Nenhum cookie carregado.'})
        opts = _base_opts(); opts.update({'extract_flat': True, 'playlistend': 1, 'ignoreerrors': True})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info('https://www.youtube.com/feed/history', download=False)
        ok = bool(info and (info.get('entries') is not None))
        return JSON({'ok': True, 'valid': ok,
                     'message': 'Cookies válidos: sua conta foi reconhecida pelo YouTube.' if ok
                     else 'O YouTube não reconheceu a sessão. Exporte os cookies novamente com a conta logada.'})
    except Exception as e:
        return JSON({'ok': True, 'valid': False, 'message': _friendly_error(str(e))})

# ---------- bootstrap ----------
def cb_bootstrap():
    try:
        if not os.path.exists(COOKIES_PATH) and _drive_on():
            saved = os.path.join(DRIVE_ROOT, 'cookies.txt')
            if os.path.exists(saved):
                shutil.copy(saved, COOKIES_PATH)
        return JSON({'ok': True, 'user': STATE['user'], 'drive': _drive_on(), 'cookies': _cookie_summary(),
                     'ytdlp': yt_dlp.version.__version__, 'js_runtime': next(iter(_detect_js_runtime()), None),
                     'gpu': _gpu_info(), 'port': FILE_PORT, 'mock': MOCK, 'max_upload_mb': MAX_UPLOAD_MB,
                     'max_duration': MAX_DURATION,
                     'modes': {k: {'label': v['label'], 'stems': v['stems'], 'factor': v['factor'], 'base': v['base'],
                                   'ready': _model_ready(v['model'])} for k, v in MODES.items()},
                     'stem_pt': STEM_PT, 'stem_icon': STEM_ICON, 'stem_color': STEM_COLOR})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- análise de link ----------
def _summarize_audio_formats(info):
    auds, seen = [], set()
    duration = info.get('duration') or 0
    for f in info.get('formats') or []:
        vcodec, acodec = f.get('vcodec') or 'none', f.get('acodec') or 'none'
        if acodec == 'none' or vcodec != 'none':
            continue
        if 'drc' in (f.get('format_id') or '') or 'DRC' in (f.get('format_note') or ''):
            continue
        size = f.get('filesize') or f.get('filesize_approx') or 0
        if not size and duration and f.get('tbr'):
            size = int(f['tbr'] * 1000 / 8 * duration)
        abr = int(round(f.get('abr') or f.get('tbr') or 0))
        key = (f.get('ext'), acodec.split('.')[0], abr // 8)
        if key in seen: continue
        seen.add(key)
        auds.append({'ext': f.get('ext'), 'acodec': acodec.split('.')[0], 'abr': abr, 'size': size, 'size_label': _fmt_size(size)})
    auds.sort(key=lambda a: -a['abr'])
    return auds

def cb_analyze(url):
    try:
        vid = _parse_video_id(url)
        opts = _base_opts(); opts['noplaylist'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={vid}', download=False)
        if not info:
            raise RuntimeError('video unavailable')
        if info.get('is_live'):
            raise RuntimeError('is a live')
        dur = info.get('duration') or 0
        src_id = uuid.uuid4().hex[:10]
        src = {
            'id': src_id, 'kind': 'youtube', 'video_id': info.get('id'), 'title': info.get('title'),
            'channel': info.get('uploader') or info.get('channel'), 'duration': dur, 'duration_str': _hms(dur),
            'views': info.get('view_count'), 'upload_date': info.get('upload_date'), 'thumbnail': _thumb(info),
            'url': info.get('webpage_url') or f'https://www.youtube.com/watch?v={vid}',
            'audio_formats': _summarize_audio_formats(info), 'wav': None, 'created': time.time(),
            'too_long': dur > MAX_DURATION,
        }
        STATE['sources'][src_id] = src
        return JSON({'ok': True, 'source': src})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

# ---------- upload de arquivo local (em pedaços base64) ----------
def cb_upload_start(name, size):
    try:
        size = int(size or 0)
        if size <= 0:
            raise ValueError('Arquivo vazio.')
        if size > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f'O arquivo tem {_fmt_size(size)}. O limite é {MAX_UPLOAD_MB} MB.')
        ext = os.path.splitext(name or '')[1].lower()
        if ext not in ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.aiff', '.aif', '.mp4', '.webm', '.mkv', '.mov'):
            raise ValueError('Formato não suportado. Envie MP3, WAV, FLAC, M4A, OGG, OPUS, AIFF ou um vídeo MP4/WEBM.')
        up_id = uuid.uuid4().hex[:10]
        path = os.path.join(WORK_DIR, f'upload_{up_id}{ext}')
        open(path, 'wb').close()
        STATE['uploads'][up_id] = {'path': path, 'name': name, 'size': size, 'received': 0}
        return JSON({'ok': True, 'upload_id': up_id})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_upload_chunk(up_id, data_b64):
    try:
        up = STATE['uploads'].get(up_id)
        if not up: raise ValueError('Envio não encontrado. Tente novamente.')
        chunk = base64.b64decode(data_b64)
        with open(up['path'], 'ab') as f:
            f.write(chunk)
        up['received'] += len(chunk)
        if up['received'] > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError('Arquivo maior que o limite.')
        return JSON({'ok': True, 'received': up['received']})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_upload_finish(up_id):
    try:
        up = STATE['uploads'].pop(up_id, None)
        if not up: raise ValueError('Envio não encontrado. Tente novamente.')
        if up['received'] != up['size']:
            raise ValueError(f'Envio incompleto ({_fmt_size(up["received"])} de {_fmt_size(up["size"])}). Tente novamente.')
        dur = _ffprobe_duration(up['path'])
        if dur <= 0:
            os.remove(up['path'])
            raise ValueError('Não consegui ler este arquivo como áudio. Verifique se ele não está corrompido.')
        src_id = uuid.uuid4().hex[:10]
        title = os.path.splitext(os.path.basename(up['name']))[0]
        src = {'id': src_id, 'kind': 'file', 'title': title, 'channel': None, 'duration': dur, 'duration_str': _hms(dur),
               'file_name': up['name'], 'file_size': up['size'], 'file_size_label': _fmt_size(up['size']),
               'thumbnail': None, 'url': None, 'audio_formats': [], 'wav': None, 'src_path': up['path'],
               'created': time.time(), 'too_long': dur > MAX_DURATION}
        STATE['sources'][src_id] = src
        return JSON({'ok': True, 'source': src})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- tarefas ----------
JOB_QUEUE = queue.Queue()

def _stage(job, key, label, status='running', percent=None):
    for s in job['stages']:
        if s['key'] == key:
            s['status'] = status
            if percent is not None: s['percent'] = percent
            if status == 'running':
                s['started'] = s.get('started') or time.time()
            if status in ('done', 'error'):
                s['ended'] = time.time()
        elif s['status'] == 'running' and status == 'running':
            s['status'] = 'done'; s['percent'] = 100; s['ended'] = time.time()
    if job.get('stage') != key: job['detail'] = ''
    job['stage'] = key; job['stage_label'] = label
    if percent is not None: job['percent'] = percent
    if status == 'running': job['status'] = 'running'

def _check_cancel(job):
    if job.get('cancel'):
        raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')

def _yt_progress(d, job):
    _check_cancel(job)
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        done = d.get('downloaded_bytes') or 0
        job['percent'] = (done / total * 100) if total else 0
        job['detail'] = f"{_fmt_size(done) or '0 B'}{' de ' + _fmt_size(total) if total else ''}" + (f" · {_fmt_size(d['speed'])}/s" if d.get('speed') else '')
    elif d['status'] == 'finished':
        job['percent'] = 100; job['detail'] = ''

def _final_path(info, out_dir, before):
    rd = (info or {}).get('requested_downloads') or []
    if rd and rd[0].get('filepath') and os.path.exists(rd[0]['filepath']):
        return rd[0]['filepath']
    cands = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
             if f not in before and not f.endswith(('.part', '.ytdl', '.webp', '.jpg', '.png'))]
    return max(cands, key=os.path.getmtime) if cands else None

def _download_youtube_audio(job, src, out_dir, audio_format='best', audio_quality='best', embed_meta=True, tag='src'):
    """Baixa o áudio de um vídeo. audio_format 'best' = original (m4a/webm) sem conversão."""
    opts = _base_opts()
    logger = _SilentLogger(); opts['logger'] = logger
    opts.update({
        'outtmpl': os.path.join(out_dir, f'{tag}_%(id)s.%(ext)s' if tag == 'src' else '%(title).120B [%(id)s].%(ext)s'),
        'noplaylist': True, 'overwrites': True, 'windowsfilenames': True, 'concurrent_fragment_downloads': 4,
        'format': 'ba/b', 'progress_hooks': [lambda d: _yt_progress(d, job)], 'postprocessors': [], 'ignoreerrors': True,
        'postprocessor_hooks': [lambda d: _pp_hook(d, job)],
    })
    if audio_format != 'best':
        pp = {'key': 'FFmpegExtractAudio', 'preferredcodec': audio_format}
        if audio_format not in ('wav', 'flac') and audio_quality and audio_quality != 'best':
            pp['preferredquality'] = str(audio_quality)
        elif audio_format == 'mp3':
            pp['preferredquality'] = '0'
        opts['postprocessors'].append(pp)
        if embed_meta:
            opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
            if audio_format in ('mp3', 'm4a', 'flac', 'opus', 'aac'):
                opts['writethumbnail'] = True
                opts['postprocessors'].append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
    before = set(os.listdir(out_dir))
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(src['url'], download=True)
    _check_cancel(job)
    path = _final_path(info, out_dir, before)
    if not path:
        raise RuntimeError(logger.errors[-1] if logger.errors else 'O arquivo não foi encontrado após o download.')
    if logger.errors:
        job['warning'] = _friendly_error(logger.errors[-1])
    return path

def _pp_hook(d, job):
    _check_cancel(job)
    names = {'FFmpegExtractAudio': 'Convertendo áudio…', 'FFmpegMetadata': 'Gravando metadados…',
             'EmbedThumbnail': 'Inserindo capa…', 'MoveFiles': 'Finalizando…'}
    if d['status'] in ('started', 'processing'):
        job['detail'] = names.get(d.get('postprocessor'), 'Processando…')

def _ensure_source_wav(job, src):
    """Garante um WAV 44.1 kHz estéreo da fonte (baixando do YouTube se preciso). Fica em cache por fonte."""
    if src.get('wav') and os.path.exists(src['wav']):
        _stage(job, 'fetch', 'Áudio já disponível', 'done', 100)
        return src['wav']
    src_dir = os.path.join(WORK_DIR, src['id']); os.makedirs(src_dir, exist_ok=True)
    if src['kind'] == 'youtube':
        _stage(job, 'fetch', 'Baixando áudio do YouTube…', 'running', 0)
        raw = _download_youtube_audio(job, src, src_dir, 'best', tag='src')
    else:
        raw = src['src_path']
    _stage(job, 'fetch', 'Preparando o áudio…', 'running', 100)
    job['detail'] = 'Convertendo para WAV 44.1 kHz'
    wav = os.path.join(src_dir, 'source.wav')
    r = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', raw, '-vn', '-ac', '2', '-ar', '44100',
                        '-c:a', 'pcm_s16le', wav], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError('Falha ao converter o áudio: ' + (r.stderr.strip().splitlines() or ['ffmpeg'])[-1])
    src['wav'] = wav
    if not src.get('duration'):
        src['duration'] = _ffprobe_duration(wav); src['duration_str'] = _hms(src['duration'])
    job['detail'] = ''
    return wav

# ---- separação (subprocesso cancelável) ----
def _sep_cmd():
    exe = shutil.which('audio-separator')
    return [exe] if exe else [sys.executable, '-m', 'audio_separator.utils.cli']

def _model_ready(model):
    return any(f.startswith(os.path.splitext(model)[0]) for f in os.listdir(MODELS_DIR)) if os.path.isdir(MODELS_DIR) else False

def _iter_output(stream):
    """Le a saida do processo separando por quebra de linha e tambem por retorno de carro (barras do tqdm)."""
    buf = ''
    while True:
        ch = stream.read(1)
        if not ch:
            if buf: yield buf
            return
        if ch == chr(13) or ch == chr(10):
            if buf.strip(): yield buf
            buf = ''
        else:
            buf += ch

def _run_separator(job, wav, mode, out_format, out_dir, names):
    cfg = MODES[mode]
    cmd = _sep_cmd() + [wav, '--model_filename', cfg['model'],
           '--model_file_dir', MODELS_DIR, '--output_dir', out_dir, '--output_format', OUT_FORMATS[out_format],
           '--custom_output_names', json.dumps(names), '--log_level', 'info']
    if out_format == 'mp3':
        cmd += ['--output_bitrate', '320k']
    if cfg['model'].endswith('.yaml'):
        cmd += ['--demucs_shifts', '1']
    if _gpu_info()['available']:
        cmd += ['--use_autocast']   # precisão mista na GPU: bem mais rápido, qualidade praticamente igual
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', TQDM_MININTERVAL='0.5')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='ignore', env=env, bufsize=0)
    job['proc'] = proc
    tail, err_hint = [], None
    started = time.time(); phase_started = None
    est = cfg['base'] + (job.get('duration') or 180) * cfg['factor']
    onde = 'na GPU' if (_gpu_info()['available']) else 'no processador'
    if _model_ready(cfg['model']):
        _stage(job, 'model', f'Carregando o modelo {onde}…', 'running', 0)
    else:
        _stage(job, 'model', 'Baixando o modelo de IA (uma vez por sessão)…', 'running', 0)
    try:
        for line in _iter_output(proc.stdout):
            if job.get('cancel'):
                proc.kill(); raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')
            tail.append(line[:300]); tail[:] = tail[-40:]
            low = line.lower()
            m = re.search(r'(\d{1,3})%\|', line)  # barras do tqdm (download do modelo / separação)
            if 'starting separation' in low:
                _stage(job, 'separate', f'Separando as faixas {onde}…', 'running', 0); phase_started = time.time(); job['detail'] = ''
            elif 'loading model' in low and job['stage'] == 'model':
                job['detail'] = 'Carregando pesos…'
            elif ' saving ' in low or 'writing output' in low:
                if job['stage'] == 'separate': job['detail'] = 'Gravando arquivos…'
            elif m and job['stage'] == 'model':
                job['percent'] = int(m.group(1)); job['detail'] = f'Baixando modelo… {m.group(1)}%'
            elif m and job['stage'] == 'separate':
                job['percent'] = max(job['percent'], min(99, int(m.group(1)))); job['detail'] = f'{m.group(1)}%'
            if ('error' in low or 'traceback' in low) and 'errorlevel' not in low:
                err_hint = line
            if job['stage'] == 'separate' and phase_started and not m:
                job['percent'] = max(job['percent'], min(95, (time.time() - phase_started) / max(est, 1) * 100))
        proc.wait()
    finally:
        job['proc'] = None
        try: proc.stdout.close()
        except Exception: pass
    if job.get('cancel'):
        raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')
    if proc.returncode != 0:
        msg = err_hint or (tail[-1] if tail else f'o separador retornou código {proc.returncode}')
        job['log_tail'] = tail[-15:]
        raise RuntimeError(_friendly_error(msg))
    job['sep_seconds'] = round(time.time() - started)

def _run_separator_mock(job, wav, mode, out_format, out_dir, names):
    """Modo de teste local: gera 'faixas' com filtros do ffmpeg, sem IA."""
    filters = {'Vocals': 'highpass=f=1200', 'Instrumental': 'lowpass=f=1200', 'Drums': 'lowpass=f=200',
               'Bass': 'lowpass=f=120', 'Guitar': 'bandpass=f=800:w=400', 'Piano': 'bandpass=f=1500:w=600', 'Other': 'highpass=f=3000'}
    _stage(job, 'model', 'Carregando o modelo (simulação)…', 'running', 0); time.sleep(1.2)
    _stage(job, 'separate', 'Separando as faixas (simulação)…', 'running', 0)
    stems = MODES[mode]['stems']
    for i, stem in enumerate(stems):
        _check_cancel(job)
        ext = out_format
        dst = os.path.join(out_dir, f'{names[stem]}.{ext}')
        codec = ['-c:a', 'libmp3lame', '-b:a', '320k'] if ext == 'mp3' else (['-c:a', 'flac'] if ext == 'flac' else ['-c:a', 'pcm_s16le'])
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', wav, '-af', filters[stem]] + codec + [dst], check=True)
        job['percent'] = (i + 1) / len(stems) * 100; time.sleep(0.6)
    job['sep_seconds'] = 3

def _make_preview(src_path, dst_path):
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src_path, '-vn', '-ac', '2', '-ar', '44100',
                    '-c:a', 'libmp3lame', '-b:a', '96k', dst_path], capture_output=True)
    return os.path.exists(dst_path)

def _copy_to_drive(job, path, sub):
    if not (job.get('save_drive') and _drive_on()):
        return None
    d = os.path.join(DRIVE_ROOT, sub); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(path))
    shutil.copy2(path, dst)
    return dst.replace(DRIVE_MYDRIVE, 'Meu Drive')

def _run_separate_job(job):
    src = STATE['sources'][job['source_id']]
    job['duration'] = src.get('duration') or 0
    out_dir = os.path.join(OUT_DIR, job['id']); os.makedirs(out_dir, exist_ok=True)
    wav = _ensure_source_wav(job, src)
    if not job['duration']:
        job['duration'] = _ffprobe_duration(wav)
    if job['duration'] > MAX_DURATION:
        raise RuntimeError(f'Este áudio tem {_hms(job["duration"])}. O limite é {MAX_DURATION // 60} minutos para não estourar a memória da GPU.')
    mode, fmt = job['mode'], job['out_format']
    base = _safe_name(src['title'])
    names = {stem: f'stemlab_{stem.lower()}' for stem in MODES[mode]['stems']}   # nomes internos simples
    (_run_separator_mock if MOCK else _run_separator)(job, wav, mode, fmt, out_dir, names)
    _stage(job, 'export', 'Preparando prévias e arquivos…', 'running', 0)
    files = []
    stems = MODES[mode]['stems']
    for i, stem in enumerate(stems):
        _check_cancel(job)
        cand = [f for f in os.listdir(out_dir) if f.lower().startswith(names[stem]) and not f.endswith('.preview.mp3')]
        if not cand:
            raise RuntimeError(f'A faixa "{STEM_PT[stem]}" não foi gerada pelo separador.' + (' Detalhes: ' + ' | '.join(job.get('log_tail') or [])[-300:] if job.get('log_tail') else ''))
        path = os.path.join(out_dir, f'{base} - {STEM_PT[stem]}{os.path.splitext(cand[0])[1]}')
        os.replace(os.path.join(out_dir, cand[0]), path)
        prev = os.path.join(out_dir, f'{stem.lower()}.preview.mp3')
        _make_preview(path, prev)
        size = os.path.getsize(path)
        files.append({'stem': stem, 'label': STEM_PT[stem], 'icon': STEM_ICON[stem], 'color': STEM_COLOR[stem],
                      'file': os.path.basename(path), 'rel': f"{job['id']}/{os.path.basename(path)}",
                      'preview': f"{job['id']}/{os.path.basename(prev)}" if os.path.exists(prev) else None,
                      'size': size, 'size_label': _fmt_size(size),
                      'drive_path': _copy_to_drive(job, path, os.path.join('Faixas', base))})
        job['percent'] = (i + 1) / len(stems) * 100
    # prévia do original para comparação no mixer
    orig_prev = os.path.join(out_dir, 'original.preview.mp3')
    if _make_preview(wav, orig_prev):
        job['original_preview'] = f"{job['id']}/original.preview.mp3"
    job['files'] = files
    _stage(job, 'export', 'Concluído', 'done', 100)

def _run_download_job(job):
    src = STATE['sources'][job['source_id']]
    out_dir = os.path.join(OUT_DIR, job['id']); os.makedirs(out_dir, exist_ok=True)
    _stage(job, 'fetch', 'Baixando áudio do YouTube…', 'running', 0)
    path = _download_youtube_audio(job, src, out_dir, job['audio_format'], job['audio_quality'], job['embed_meta'], tag='final')
    _stage(job, 'export', 'Finalizando…', 'running', 50)
    size = os.path.getsize(path)
    job['files'] = [{'stem': 'Audio', 'label': 'Áudio', 'icon': '🎵', 'color': '#38bdf8', 'file': os.path.basename(path),
                     'rel': f"{job['id']}/{os.path.basename(path)}", 'size': size, 'size_label': _fmt_size(size), 'preview': None,
                     'drive_path': _copy_to_drive(job, path, 'Downloads')}]
    _stage(job, 'export', 'Concluído', 'done', 100)

def _run_job(job_id):
    job = STATE['jobs'][job_id]
    job['started'] = time.time()
    try:
        if job['kind'] == 'separate':
            _run_separate_job(job)
        else:
            _run_download_job(job)
        job['status'] = 'done'; job['percent'] = 100
    except yt_dlp.utils.DownloadCancelled:
        job['status'] = 'cancelled'; job['stage_label'] = 'Cancelado'
        for s in job['stages']:
            if s['status'] == 'running': s['status'] = 'cancelled'
    except Exception as e:
        job['status'] = 'error'; job['error'] = _friendly_error(str(e)); job['stage_label'] = 'Erro'
        for s in job['stages']:
            if s['status'] == 'running': s['status'] = 'error'
    job['finished'] = time.time()
    job['elapsed'] = round(job['finished'] - job['started'])

def _worker():
    while True:
        job_id = JOB_QUEUE.get()
        try:
            job = STATE['jobs'].get(job_id)
            if job and job.get('cancel'):
                job['status'] = 'cancelled'; job['stage_label'] = 'Cancelado'; job['finished'] = time.time()
            elif job:
                _run_job(job_id)
        except Exception as e:
            job = STATE['jobs'].get(job_id)
            if job:
                job['status'] = 'error'; job['error'] = _friendly_error(str(e)); job['finished'] = time.time()
        finally:
            JOB_QUEUE.task_done()

def _ensure_worker():
    w = STATE.get('worker')
    if not w or not w.is_alive():
        w = threading.Thread(target=_worker, daemon=True); w.start()
        STATE['worker'] = w

def cb_start_job(payload):
    try:
        src = STATE['sources'].get(payload.get('source_id'))
        if not src:
            return JSON({'ok': False, 'error': 'Fonte não encontrada. Analise o link ou envie o arquivo novamente.'})
        kind = payload.get('kind')
        job_id = uuid.uuid4().hex[:10]
        job = {'id': job_id, 'kind': kind, 'source_id': src['id'], 'title': src['title'], 'thumbnail': src.get('thumbnail'),
               'status': 'queued', 'cancel': False, 'created': time.time(), 'percent': 0, 'detail': '', 'stage': None,
               'stage_label': 'Na fila', 'files': [], 'error': None, 'warning': None,
               'save_drive': bool(payload.get('save_drive')), 'duration': src.get('duration') or 0}
        if kind == 'separate':
            mode = payload.get('mode'); fmt = payload.get('out_format', 'wav')
            if mode not in MODES: return JSON({'ok': False, 'error': 'Modo de separação inválido.'})
            if fmt not in OUT_FORMATS: return JSON({'ok': False, 'error': 'Formato de saída inválido.'})
            if src.get('too_long'):
                return JSON({'ok': False, 'error': f'Este áudio tem {src["duration_str"]}. O limite é {MAX_DURATION // 60} minutos.'})
            job.update({'mode': mode, 'mode_label': MODES[mode]['label'], 'out_format': fmt, 'stems': MODES[mode]['stems'],
                        'stages': [{'key': 'fetch', 'label': 'Obter o áudio', 'status': 'pending', 'percent': 0},
                                   {'key': 'model', 'label': 'Modelo de IA', 'status': 'pending', 'percent': 0},
                                   {'key': 'separate', 'label': 'Separar na GPU', 'status': 'pending', 'percent': 0},
                                   {'key': 'export', 'label': 'Exportar faixas', 'status': 'pending', 'percent': 0}],
                        'label': f"{MODES[mode]['label']} · {fmt.upper()}"})
            if not MOCK and not _gpu_info()['available']:
                job['warning'] = 'Sem GPU nesta sessão: a separação vai rodar no processador e pode demorar muitos minutos.'
        elif kind == 'download':
            if src['kind'] != 'youtube':
                return JSON({'ok': False, 'error': 'O download de áudio só vale para links do YouTube.'})
            fmt = payload.get('audio_format', 'mp3')
            if fmt not in ('mp3', 'm4a', 'opus', 'flac', 'wav', 'best'):
                return JSON({'ok': False, 'error': 'Formato de áudio inválido.'})
            job.update({'audio_format': fmt, 'audio_quality': str(payload.get('audio_quality', 'best')),
                        'embed_meta': bool(payload.get('embed_meta', True)),
                        'stages': [{'key': 'fetch', 'label': 'Baixar do YouTube', 'status': 'pending', 'percent': 0},
                                   {'key': 'export', 'label': 'Converter e finalizar', 'status': 'pending', 'percent': 0}],
                        'label': f"Áudio {'original' if fmt == 'best' else fmt.upper()}"})
        else:
            return JSON({'ok': False, 'error': 'Tipo de tarefa inválido.'})
        STATE['jobs'][job_id] = job
        ahead = sum(1 for j in STATE['jobs'].values() if j['id'] != job_id and j['status'] in ('queued', 'running'))
        JOB_QUEUE.put(job_id); _ensure_worker()
        return JSON({'ok': True, 'job_id': job_id, 'ahead': ahead})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

def _job_view(job):
    v = {k: val for k, val in job.items() if k not in ('cancel', 'proc')}
    v['ok'] = True
    if job['status'] == 'running' and job.get('started'):
        v['elapsed'] = round(time.time() - job['started'])
    v['ahead'] = sum(1 for j in STATE['jobs'].values() if j['id'] != job['id'] and j['status'] in ('queued', 'running')
                     and j['created'] < job['created']) if job['status'] == 'queued' else 0
    return v

def cb_job_status(job_id):
    job = STATE['jobs'].get(job_id)
    if not job:
        return JSON({'ok': False, 'error': 'Tarefa não encontrada.'})
    return JSON(_job_view(job))

def cb_jobs_list():
    try:
        out = []
        for j in sorted(STATE['jobs'].values(), key=lambda x: x['created']):
            out.append({'id': j['id'], 'kind': j['kind'], 'status': j['status'], 'label': j.get('label'), 'title': j.get('title'),
                        'thumbnail': j.get('thumbnail'), 'percent': round(j.get('percent') or 0), 'stage_label': j.get('stage_label'),
                        'error': j.get('error'), 'created': j['created'], 'files': len(j.get('files') or [])})
        return JSON({'ok': True, 'jobs': out, 'active': any(j['status'] in ('queued', 'running') for j in STATE['jobs'].values())})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_cancel_job(job_id):
    job = STATE['jobs'].get(job_id)
    if job:
        job['cancel'] = True
        p = job.get('proc')
        if p:
            try: p.kill()
            except Exception: pass
    return JSON({'ok': True})

def cb_zip_job(job_id):
    try:
        job = STATE['jobs'].get(job_id)
        if not job or not job.get('files'): return JSON({'ok': False, 'error': 'Nenhum arquivo para compactar.'})
        src = os.path.join(OUT_DIR, job_id)
        name = _safe_name(job.get('title') or 'faixas', 60)
        tmp = os.path.join(OUT_DIR, f'{job_id}_zipsrc'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        for f in job['files']:
            shutil.copy2(os.path.join(src, f['file']), os.path.join(tmp, f['file']))
        zp = shutil.make_archive(os.path.join(OUT_DIR, f'{job_id}_{re.sub(r"[^\w.-]+", "_", name)}'), 'zip', tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        drive = _copy_to_drive(job, zp, 'Faixas') if job.get('save_drive') else None
        return JSON({'ok': True, 'rel': os.path.basename(zp), 'size_label': _fmt_size(os.path.getsize(zp)), 'drive_path': drive})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_colab_download(rel):
    """Download pelo mecanismo nativo do Colab (vai direto para a pasta Downloads do navegador)."""
    try:
        path = os.path.normpath(os.path.join(OUT_DIR, rel))
        if not path.startswith(os.path.normpath(OUT_DIR)) or not os.path.exists(path):
            raise FileNotFoundError('Arquivo não encontrado (a sessão pode ter sido reiniciada).')
        from google.colab import files as colab_files
        colab_files.download(path)
        return JSON({'ok': True})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_preview_b64(rel):
    """Plano B do mixer: entrega a prévia em base64 pela ponte do Colab quando o proxy de portas não responde."""
    try:
        path = os.path.normpath(os.path.join(OUT_DIR, rel))
        if not path.startswith(os.path.normpath(OUT_DIR)) or not os.path.exists(path):
            raise FileNotFoundError('Prévia não encontrada.')
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return JSON({'ok': True, 'b64': data, 'mime': 'audio/mpeg'})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_cleanup():
    try:
        for j in list(STATE['jobs'].values()):
            if j['status'] in ('queued', 'running'):
                return JSON({'ok': False, 'error': 'Há tarefas em andamento. Aguarde ou cancele antes de limpar.'})
        shutil.rmtree(OUT_DIR, ignore_errors=True); os.makedirs(OUT_DIR, exist_ok=True)
        shutil.rmtree(WORK_DIR, ignore_errors=True); os.makedirs(WORK_DIR, exist_ok=True)
        STATE['jobs'].clear(); STATE['sources'].clear()
        return JSON({'ok': True})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- pré-download do modelo padrão (em segundo plano) ----------
def _prefetch_model(model):
    if MOCK or _model_ready(model) or STATE['prefetch'].get(model):
        return
    STATE['prefetch'][model] = 'running'
    def run():
        try:
            subprocess.run(_sep_cmd() + ['--download_model_only', '--model_filename', model,
                            '--model_file_dir', MODELS_DIR, '--log_level', 'warning'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
            STATE['prefetch'][model] = 'done' if _model_ready(model) else 'failed'
        except Exception:
            STATE['prefetch'][model] = 'failed'
    threading.Thread(target=run, daemon=True).start()

def cb_models_status():
    return JSON({'ok': True, 'models': {k: {'ready': _model_ready(v['model']), 'prefetch': STATE['prefetch'].get(v['model'])} for k, v in MODES.items()}})

# ---------- servidor de arquivos (prévias do mixer, com suporte a Range) ----------
class _FileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=OUT_DIR, **k)
    def log_message(self, *a): pass
    def list_directory(self, path):
        self.send_error(403, 'Listagem desabilitada'); return None
    def do_GET(self):
        path = self.translate_path(self.path.split('?')[0])
        if os.path.isdir(path) or not os.path.exists(path):
            return super().do_GET()
        size = os.path.getsize(path)
        rng = self.headers.get('Range')
        start, end = 0, size - 1
        if rng and rng.startswith('bytes='):
            a, _, b = rng[6:].partition('-')
            try:
                start = int(a) if a else max(0, size - int(b))
                end = int(b) if (a and b) else end
            except ValueError:
                start, end = 0, size - 1
            if start >= size:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.end_headers(); return
            end = min(end, size - 1)
        ctype = self.guess_type(path)
        self.send_response(206 if rng else 200)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if rng: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        with open(path, 'rb') as f:
            f.seek(start); remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): break
                remaining -= len(chunk)

def _start_file_server():
    if STATE.get('server'): return
    class _Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True; daemon_threads = True
    try:
        srv = _Srv(('0.0.0.0', FILE_PORT), _FileHandler)
    except OSError:
        return
    STATE['server'] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()

_start_file_server()
_prefetch_model(MODES['2stem']['model'])

# ---------- registro das funções para a interface ----------
def _register(name, fn):
    try:
        from google.colab import output as _out
        _out.register_callback(f'stemlab.{name}', fn)
    except Exception:
        pass

for _n, _f in {
    'bootstrap': cb_bootstrap, 'save_cookies': cb_save_cookies, 'clear_cookies': cb_clear_cookies, 'test_cookies': cb_test_cookies,
    'analyze': cb_analyze, 'upload_start': cb_upload_start, 'upload_chunk': cb_upload_chunk, 'upload_finish': cb_upload_finish,
    'start_job': cb_start_job, 'job_status': cb_job_status, 'jobs_list': cb_jobs_list, 'cancel_job': cb_cancel_job,
    'zip_job': cb_zip_job, 'colab_download': cb_colab_download, 'cleanup': cb_cleanup, 'models_status': cb_models_status,
    'preview_b64': cb_preview_b64,
}.items():
    _register(_n, _f)
