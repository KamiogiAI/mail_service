# VPS移行手順書 - mail_service (さくらのVPS Ubuntu 22.04)

本書は、mail_service を既にvps_noteが稼働中のさくらのVPS（Ubuntu 22.04）に移行する手順を記載する。
既存システムに影響を与えず、独立して稼働させる。

---

## 前提条件

| 項目 | 内容 |
|------|------|
| VPS | さくらのVPS (vps_noteが稼働中) |
| OS | Ubuntu 22.04 LTS |
| 既存システム | `/opt/vps_note` (ポート8080使用) |
| ドメイン | soccermeshi.com |
| DNS | soccermeshi.com の Aレコードが VPS の IP を指していること |

### 既存システムとのポート割り当て

| システム | アプリ | MySQL | Redis | その他 |
|----------|--------|-------|-------|--------|
| vps_note (既存) | 8080 | 3306 | - | Chrome: 4444, 7900 |
| mail_service (今回) | 8081 | 3307 | 6380 | - |

---

## 1. プロジェクトディレクトリの作成

```bash
# VPSにSSH接続
ssh deploy@<VPSのIPアドレス>

# ディレクトリ作成
sudo mkdir -p /opt/mail_service
sudo chown deploy:deploy /opt/mail_service

# 旧フォームページ用ディレクトリ (soccermeshi.com/form)
sudo mkdir -p /opt/mail_service_legacy_form
sudo chown deploy:deploy /opt/mail_service_legacy_form
```

---

## 2. ファイル転送

### 2-1. mail_service 本体

ローカルPCで実行:

```bash
cd /Users/shiromaruedit/Desktop/vps_mail/mail_service

rsync -avz --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='mysql_data' \
  --exclude='redis_data' \
  --exclude='.DS_Store' \
  --exclude='*.pyc' \
  ./ deploy@153.120.43.86:/opt/mail_service/
```

### 2-2. 旧フォームページ (soccermeshi.com/form 用)

```bash
cd /Users/shiromaruedit/Desktop/vps_mail

rsync -avz --exclude='.DS_Store' \
  automail_form_frontend/ deploy@153.120.43.86:/opt/mail_service_legacy_form/
```

---

## 3. docker-compose.yml のポート変更

VPSで `/opt/mail_service/docker-compose.yml` を編集し、既存システムとのポート競合を回避する。

```bash
cd /opt/mail_service
vi docker-compose.yml
```

以下のように変更:

```yaml
services:
  api:
    build: .
    ports:
      - "127.0.0.1:8081:8000"  # 8000→8081に変更、localhostのみ
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    restart: unless-stopped
    container_name: mail_service_api

  db:
    image: mysql:8.0
    ports:
      - "127.0.0.1:3307:3306"  # 3306→3307に変更
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-rootpassword}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-mail_service}
      MYSQL_USER: ${MYSQL_USER:-mailuser}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-mailpassword}
    volumes:
      - mail_service_mysql:/var/lib/mysql
    command: >
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --default-authentication-plugin=mysql_native_password
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-rootpassword}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    container_name: mail_service_db

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:6380:6379"  # 6379→6380に変更
    volumes:
      - mail_service_redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    container_name: mail_service_redis

  # nginx は削除 (ホストのNginxを使用)
  # nginx:
  #   ...

  worker:
    build: .
    command: python -m app.worker
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    restart: unless-stopped
    container_name: mail_service_worker

  scheduler:
    build: .
    command: python -m app.scheduler
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    restart: unless-stopped
    container_name: mail_service_scheduler

volumes:
  mail_service_mysql:
  mail_service_redis:
```

**重要な変更点:**
- `nginx` サービスを削除（ホストのNginxを使用）
- 全ポートを `127.0.0.1` にバインド
- ボリューム名を `mail_service_` プレフィックスに変更
- コンテナ名を明示的に設定

---

## 4. 本番用オーバーライドの作成

```bash
vi /opt/mail_service/docker-compose.prod.yml
```

