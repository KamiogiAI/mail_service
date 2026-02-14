#!/usr/bin/env python3
"""12プランを追加するスクリプト"""
import sys
sys.path.insert(0, '/app')

from app.core.database import SessionLocal
from app.models.plan import Plan
from app.models.plan_question import PlanQuestion
from app.services import stripe_service

# 松浦さん指定の個別指示
INDIVIDUAL_INSTRUCTION = """━━━━━━━━━━━━━━━━━━
【入力情報】
━━━━━━━━━━━━━━━━━━
① 生年月日：{birthday}
② 性別：{maleorfemale}
③ 身長：{height}
④ 体重：{weight}
⑤ 好物：{likes}
⑥ 嫌いな物：{dislikes}
⑦ ポジション（FW / MF / DF / GK）：{position}
⑧ 練習する曜日（試合含む）：{practiceday}

各ユーザーの過去の送信履歴を見て、類似するメニューの生成は禁止する。
必ず過去の履歴を参照し、直前に送信された内容の「続き」となる1食のみを生成すること。
1回のメール配信につき、出力は常に1食分のみとする（週2回プラン等であっても1通に複数食を含めない）。

履歴上、最終送信日から1週間以上経過している場合は「新しい週」と判定し、各プランの第1食目として再開すること。
履歴が同一週内であれば、前回の第◯食に続く番号で1食のみ生成すること。

情報が入力されていない場合は、指定なしとして処理すること。未入力項目がある場合、本文の最後に以下の文章を入れる

※質問に回答されていない項目があります。マイページにログインして質問に回答することで、更に分析ができます。"""

# 質問項目のテンプレート
QUESTIONS = [
    {"variable_name": "birthday", "label": "生年月日", "question_type": "date", "is_required": True, "carry_over": False},
    {"variable_name": "maleorfemale", "label": "性別", "question_type": "select", "options": '["男性", "女性"]', "is_required": True, "carry_over": False},
    {"variable_name": "height", "label": "身長", "question_type": "number", "is_required": True, "carry_over": True},
    {"variable_name": "weight", "label": "体重", "question_type": "number", "is_required": True, "carry_over": True},
    {"variable_name": "likes", "label": "好きな食べ物", "question_type": "array", "array_max": 10, "is_required": True, "carry_over": True},
    {"variable_name": "dislikes", "label": "嫌いな食べ物", "question_type": "array", "array_max": 10, "is_required": True, "carry_over": True},
    {"variable_name": "position", "label": "ポジション　", "question_type": "select", "options": '["FW", "MF", "DF", "GK"]', "is_required": True, "carry_over": False},
    {"variable_name": "practiceday", "label": "練習曜日（試合がある曜日も含む）", "question_type": "checkbox", "options": '["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]', "is_required": True, "carry_over": False},
]

# 曜日→数字変換
DAY_MAP = {
    "月曜日": 0, "火曜日": 1, "水曜日": 2, "木曜日": 3,
    "金曜日": 4, "土曜日": 5, "日曜日": 6, "毎日": None
}

def parse_days(day_str):
    """曜日文字列をリストに変換"""
    if day_str == "毎日":
        return [0, 1, 2, 3, 4, 5, 6]
    days = []
    for d in day_str.replace("・", "、").split("、"):
        d = d.strip()
        if d in DAY_MAP:
            days.append(DAY_MAP[d])
    return days

def parse_time(time_str):
    """時刻文字列をパース"""
    try:
        parts = str(time_str).split(":")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except:
        return 0, 0

