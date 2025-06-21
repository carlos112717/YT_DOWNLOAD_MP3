# Usa una imagen base de Python
FROM python:3.9-slim

# Establece el directorio de trabajo
WORKDIR /app

# Usa esta línea para asegurar compatibilidad con rutas Windows
RUN mkdir -p /app/downloads && chmod -R 777 /app/downloads

# Instala dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copia los archivos de requisitos primero para caché
COPY requirements.txt .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto de los archivos
COPY . .

# Crea el directorio de descargas
RUN mkdir -p /app/downloads

# Variables de entorno
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Puerto expuesto
EXPOSE 5000

# Comando para ejecutar la aplicación
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]