```yaml
# 本番用オーバーライド: docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  api:
    volumes:
      - ./backend:/app
      - ./alembic:/app/alembic
      - ./alembic.ini:/app/alembic.ini
    environment:
      - DEBUG=false
    restart: always

  db:
    restart: always

  redis:
    restart: always

  worker:
    volumes:
      - ./backend:/app
    environment:
      - DEBUG=false
    restart: always

  scheduler:
    volumes:
      - ./backend:/app
    environment:
      - DEBUG=false
    restart: always
```

---

## 5. 環境変数ファイルの作成

```bash
cd /opt/mail_service
cp .env.example .env
vi .env
```

以下を設定:

```bash
# ===========================================
# Mail Service 本番環境設定
# ===========================================

# --- データベース ---
MYSQL_ROOT_PASSWORD=<強力なパスワードを生成>
MYSQL_DATABASE=mail_service
MYSQL_USER=mailuser
MYSQL_PASSWORD=<強力なパスワードを生成>
DATABASE_URL=mysql+pymysql://mailuser:<上記パスワード>@db:3306/mail_service?charset=utf8mb4

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- セキュリティ ---
# AES暗号化キー (32バイト hex) - 以下で生成:
# python3 -c "import secrets; print(secrets.token_hex(32))"
AES_KEY=<生成したキー>

# JWTシークレット
JWT_SECRET=<任意のシークレット文字列>

# --- Stripe ---
STRIPE_SECRET_KEY=sk_live_xxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx

# --- Resend ---
RESEND_API_KEY=re_xxxxxxxx
RESEND_FROM_EMAIL=noreply@soccermeshi.com
RESEND_WEBHOOK_SECRET=<Resend管理画面から取得>

# --- OpenAI ---
OPENAI_API_KEY=sk-proj-xxxxxxxx

# --- サービス設定 ---
SITE_URL=https://soccermeshi.com
SITE_NAME=SoccerMeshi Mail
ALLOWED_ORIGINS=https://soccermeshi.com

# --- セッション ---
SESSION_TIMEOUT_MINUTES=60

# --- スケジューラ ---
SCHEDULER_TOKEN=<任意のトークン>

# --- 環境 ---
ENV=production
DEBUG=false
```

> **重要**: DATABASE_URL と REDIS_URL のホスト名は `db`, `redis` のままにする（Docker内部ネットワーク名）

---

## 6. SSL証明書の取得

### 6-1. 仮のNginx設定（証明書取得用）