# プランデータ（プラン2〜13）
PLANS = [
    {
        "name": "BUILD（週2回）成長加速プラン・バランス系",
        "days": "月曜日・木曜日",
        "time": "01:00",
        "description": "毎週月曜日・木曜日にお届けします。・成長の材料と刺激を安定供給。平均的な家庭のスタートに最適。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長・骨成長・筋肉・体格」を
偏りなく最大化する専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週2回】で全体成長を安定的に底上げする
「二段階バランス型・成長設計」を作成せよ。

各日について
①家庭で作る本格レシピ
②コンビニで代替できる簡易版
の両方を必ず出力すること。

さらに
・通常版
・セノビック パフォーマンスアップ併用版
の2種類を出力せよ。"""
    },
    {
        "name": "ACCELERATE（週5回）成長循環プラン・バランス系",
        "days": "月曜日・火曜日・水曜日・木曜日・金曜日",
        "time": "02:00",
        "description": "毎週月曜日・火曜日・水曜日・木曜日・金曜日にお届けします。・成長→同化→回復→再刺激の循環を作る本格強化モデル。体格差が気になり始めた選手に最もおすすめ。★人気No.1",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長・骨成長・筋肉・体格」を
偏りなく最大化する専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週5回】で安定的に全体成長を促進する
「五段階バランス循環・成長設計」を作成せよ。"""
    },
    {
        "name": "MAXIMUM（週7回）完全成長プラン・バランス系",
        "days": "毎日",
        "time": "03:00",
        "description": "毎日お届けします。・毎日の栄養を管理し、成長を止めない完全設計。練習量が多い選手向け。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長・骨成長・筋肉・体格」を
偏りなく最大化する専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週7回（毎日）】で安定的に全体成長を促進する
「七段階バランス循環・成長設計」を作成せよ。"""
    },
    {
        "name": "FOUNDATION（週1回）基礎強化プラン・身長特化系",
        "days": "月曜日",
        "time": "04:00",
        "description": "毎週月曜日にお届けします。・最低限の成長刺激を入れる基本管理。まず試したい家庭向け。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長最大化」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週1回】で身長を最大限伸ばすための
「身長特化・成長ブースト設計」を1食分作成せよ。"""
    },
    {
        "name": "BUILD（週2回）成長加速プラン・身長特化系",
        "days": "月曜日・木曜日",
        "time": "05:00",
        "description": "毎週月曜日・木曜日にお届けします。・成長の材料と刺激を安定供給。平均的な家庭のスタートに最適。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長最大化」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週2回】で身長を最大限伸ばすための
「二段階・身長特化循環設計」を作成せよ。"""
    },
    {
        "name": "ACCELERATE（週5回）成長循環プラン・身長特化系",
        "days": "月曜日・火曜日・水曜日・木曜日・金曜日",
        "time": "06:00",
        "description": "毎週月曜日・火曜日・水曜日・木曜日・金曜日にお届けします。・成長→同化→回復→再刺激の循環を作る本格強化モデル。体格差が気になり始めた選手に最もおすすめ。★人気No.1",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長最大化」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週5回】で身長を最大限伸ばすための
「五段階・身長特化循環設計」を作成せよ。"""
    },
    {
        "name": "MAXIMUM（週7回）完全成長プラン・身長特化系",
        "days": "毎日",
        "time": "07:00",
        "description": "毎日お届けします。・毎日の栄養を管理し、成長を止めない完全設計。練習量が多い選手向け。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「身長最大化」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週7回（毎日）】で身長を最大限伸ばすための
「七段階・身長特化循環設計」を作成せよ。"""
    },
    {
        "name": "FOUNDATION（週1回）基礎強化プラン・体重特化系",
        "days": "月曜日",
        "time": "08:00",
        "description": "毎週月曜日にお届けします。・最低限の成長刺激を入れる基本管理。まず試したい家庭向け。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「質の高い体重増加（筋肉・体水分・骨量）」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週1回】で脂肪を増やさず体重を増やすための
「体重特化・成長ブースト設計」を1食分作成せよ。"""
    },
    {
        "name": "BUILD（週2回）成長加速プラン・体重特化系",
        "days": "月曜日・木曜日",
        "time": "09:00",
        "description": "毎週月曜日・木曜日にお届けします。・成長の材料と刺激を安定供給。平均的な家庭のスタートに最適。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「質の高い体重増加（筋肉・体水分・骨量）」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週2回】で脂肪を増やさず体重を増やすための
「二段階・体重特化循環設計」を作成せよ。"""
    },
    {
        "name": "ACCELERATE（週5回）成長循環プラン・体重特化系",
        "days": "月曜日・火曜日・水曜日・木曜日・金曜日",
        "time": "10:00",
        "description": "毎週月曜日・火曜日・水曜日・木曜日・金曜日にお届けします。・成長→同化→回復→再刺激の循環を作る本格強化モデル。体格差が気になり始めた選手に最もおすすめ。★人気No.1",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「質の高い体重増加（筋肉・体水分・骨量）」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週5回】で脂肪を増やさず体重を増やすための
「五段階・体重特化循環設計」を作成せよ。"""
    },
    {
        "name": "MAXIMUM（週7回）完全成長プラン・体重特化系",
        "days": "毎日",
        "time": "11:00",
        "description": "毎日お届けします。・毎日の栄養を管理し、成長を止めない完全設計。練習量が多い選手向け。",
        "base_prompt": """あなたは
9〜18歳のサッカー選手の「質の高い体重増加（筋肉・体水分・骨量）」に特化した
専門スポーツ栄養管理士である。

以下の8項目を入力として受け取り、
【週7回（毎日）】で脂肪を増やさず体重を増やすための
「七段階・体重特化循環設計」を作成せよ。"""
    },
    {
        "name": "ELITE GROWTH SYSTEM（週7回プレミアム）成長最適化アルゴリズムプラン",
        "days": "毎日",
        "time": "12:00",
        "description": "毎日お届けします。・現在の成長位置まで自動判定し、毎日の設計を完全最適化する最上位モデル。本気で体格を管理したい家庭向け。",
        "base_prompt": """あなたは
7〜18歳のサッカー選手の
「身長・骨成長・筋肉・体格」を科学的に最適化する
プレミアム成長設計アナリストである。

この設計は【週7固定】の本気層専用モデルである。"""
    },
]

