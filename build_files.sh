#!/usr/bin/env bash
# ============================================================
# build_files.sh — Script de build exécuté par Vercel
#
# Ordre d'exécution :
#   1. pip install (géré automatiquement par Vercel via requirements.txt)
#   2. Ce script
#   3. Démarrage du serveur WSGI (config/wsgi.py)
#
# DATABASE_URL doit être défini dans les variables d'environnement
# Vercel pour que migrate s'applique sur Postgres.
# ============================================================
set -e   # arrêter immédiatement en cas d'erreur

echo "==> Applying database migrations..."
python manage.py migrate --no-input

echo "==> Collecting static files..."
python manage.py collectstatic --no-input --clear

echo "==> Build complete."