```bash
sudo tee /etc/nginx/sites-available/soccermeshi.com <<'EOF'
server {
    listen 80;
    server_name soccermeshi.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'ok';
        add_header Content-Type text/plain;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/soccermeshi.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 6-2. 証明書の取得

**DNSのAレコードが正しく設定されていることを確認してから実行:**

```bash
sudo certbot --nginx -d soccermeshi.com
```

---

## 7. Nginx本番設定

```bash
sudo tee /etc/nginx/sites-available/soccermeshi.com <<'NGINX_EOF'
# HTTP → HTTPS リダイレクト
server {
    listen 80;
    server_name soccermeshi.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name soccermeshi.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/soccermeshi.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/soccermeshi.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # セキュリティヘッダー
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # ==================================
    # 旧フォームページ (将来削除予定)
    # ==================================
    location /form/ {
        alias /opt/mail_service_legacy_form/;
        index index.html;
        try_files $uri $uri/ /form/index.html;
    }
    location /form {
        return 301 /form/;
    }

    # ==================================
    # API (FastAPI)
    # ==================================
    location /api/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_connect_timeout 30s;
        client_max_body_size 10m;
    }

    location /health {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
    }

    # ==================================
    # 管理画面 (SPA)
    # ==================================
    location /admin/ {
        alias /opt/mail_service/frontend/admin/;
        index index.html;
        try_files $uri $uri/ /admin/index.html;
    }

    # ==================================
    # ユーザーページ
    # ==================================
    location /user/ {
        alias /opt/mail_service/frontend/user/;
        try_files $uri $uri/ =404;
    }

    # ==================================
    # 共通アセット
    # ==================================
    location /assets/ {
        alias /opt/mail_service/frontend/assets/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # ==================================
    # 公開ページ (デフォルト)
    # ==================================
    location / {
        root /opt/mail_service/frontend/public;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # ログ
    access_log /var/log/nginx/soccermeshi.com.access.log;
    error_log /var/log/nginx/soccermeshi.com.error.log;
}
NGINX_EOF
```

設定の有効化:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 8. データベースのセットアップ

### 8-1. MySQLコンテナのみ先に起動

```bash
cd /opt/mail_service
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db
```

起動を待つ:

```bash
docker compose logs -f db
# "ready for connections" が表示されるまで待つ (Ctrl+C で終了)
```

### 8-2. マイグレーション実行

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
```

---

## 9. 全サービスの起動

```bash
cd /opt/mail_service
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

起動確認:

```bash
docker compose ps
```

5つのコンテナが `running` であることを確認:
- `mail_service_api`
- `mail_service_db`
- `mail_service_redis`
- `mail_service_worker`
- `mail_service_scheduler`

---

## 10. 動作確認

### 10-1. ヘルスチェック

```bash
curl https://soccermeshi.com/health
# {"status":"ok","database":"ok","redis":"ok"} が返ればOK
```

### 10-2. 各ページの確認

| URL | 内容 |
|-----|------|
| https://soccermeshi.com/ | 公開トップページ |
| https://soccermeshi.com/admin/ | 管理画面 |
| https://soccermeshi.com/user/mypage.html | ユーザーマイページ |
| https://soccermeshi.com/form/ | 旧フォームページ (レガシー) |

### 10-3. ログ確認

```bash
# APIログ
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api

# スケジューラーログ
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f scheduler

# ワーカーログ
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker
```

---

## 11. Webhook設定

### 11-1. Stripe Webhook

Stripe管理画面で以下を設定:
- **Endpoint URL**: `https://soccermeshi.com/api/webhooks/stripe`
- **Events**:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`

取得した Webhook Secret を `.env` の `STRIPE_WEBHOOK_SECRET` に設定し、再起動:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api
```

### 11-2. Resend Webhook

Resend管理画面で以下を設定:
- **Endpoint URL**: `https://soccermeshi.com/api/webhooks/resend`
- **Events**: すべて選択

---

## 12. 管理者ユーザーの作成

初回ログイン用の管理者を作成:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python -c "
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash
import uuid

db = SessionLocal()
admin = User(
    member_no='ADMIN001',
    email='admin@soccermeshi.com',
    password_hash=get_password_hash('初期パスワード'),
    name_last='管理者',
    name_first='',
    role='admin',
    email_verified=True,
    is_active=True,
    unsubscribe_token=str(uuid.uuid4()),
)
db.add(admin)
db.commit()
print('管理者を作成しました')
db.close()
"
```

> **重要**: 作成後、管理画面からパスワードを変更してください

---

## 13. バックアップ設定

### 13-1. バックアップスクリプト

```bash
sudo mkdir -p /opt/mail_service/scripts
sudo mkdir -p /opt/mail_service/backups

sudo tee /opt/mail_service/scripts/backup_db.sh <<'EOF'
#!/bin/bash
BACKUP_DIR=/opt/mail_service/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# MySQL パスワードを .env から取得
source /opt/mail_service/.env

docker exec mail_service_db mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" mail_service | gzip > $BACKUP_DIR/mail_service_$TIMESTAMP.sql.gz

# 30日以上前のバックアップを削除
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "$(date): Backup complete - mail_service_$TIMESTAMP.sql.gz"
EOF

chmod +x /opt/mail_service/scripts/backup_db.sh
```

### 13-2. crontab登録

```bash
crontab -e
```

追加:

```
# mail_service DBバックアップ (毎日5時)
0 5 * * * /opt/mail_service/scripts/backup_db.sh >> /opt/mail_service/logs/backup.log 2>&1
```

---

## 14. 運用コマンド

### ログ確認

```bash
cd /opt/mail_service

# 全サービスのログ
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# 特定サービス
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f scheduler
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker
```

### サービスの再起動

```bash
cd /opt/mail_service

# 全体
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart

# 特定サービス
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api
```

### コードの更新

ローカルPCで実行:

```bash
rsync -avz --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='mysql_data' \
  --exclude='redis_data' \
  --exclude='.DS_Store' \
  ./backend/ deploy@<VPSのIPアドレス>:/opt/mail_service/backend/

rsync -avz --exclude='.DS_Store' \
  ./frontend/ deploy@<VPSのIPアドレス>:/opt/mail_service/frontend/
```

VPSで再起動:

```bash
cd /opt/mail_service
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api worker scheduler
```

### マイグレーション実行

```bash
cd /opt/mail_service
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api worker scheduler
```

### MySQL接続

```bash
docker exec -it mail_service_db mysql -u mailuser -p mail_service
```

---

## 15. 旧フォームページの削除手順 (将来)

不要になったら以下を実行:

### 15-1. Nginx設定から削除

`/etc/nginx/sites-available/soccermeshi.com` から以下を削除:

```nginx
    # ==================================
    # 旧フォームページ (将来削除予定)
    # ==================================
    location /form/ {
        alias /opt/mail_service_legacy_form/;
        index index.html;
        try_files $uri $uri/ /form/index.html;
    }
    location /form {
        return 301 /form/;
    }
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 15-2. ファイル削除

```bash
sudo rm -rf /opt/mail_service_legacy_form
```

---

## 16. チェックリスト

移行完了後、以下を確認:

- [ ] `https://soccermeshi.com/health` でヘルスチェックOK
- [ ] `https://soccermeshi.com/` でトップページ表示
- [ ] `https://soccermeshi.com/admin/` で管理画面表示
- [ ] 管理者でログインできる
- [ ] `https://soccermeshi.com/form/` で旧フォーム表示
- [ ] 新規ユーザー登録ができる
- [ ] メール認証メールが届く
- [ ] Stripeテスト決済が完了する
- [ ] `docker compose ps` で5コンテナがrunning
- [ ] SSL証明書が有効（ブラウザで鍵マーク確認）
- [ ] 既存の yoso-ya.net (vps_note) に影響なし

---

## トラブルシューティング

### コンテナが起動しない

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs <サービス名>
```

### ポート競合エラー

```bash
# 使用中のポートを確認
sudo netstat -tlnp | grep -E '8081|3307|6380'

# 必要に応じてポートを変更
```

### MySQLに接続できない

```bash
# コンテナの状態確認
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps db
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs db
```

### Nginxエラー

```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/soccermeshi.com.error.log
```

### 既存システム (vps_note) への影響確認

```bash
# vps_noteのコンテナ状態
docker compose -f /opt/vps_note/docker-compose.yml -f /opt/vps_note/docker-compose.prod.yml ps

# yoso-ya.net へのアクセス確認
curl -I https://yoso-ya.net/health
```

---

## 補足: 両システムの構成図

```
┌─────────────────────────────────────────────────────────────────┐
│                     さくらのVPS (Ubuntu 22.04)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Nginx (ホスト)                          │   │
│  │  ポート 80, 443                                          │   │
│  │                                                          │   │
│  │  yoso-ya.net → 127.0.0.1:8080 (vps_note)                │   │
│  │  soccermeshi.com → 127.0.0.1:8081 (mail_service)        │   │
│  │  soccermeshi.com/form → /opt/mail_service_legacy_form/  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│          ┌────────────────┴────────────────┐                    │
│          ▼                                 ▼                    │
│  ┌───────────────────┐          ┌───────────────────┐          │
│  │ vps_note (既存)   │          │ mail_service      │          │
│  │ /opt/vps_note     │          │ /opt/mail_service │          │
│  ├───────────────────┤          ├───────────────────┤          │
│  │ app:8080          │          │ api:8081          │          │
│  │ mysql:3306        │          │ db:3307           │          │
│  │ chrome:4444,7900  │          │ redis:6380        │          │
│  └───────────────────┘          │ worker            │          │
│                                  │ scheduler         │          │
│                                  └───────────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
