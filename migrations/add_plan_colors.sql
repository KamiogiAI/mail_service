-- plans テーブルに背景色・文字色カラムを追加
ALTER TABLE plans
ADD COLUMN bg_color VARCHAR(7) DEFAULT '#ffffff' COMMENT '背景色 (HEX)' AFTER sort_order,
ADD COLUMN text_color VARCHAR(7) DEFAULT '#000000' COMMENT '文字色 (HEX)' AFTER bg_color;
