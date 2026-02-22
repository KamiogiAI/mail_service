-- ユーザーメール履歴テーブル
-- 購読管理画面からユーザー別に送信済みメールを確認するため
-- ユーザー×プランごとに最新10件のみ保持

CREATE TABLE IF NOT EXISTS user_email_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    plan_id INT NULL,
    delivery_id INT NULL,
    subject VARCHAR(500) NOT NULL,
    body_html MEDIUMTEXT NOT NULL,
    sent_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_plan_sent (user_id, plan_id, sent_at DESC),
    INDEX idx_delivery_user (delivery_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE SET NULL,
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE SET NULL
);
