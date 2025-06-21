import os
import yt_dlp
import re
import threading
import uuid
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['UPLOAD_FOLDER'] = os.path.abspath('downloads')
app.secret_key = 'tu_clave_secreta_aqui_12345'

# Variables globales para control de descarga
download_progress = {
    'percent': '0%',
    'status': 'Preparando descarga...',
    'filename': '',
    'active': False,
    'cancel_requested': False,
    'temp_dir': None
}

def get_ffmpeg_path():
    """Obtiene la ruta de FFmpeg"""
    possible_paths = [
        'C:\\ffmpeg\\bin\\ffmpeg.exe',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg'
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return 'ffmpeg'

def clean_filename(filename):
    """Limpia el nombre de archivo de caracteres inválidos"""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def progress_hook(d):
    """Callback para el progreso de descarga"""
    global download_progress
    if download_progress['cancel_requested']:
        raise Exception("Descarga cancelada por el usuario")
    
    if d['status'] == 'downloading':
        percent_str = re.sub(r'\x1b\[[0-9;]*[mK]', '', d['_percent_str'])
        clean_percent = ''.join(filter(lambda x: x.isdigit() or x == '.', percent_str))
        
        try:
            percent_value = float(clean_percent) if clean_percent else 0.0
            download_progress['percent'] = f"{min(100, percent_value)}%"
            download_progress['status'] = f"Descargando... {download_progress['percent']}"
        except ValueError:
            download_progress['percent'] = "0%"
            download_progress['status'] = "Descargando..."
            
    elif d['status'] == 'finished':
        download_progress['status'] = "Convirtiendo a MP3..."
        download_progress['percent'] = "100%"

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    """Inicia la descarga"""
    global download_progress
    
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'Por favor ingresa una URL'}), 400
    
    # Extraer solo el video individual si es una lista
    url = url.split('&list=')[0].split('&')[0]
    
    try:
        # Crear directorio de descargas si no existe
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Crear un directorio temporal único
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        download_progress = {
            'percent': '0%',
            'status': 'Iniciando descarga...',
            'filename': '',
            'active': True,
            'cancel_requested': False,
            'temp_dir': temp_dir
        }
        
        thread = threading.Thread(target=process_download, args=(url, temp_dir))
        thread.start()
        return jsonify({'message': 'Descarga iniciada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_download(url, temp_dir):
    """Procesa la descarga en un hilo separado"""
    global download_progress
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s').replace('\\', '/'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'extractaudio': True,
            'audioformat': 'mp3',
            'restrictfilenames': True,
            'noplaylist': True,
            'windowsfilenames': True,
            'no_color': True,
            'ffmpeg_location': get_ffmpeg_path()
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace('\\', '/')
            
            # Verificar si el archivo ya está en formato MP3
            if not filename.endswith('.mp3'):
                mp3_filename = os.path.splitext(filename)[0] + '.mp3'
                if os.path.exists(filename):
                    os.rename(filename, mp3_filename)
                filename = mp3_filename
            
            # Mover el archivo a la ubicación final (fuera del temp)
            final_filename = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(filename))
            if os.path.exists(filename):
                os.replace(filename, final_filename)
            
            download_progress.update({
                'status': '¡Descarga completada!',
                'percent': '100%',
                'filename': final_filename.replace('\\', '/'),
                'active': False
            })
    except Exception as e:
        download_progress.update({
            'status': f'Error: {str(e)}',
            'active': False
        })
    finally:
        # Limpiar directorio temporal si está vacío
        try:
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except Exception as e:
            print(f"Error al limpiar directorio temporal: {str(e)}")

@app.route('/progress')
def get_progress():
    """Obtiene el progreso actual de la descarga"""
    return jsonify(download_progress)

@app.route('/cancel', methods=['POST'])
def cancel_download():
    """Cancela la descarga en curso"""
    global download_progress
    download_progress['cancel_requested'] = True
    
    # Intentar eliminar archivos temporales
    if download_progress.get('temp_dir'):
        try:
            if os.path.exists(download_progress['temp_dir']):
                for file in os.listdir(download_progress['temp_dir']):
                    os.remove(os.path.join(download_progress['temp_dir'], file))
                os.rmdir(download_progress['temp_dir'])
        except Exception as e:
            print(f"Error al limpiar archivos temporales: {str(e)}")
    
    return jsonify({'message': 'Cancelación solicitada'})

@app.route('/get_file')
def serve_file():
    """Sirve el archivo descargado"""
    filename = request.args.get('filename')
    
    if not filename:
        return jsonify({'error': 'Nombre de archivo no proporcionado'}), 400
    
    try:
        # Normalizar la ruta del archivo
        filename = filename.replace('%5C', '/').replace('\\', '/')
        
        # Verificar si la ruta es absoluta o relativa
        if not os.path.isabs(filename):
            filename = os.path.join(app.config['UPLOAD_FOLDER'], filename.split('/')[-1])
        
        # Verificar existencia del archivo
        if not os.path.exists(filename):
            return jsonify({
                'error': 'Archivo no encontrado',
                'suggested_fix': 'Intente descargar nuevamente',
                'filename': filename
            }), 404
        
        # Obtener nombre limpio para la descarga
        clean_name = os.path.basename(filename)
        return send_file(
            filename,
            as_attachment=True,
            download_name=clean_name,
            mimetype='audio/mpeg'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Crear directorio de descargas si no existe
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Configuración para desarrollo
    app.run(debug=True, threaded=True)