#!/bin/bash
set -euo pipefail

# ============================================================
# デプロイスクリプト
# 使用方法: bash deploy.sh [--init] [--ssl DOMAIN]
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="/opt/mail_service_xx"
COMPOSE_CMD="docker compose"

# docker compose v1 フォールバック
if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
fi

usage() {
    echo "使用方法: bash deploy.sh [OPTIONS]"
    echo ""
    echo "オプション:"
    echo "  --init          初回セットアップ (ディレクトリ作成、DB初期化)"
    echo "  --ssl DOMAIN    SSL証明書を取得 (Let's Encrypt)"
    echo "  --migrate       Alembicマイグレーション実行"
    echo "  --restart       サービス再起動のみ"
    echo "  --help          ヘルプ表示"
    exit 0
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# .envファイル確認
check_env() {
    if [ ! -f "$DEPLOY_DIR/.env" ]; then
        echo "エラー: $DEPLOY_DIR/.env が見つかりません"
        echo ".env.example をコピーして設定してください:"
        echo "  cp $SCRIPT_DIR/.env.example $DEPLOY_DIR/.env"
        echo "  vim $DEPLOY_DIR/.env"
        exit 1
    fi
}

# 初回セットアップ
init_setup() {
    log "初回セットアップ開始"

    # デプロイディレクトリ作成
    if [ ! -d "$DEPLOY_DIR" ]; then
        sudo mkdir -p "$DEPLOY_DIR"
        sudo chown "$(whoami):" "$DEPLOY_DIR"
        log "デプロイディレクトリ作成: $DEPLOY_DIR"
    fi

    # ファイルコピー
    sync_files

    # .env確認
    if [ ! -f "$DEPLOY_DIR/.env" ]; then
        cp "$SCRIPT_DIR/.env.example" "$DEPLOY_DIR/.env"
        log ".env.example をコピーしました。設定を編集してください:"
        log "  vim $DEPLOY_DIR/.env"
        exit 0
    fi

    # ビルド & 起動
    cd "$DEPLOY_DIR"
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml build
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d db redis
    log "DB/Redis起動待機中..."
    sleep 15

    # マイグレーション
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
    log "マイグレーション完了"

    # 全サービス起動
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d
    log "初回セットアップ完了"
}

# ファイル同期
sync_files() {
    log "ファイル同期中..."
    rsync -av --exclude='.env' \
              --exclude='__pycache__' \
              --exclude='*.pyc' \
              --exclude='.git' \
              --exclude='mysql_data' \
              --exclude='redis_data' \
              "$SCRIPT_DIR/" "$DEPLOY_DIR/"
    log "ファイル同期完了"
}

# SSL証明書取得
setup_ssl() {
    local domain="$1"
    log "SSL証明書取得: $domain"

    cd "$DEPLOY_DIR"

    # Nginx起動 (HTTP のみ)
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d nginx

    # certbot実行
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot \
        certbot certonly --webroot \
        --webroot-path=/var/www/certbot \
        --email "admin@${domain}" \
        --agree-tos \
        --no-eff-email \
        -d "$domain"

    log "SSL証明書取得完了"
    log "nginx/conf.d/mail_service.conf のHTTPS設定をアンコメントしてください:"
    log "  - server_name を $domain に変更"
    log "  - ssl_certificate パスを確認"
    log "  - HTTPリダイレクトを有効化"
    log "その後 bash deploy.sh --restart を実行"
}

# マイグレーション
run_migrate() {
    log "マイグレーション実行"
    cd "$DEPLOY_DIR"
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
    log "マイグレーション完了"
}

# デプロイ (通常)
deploy() {
    log "デプロイ開始"
    check_env
    sync_files
    cd "$DEPLOY_DIR"

    # ビルド
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml build

    # マイグレーション
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head

    # サービス再起動
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d
    log "デプロイ完了"
}

# 再起動
restart_services() {
    log "サービス再起動"
    cd "$DEPLOY_DIR"
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml restart
    log "再起動完了"
}

# メインロジック
case "${1:-}" in
    --init)
        init_setup
        ;;
    --ssl)
        if [ -z "${2:-}" ]; then
            echo "エラー: ドメインを指定してください: bash deploy.sh --ssl example.com"
            exit 1
        fi
        setup_ssl "$2"
        ;;
    --migrate)
        check_env
        run_migrate
        ;;
    --restart)
        check_env
        restart_services
        ;;
    --help)
        usage
        ;;
    *)
        check_env
        deploy
        ;;
esac
