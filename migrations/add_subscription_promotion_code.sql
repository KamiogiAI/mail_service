-- subscriptions テーブルに promotion_code_id カラムを追加
ALTER TABLE subscriptions
ADD COLUMN promotion_code_id INT NULL COMMENT '適用プロモーションコード' AFTER trial_end,
ADD INDEX ix_subscriptions_promotion_code_id (promotion_code_id),
ADD CONSTRAINT fk_subscriptions_promotion_code
    FOREIGN KEY (promotion_code_id) REFERENCES promotion_codes(id) ON DELETE SET NULL;
