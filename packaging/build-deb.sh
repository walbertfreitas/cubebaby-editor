#!/bin/bash
# Gera o pacote .deb do Cube Baby Editor (arquitetura "all": só Python, usa as bibliotecas do sistema).
# Uso: packaging/build-deb.sh   → dist/cubebaby-editor_<versão>_all.deb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
PKG=cubebaby-editor
BUILD="$(mktemp -d)"
STAGE="$BUILD/${PKG}_${VERSION}_all"
trap 'rm -rf "$BUILD"' EXIT

# Código Python
install -d "$STAGE/usr/lib/$PKG/cubebaby"
install -m 644 "$ROOT"/cubebaby/*.py "$ROOT/cubebaby/icon.svg" "$STAGE/usr/lib/$PKG/cubebaby/"

# Comando
install -d "$STAGE/usr/bin"
cat > "$STAGE/usr/bin/$PKG" <<'EOF'
#!/bin/sh
PYTHONPATH=/usr/lib/cubebaby-editor${PYTHONPATH:+:$PYTHONPATH} exec /usr/bin/python3 -m cubebaby "$@"
EOF
chmod 755 "$STAGE/usr/bin/$PKG"

# Menu e ícone
install -D -m 644 "$ROOT/packaging/$PKG.desktop" "$STAGE/usr/share/applications/$PKG.desktop"
install -D -m 644 "$ROOT/cubebaby/icon.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/$PKG.svg"

# Documentação
DOC="$STAGE/usr/share/doc/$PKG"
install -D -m 644 "$ROOT/packaging/copyright" "$DOC/copyright"
gzip -9n -c "$ROOT/packaging/changelog" > "$DOC/changelog.gz"
chmod 644 "$DOC/changelog.gz"

# Metadados
install -d "$STAGE/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/control.in" > "$STAGE/DEBIAN/control"

# Remove caches de Python que possam ter vindo junto
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/" >/dev/null
echo "Pacote gerado: $ROOT/dist/${PKG}_${VERSION}_all.deb"