def main():
    db = SessionLocal()
    stripe_service._init_stripe()
    
    try:
        for i, plan_data in enumerate(PLANS, start=2):
            print(f"[{i}/13] {plan_data['name']} を作成中...")
            
            # 曜日と時刻をパース
            days = parse_days(plan_data["days"])
            hour, minute = parse_time(plan_data["time"])
            
            # 配信スケジュール設定
            schedule_times = [f"{hour:02d}:{minute:02d}" for _ in days]
            
            # Stripeで商品を作成（価格は仮で1000円）
            stripe = stripe_service.stripe
            stripe_product = stripe.Product.create(
                name=plan_data["name"],
                description=plan_data["description"]
            )
            stripe_price = stripe.Price.create(
                product=stripe_product["id"],
                unit_amount=1000,  # 仮の価格
                currency="jpy",
                recurring={"interval": "month"}
            )
            
            # プランを作成
            import json
            plan = Plan(
                name=plan_data["name"],
                description=plan_data["description"],
                price=1000,  # 仮の価格
                stripe_product_id=stripe_product["id"],
                stripe_price_id=stripe_price["id"],
                system_prompt=plan_data["base_prompt"],
                prompt=INDIVIDUAL_INSTRUCTION,
                is_active=True,
                trial_enabled=False,
                schedule_type="weekday" if days != [0,1,2,3,4,5,6] else "daily",
                schedule_weekdays=json.dumps(days),
                send_time=f"{hour:02d}:{minute:02d}:00",
                model="gpt-4o",
                batch_send_enabled=False,
            )
            db.add(plan)
            db.flush()  # IDを取得
            
            # 質問項目を追加
            for order, q in enumerate(QUESTIONS):
                question = PlanQuestion(
                    plan_id=plan.id,
                    var_name=q["variable_name"],
                    label=q["label"],
                    question_type=q["question_type"],
                    options=q.get("options", "null"),
                    array_max=q.get("array_max"),
                    is_required=q["is_required"],
                    sort_order=order,
                    track_changes=q.get("carry_over", False),
                )
                db.add(question)
            
            print(f"  ✅ 作成完了: plan_id={plan.id}, stripe_product={stripe_product['id']}")
        
        db.commit()
        print("\n✅ 全12プランの追加が完了しました！")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ エラー: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
