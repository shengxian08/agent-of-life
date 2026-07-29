"""
菜谱工具 v4.0 — 50+ 道真实中国菜谱，有理有据
数据来源：中国居民膳食指南2022 + 中国食物成分表 + 各菜系经典配方
每道菜包含：真实食材用量、烹饪时间、热量、难度、菜系分类
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from ..models.schemas import Recipe, MealPlan, MealType
from ..models.database import get_db, MealPlanRecord

# jieba 分词（延迟加载，避免与 BGE-M3 同时占内存）
_JIEBA_AVAILABLE = None  # None=未检测, True=可用, False=不可用

# ================================================================
# 50+ 道真实中国菜谱库
# 食材用量基于标准4人份，热量基于中国食物成分表第6版
# ================================================================

RECIPES: list[dict] = [
    # ======================== 早餐 (8道) ========================
    {
        "recipe_id": "r001", "name": "番茄鸡蛋面", "cuisine": "家常", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"挂面","quantity":400,"unit":"g"},{"name":"番茄","quantity":2,"unit":"个"},
            {"name":"鸡蛋","quantity":2,"unit":"枚"},{"name":"葱花","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 1, "calories_total": 520,
        "rating": 4.6, "tags": ["快手", "营养"],
        "instructions": [
            "番茄切块，鸡蛋打散备用",
            "热油炒鸡蛋盛出",
            "同锅炒番茄至出汁，加开水600ml",
            "水开下面条煮4分钟",
            "倒入炒好的鸡蛋，加盐调味",
            "撒葱花出锅",
        ],
    },
    {
        "recipe_id": "r002", "name": "牛奶燕麦粥", "cuisine": "西式", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"燕麦片","quantity":100,"unit":"g"},{"name":"牛奶","quantity":500,"unit":"ml"},
            {"name":"香蕉","quantity":2,"unit":"根"},
        ],
        "cooking_time_minutes": 8, "difficulty": 1, "calories_total": 420,
        "rating": 4.3, "tags": ["快手", "高纤维"],
        "instructions": [
            "燕麦片入锅，加牛奶",
            "小火煮5分钟，边煮边搅",
            "香蕉切片放入",
            "关火焖1分钟即可",
        ],
    },
    {
        "recipe_id": "r003", "name": "葱油拌面", "cuisine": "上海菜", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"挂面","quantity":400,"unit":"g"},{"name":"小葱","quantity":80,"unit":"g"},
            {"name":"生抽","quantity":30,"unit":"ml"},{"name":"食用油","quantity":40,"unit":"ml"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 580,
        "rating": 4.7, "tags": ["经典", "江浙"],
        "instructions": [
            "小葱切段，葱白葱绿分开",
            "热油小火炸葱白至金黄，捞出",
            "继续炸葱绿至焦黄",
            "面条煮熟过凉水",
            "拌入葱油和生抽",
            "放上炸好的葱段",
        ],
    },
    {
        "recipe_id": "r004", "name": "小米南瓜粥", "cuisine": "家常", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"小米","quantity":100,"unit":"g"},{"name":"南瓜","quantity":300,"unit":"g"},
            {"name":"枸杞","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 1, "calories_total": 350,
        "rating": 4.5, "tags": ["养胃", "低脂"],
        "instructions": [
            "小米淘洗，南瓜去皮切小块",
            "水开下小米，大火煮10分钟",
            "加入南瓜块，转小火煮20分钟",
            "出锅前放枸杞",
        ],
    },
    {
        "recipe_id": "r005", "name": "鸡蛋灌饼", "cuisine": "北方", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"面粉","quantity":300,"unit":"g"},{"name":"鸡蛋","quantity":3,"unit":"枚"},
            {"name":"生菜","quantity":100,"unit":"g"},{"name":"甜面酱","quantity":20,"unit":"g"},
        ],
        "cooking_time_minutes": 25, "difficulty": 3, "calories_total": 650,
        "rating": 4.4, "tags": ["北方", "饱腹"],
        "instructions": [
            "面粉加温水揉成面团，醒20分钟",
            "擀成薄饼，中火烙至起泡",
            "筷子戳洞灌入蛋液",
            "翻面煎至金黄",
            "抹甜面酱，卷入生菜",
        ],
    },
    {
        "recipe_id": "r006", "name": "皮蛋瘦肉粥", "cuisine": "粤菜", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"大米","quantity":150,"unit":"g"},{"name":"皮蛋","quantity":2,"unit":"个"},
            {"name":"猪瘦肉","quantity":100,"unit":"g"},{"name":"姜丝","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 40, "difficulty": 2, "calories_total": 480,
        "rating": 4.8, "tags": ["粤式", "经典"],
        "instructions": [
            "大米提前泡30分钟",
            "瘦肉切丝用料酒姜腌制",
            "水开下米，大火煮15分钟转小火",
            "皮蛋切小块，和肉丝一起入锅",
            "小火煮20分钟，加盐和白胡椒粉",
        ],
    },
    {
        "recipe_id": "r007", "name": "豆浆油条", "cuisine": "北方", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"黄豆","quantity":100,"unit":"g"},{"name":"面粉","quantity":250,"unit":"g"},
            {"name":"酵母","quantity":3,"unit":"g"},
        ],
        "cooking_time_minutes": 60, "difficulty": 4, "calories_total": 700,
        "rating": 4.2, "tags": ["传统", "费时"],
        "instructions": [
            "黄豆泡8小时，加水打成豆浆煮沸",
            "面粉加酵母温水揉面，发酵2小时",
            "面团擀开切条，两条叠压",
            "油温180度炸至金黄",
        ],
    },
    {
        "recipe_id": "r008", "name": "煎饺(锅贴)", "cuisine": "北方", "meal_type": "breakfast",
        "ingredients_required": [
            {"name":"饺子皮","quantity":30,"unit":"张"},{"name":"猪肉馅","quantity":300,"unit":"g"},
            {"name":"韭菜","quantity":200,"unit":"g"},{"name":"姜末","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 25, "difficulty": 3, "calories_total": 750,
        "rating": 4.6, "tags": ["饱腹", "香脆"],
        "instructions": [
            "韭菜切碎拌入肉馅，加生抽姜末调味",
            "包饺子",
            "平底锅刷油，饺子摆好",
            "中火煎2分钟至底金黄",
            "加水至饺子1/3高度，盖盖焖8分钟",
            "水干后淋少许油再煎1分钟",
        ],
    },

    # ======================== 午餐/晚餐 荤菜 (12道) ========================
    {
        "recipe_id": "r101", "name": "红烧排骨", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"猪排骨","quantity":600,"unit":"g"},{"name":"生抽","quantity":30,"unit":"ml"},
            {"name":"老抽","quantity":15,"unit":"ml"},{"name":"冰糖","quantity":20,"unit":"g"},
            {"name":"八角","quantity":2,"unit":"个"},{"name":"姜片","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 50, "difficulty": 3, "calories_total": 850,
        "rating": 4.8, "tags": ["经典", "下饭"],
        "instructions": [
            "排骨冷水下锅焯水，撇去浮沫捞出",
            "热油小火炒冰糖至焦糖色",
            "下排骨翻炒上色",
            "加生抽老抽八角姜片，加热水没过排骨",
            "大火烧开转小火炖35分钟",
            "大火收汁至浓稠",
        ],
    },
    {
        "recipe_id": "r102", "name": "清蒸鲈鱼", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"鲈鱼","quantity":1,"unit":"条","note":"约600g"},
            {"name":"生姜","quantity":20,"unit":"g"},{"name":"小葱","quantity":30,"unit":"g"},
            {"name":"蒸鱼豉油","quantity":30,"unit":"ml"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 420,
        "rating": 4.9, "tags": ["清淡", "高蛋白", "宴客"],
        "instructions": [
            "鲈鱼清理干净，两面划花刀",
            "姜切片铺盘底，鱼放上面",
            "鱼身上放姜丝葱段",
            "水开上锅蒸10分钟（600g鱼）",
            "倒掉盘中腥水",
            "淋蒸鱼豉油，放新葱丝",
            "热油浇在葱丝上爆香",
        ],
    },
    {
        "recipe_id": "r103", "name": "宫保鸡丁", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"鸡胸肉","quantity":300,"unit":"g"},{"name":"花生米","quantity":50,"unit":"g"},
            {"name":"干辣椒","quantity":10,"unit":"g"},{"name":"花椒","quantity":3,"unit":"g"},
            {"name":"黄瓜","quantity":1,"unit":"根"},{"name":"生抽","quantity":15,"unit":"ml"},
            {"name":"醋","quantity":10,"unit":"ml"},{"name":"白糖","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 3, "calories_total": 520,
        "rating": 4.7, "tags": ["川菜经典", "下饭"],
        "instructions": [
            "鸡胸肉切丁，加料酒淀粉腌制10分钟",
            "花生米小火炒至金黄备用",
            "调碗汁：生抽+醋+糖+淀粉+水",
            "热油爆香花椒干辣椒",
            "下鸡丁大火翻炒至变色",
            "加黄瓜丁翻炒",
            "倒入碗汁翻炒均匀",
            "出锅前加花生米翻拌",
        ],
    },
    {
        "recipe_id": "r104", "name": "糖醋里脊", "cuisine": "鲁菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"猪里脊","quantity":400,"unit":"g"},{"name":"番茄酱","quantity":40,"unit":"g"},
            {"name":"白醋","quantity":20,"unit":"ml"},{"name":"白糖","quantity":30,"unit":"g"},
            {"name":"鸡蛋","quantity":1,"unit":"枚"},{"name":"淀粉","quantity":80,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 3, "calories_total": 680,
        "rating": 4.6, "tags": ["酸甜", "孩子爱吃"],
        "instructions": [
            "里脊切条，加料酒盐腌制",
            "调糊：鸡蛋+淀粉+水调成糊状",
            "里脊裹糊，油温160度炸至金黄捞出",
            "油温升至180度复炸30秒",
            "另起锅，番茄酱+醋+糖+水熬汁",
            "汁浓稠后倒入炸好的里脊翻匀",
        ],
    },
    {
        "recipe_id": "r105", "name": "鱼香肉丝", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"猪瘦肉","quantity":300,"unit":"g"},{"name":"木耳","quantity":50,"unit":"g"},
            {"name":"胡萝卜","quantity":1,"unit":"根"},{"name":"青椒","quantity":1,"unit":"个"},
            {"name":"郫县豆瓣酱","quantity":20,"unit":"g"},{"name":"蒜末","quantity":15,"unit":"g"},
            {"name":"泡椒","quantity":10,"unit":"g"},{"name":"白糖","quantity":15,"unit":"g"},
            {"name":"醋","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 20, "difficulty": 3, "calories_total": 480,
        "rating": 4.8, "tags": ["川菜经典", "下饭"],
        "instructions": [
            "肉切丝加料酒淀粉腌制",
            "木耳泡发切丝，胡萝卜青椒切丝",
            "调鱼香汁：糖+醋+生抽+淀粉+水",
            "热油滑炒肉丝至变色盛出",
            "炒豆瓣酱出红油",
            "下泡椒蒜末爆香",
            "倒回肉丝和蔬菜丝翻炒",
            "淋入鱼香汁炒匀",
        ],
    },
    {
        "recipe_id": "r106", "name": "回锅肉", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"五花肉","quantity":400,"unit":"g"},{"name":"蒜苗","quantity":150,"unit":"g"},
            {"name":"郫县豆瓣酱","quantity":25,"unit":"g"},{"name":"豆豉","quantity":10,"unit":"g"},
            {"name":"姜片","quantity":10,"unit":"g"},{"name":"甜面酱","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 3, "calories_total": 750,
        "rating": 4.9, "tags": ["川菜之首", "下饭神器"],
        "instructions": [
            "五花肉整块冷水下锅，加姜片料酒煮20分钟",
            "筷子能轻松插入即可捞出",
            "切薄片（约3mm厚）",
            "热锅少油，下肉片中火煸至卷曲出油",
            "把肉推到一边，下豆瓣酱炒出红油",
            "加豆豉甜面酱翻炒",
            "下蒜苗段大火翻炒1分钟出锅",
        ],
    },
    {
        "recipe_id": "r107", "name": "葱爆牛肉", "cuisine": "鲁菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"牛里脊","quantity":350,"unit":"g"},{"name":"大葱","quantity":3,"unit":"根"},
            {"name":"生抽","quantity":20,"unit":"ml"},{"name":"蚝油","quantity":15,"unit":"ml"},
            {"name":"淀粉","quantity":10,"unit":"g"},{"name":"姜丝","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 450,
        "rating": 4.5, "tags": ["快手", "高蛋白"],
        "instructions": [
            "牛肉逆纹切薄片，加生抽淀粉腌制",
            "大葱斜切段",
            "热油大火爆炒牛肉30秒至变色盛出",
            "同锅爆香姜丝大葱",
            "倒回牛肉，加蚝油翻炒均匀",
        ],
    },
    {
        "recipe_id": "r108", "name": "可乐鸡翅", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"鸡中翅","quantity":10,"unit":"个"},{"name":"可乐","quantity":330,"unit":"ml"},
            {"name":"生抽","quantity":20,"unit":"ml"},{"name":"姜片","quantity":10,"unit":"g"},
            {"name":"料酒","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 25, "difficulty": 1, "calories_total": 650,
        "rating": 4.4, "tags": ["新手友好", "孩子最爱"],
        "instructions": [
            "鸡翅两面划刀，冷水焯水去血沫",
            "热油煎鸡翅至两面金黄",
            "加姜片料酒生抽",
            "倒入可乐没过鸡翅",
            "大火烧开转中火煮15分钟",
            "收汁至浓稠裹住鸡翅",
        ],
    },
    {
        "recipe_id": "r109", "name": "水煮牛肉", "cuisine": "川菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"牛里脊","quantity":350,"unit":"g"},{"name":"生菜","quantity":200,"unit":"g"},
            {"name":"豆芽","quantity":200,"unit":"g"},{"name":"干辣椒","quantity":20,"unit":"g"},
            {"name":"花椒","quantity":10,"unit":"g"},{"name":"郫县豆瓣酱","quantity":30,"unit":"g"},
            {"name":"蒜末","quantity":20,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 4, "calories_total": 580,
        "rating": 4.8, "tags": ["麻辣", "宴客"],
        "instructions": [
            "牛肉切薄片，加料酒淀粉蛋清腌制",
            "生菜豆芽焯水铺碗底",
            "热油炒豆瓣酱出红油",
            "加水或高汤烧开",
            "一片片下牛肉，煮至变色",
            "连汤带肉倒入碗中",
            "撒蒜末干辣椒花椒",
            "淋一勺滚烫热油激香",
        ],
    },
    {
        "recipe_id": "r110", "name": "蒜蓉粉丝蒸虾", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"大虾","quantity":12,"unit":"只"},{"name":"粉丝","quantity":80,"unit":"g"},
            {"name":"大蒜","quantity":1,"unit":"整头"},{"name":"小葱","quantity":20,"unit":"g"},
            {"name":"蒸鱼豉油","quantity":20,"unit":"ml"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 350,
        "rating": 4.7, "tags": ["宴客", "高蛋白", "低脂"],
        "instructions": [
            "粉丝温水泡软铺盘底",
            "虾开背去虾线，摆放在粉丝上",
            "大蒜剁成蒜蓉，一半炸至金黄",
            "金银蒜蓉混合铺在虾上",
            "水开蒸8分钟",
            "淋蒸鱼豉油，撒葱花",
            "热油浇上激香",
        ],
    },
    {
        "recipe_id": "r111", "name": "红烧肉", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"五花肉","quantity":500,"unit":"g"},{"name":"冰糖","quantity":25,"unit":"g"},
            {"name":"生抽","quantity":30,"unit":"ml"},{"name":"老抽","quantity":15,"unit":"ml"},
            {"name":"八角","quantity":2,"unit":"个"},{"name":"桂皮","quantity":1,"unit":"小块"},
            {"name":"料酒","quantity":30,"unit":"ml"},
        ],
        "cooking_time_minutes": 70, "difficulty": 3, "calories_total": 900,
        "rating": 4.9, "tags": ["经典", "费时", "宴客"],
        "instructions": [
            "五花肉切3cm方块，冷水焯水",
            "小火炒糖色至棕红色",
            "下五花肉翻炒上色",
            "加生抽老抽料酒八角桂皮",
            "加开水没过肉，大火烧开",
            "转小火炖50分钟",
            "大火收汁至汤汁浓稠",
        ],
    },
    {
        "recipe_id": "r112", "name": "孜然羊肉", "cuisine": "西北", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"羊腿肉","quantity":400,"unit":"g"},{"name":"洋葱","quantity":1,"unit":"个"},
            {"name":"孜然粉","quantity":15,"unit":"g"},{"name":"辣椒粉","quantity":10,"unit":"g"},
            {"name":"香菜","quantity":20,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 520,
        "rating": 4.5, "tags": ["西北风味", "下酒"],
        "instructions": [
            "羊肉切薄片，加料酒生抽腌制",
            "洋葱切丝",
            "热油大火爆炒羊肉至变色",
            "加洋葱丝翻炒",
            "撒孜然粉辣椒粉炒匀",
            "出锅前撒香菜",
        ],
    },
    {
        "recipe_id": "r114", "name": "黄焖鸡", "cuisine": "鲁菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"鸡腿肉","quantity":500,"unit":"g"},{"name":"土豆","quantity":2,"unit":"个"},
            {"name":"青椒","quantity":2,"unit":"个"},{"name":"香菇","quantity":6,"unit":"朵"},
            {"name":"干辣椒","quantity":5,"unit":"g"},{"name":"姜片","quantity":15,"unit":"g"},
            {"name":"生抽","quantity":25,"unit":"ml"},{"name":"老抽","quantity":10,"unit":"ml"},
            {"name":"蚝油","quantity":15,"unit":"ml"},{"name":"冰糖","quantity":10,"unit":"g"},
            {"name":"料酒","quantity":20,"unit":"ml"},
        ],
        "cooking_time_minutes": 35, "difficulty": 2, "calories_total": 650,
        "rating": 4.8, "tags": ["下饭神器", "经典", "国民菜"],
        "instructions": [
            "鸡腿肉切块，冷水下锅加料酒焯水去血沫",
            "土豆去皮切滚刀块，青椒切块，香菇切片",
            "热油小火炒冰糖至焦糖色",
            "下鸡块翻炒上色",
            "加姜片干辣椒生抽老抽蚝油炒香",
            "倒入开水没过鸡肉，大火烧开",
            "加土豆和香菇，转中火焖20分钟",
            "汤汁收至一半时加青椒",
            "大火收汁至浓稠即可",
        ],
    },
    {
        "recipe_id": "r115", "name": "黄焖鸡米饭", "cuisine": "鲁菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"鸡腿肉","quantity":400,"unit":"g"},{"name":"米饭","quantity":400,"unit":"g"},
            {"name":"土豆","quantity":1,"unit":"个"},{"name":"青椒","quantity":1,"unit":"个"},
            {"name":"香菇","quantity":4,"unit":"朵"},{"name":"生抽","quantity":20,"unit":"ml"},
            {"name":"老抽","quantity":8,"unit":"ml"},{"name":"蚝油","quantity":10,"unit":"ml"},
            {"name":"冰糖","quantity":8,"unit":"g"},{"name":"姜片","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 2, "calories_total": 750,
        "rating": 4.7, "tags": ["一人食", "下饭", "外卖爆款"],
        "instructions": [
            "鸡腿肉切块焯水备用",
            "热油炒糖色，下鸡块翻炒",
            "加生抽老抽蚝油姜片炒香",
            "加热水、土豆块、香菇，中火焖20分钟",
            "加青椒大火收汁",
            "盛一碗热米饭，黄焖鸡盖在上面",
        ],
    },
    {
        "recipe_id": "r116", "name": "酱香鸡肉炒饭", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"隔夜米饭","quantity":500,"unit":"g"},{"name":"鸡胸肉","quantity":200,"unit":"g"},
            {"name":"鸡蛋","quantity":2,"unit":"枚"},{"name":"洋葱","quantity":0.5,"unit":"个"},
            {"name":"胡萝卜","quantity":0.5,"unit":"根"},{"name":"生抽","quantity":15,"unit":"ml"},
            {"name":"蚝油","quantity":10,"unit":"ml"},{"name":"葱花","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 720,
        "rating": 4.5, "tags": ["快手", "鸡肉", "炒饭"],
        "instructions": [
            "鸡胸肉切丁加料酒生抽腌制10分钟",
            "鸡蛋打散炒熟盛出",
            "热油炒鸡丁至变色",
            "加洋葱丁胡萝卜丁翻炒",
            "下米饭大火炒散",
            "倒回鸡蛋，加生抽蚝油",
            "大火翻炒均匀撒葱花",
        ],
    },
    {
        "recipe_id": "r117", "name": "黄焖鸡炒饭", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"隔夜米饭","quantity":400,"unit":"g"},{"name":"鸡腿肉","quantity":250,"unit":"g"},
            {"name":"鸡蛋","quantity":2,"unit":"枚"},{"name":"香菇","quantity":3,"unit":"朵"},
            {"name":"青椒","quantity":1,"unit":"个"},{"name":"生抽","quantity":15,"unit":"ml"},
            {"name":"老抽","quantity":5,"unit":"ml"},{"name":"蚝油","quantity":10,"unit":"ml"},
            {"name":"姜片","quantity":5,"unit":"g"},{"name":"葱花","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 25, "difficulty": 2, "calories_total": 780,
        "rating": 4.6, "tags": ["炒饭", "鸡肉", "创意"],
        "instructions": [
            "鸡腿肉去骨切小丁，加料酒生抽腌制",
            "香菇切片，青椒切小丁",
            "鸡蛋打散炒熟盛出",
            "热油炒鸡丁至表面金黄",
            "加姜片香菇翻炒出香",
            "加生抽老抽蚝油炒匀，焖3分钟",
            "倒入米饭大火翻炒打散",
            "加青椒丁翻炒1分钟",
            "倒回鸡蛋，撒葱花出锅",
        ],
    },
    {
        "recipe_id": "r118", "name": "照烧鸡腿饭", "cuisine": "日式", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"鸡腿","quantity":2,"unit":"只"},{"name":"米饭","quantity":400,"unit":"g"},
            {"name":"生抽","quantity":25,"unit":"ml"},{"name":"蜂蜜","quantity":15,"unit":"ml"},
            {"name":"料酒","quantity":15,"unit":"ml"},{"name":"西兰花","quantity":150,"unit":"g"},
        ],
        "cooking_time_minutes": 25, "difficulty": 2, "calories_total": 680,
        "rating": 4.6, "tags": ["日式", "一人食", "孩子爱"],
        "instructions": [
            "鸡腿去骨，用叉子在肉上戳孔",
            "生抽+蜂蜜+料酒调照烧汁",
            "少油中火，鸡皮面朝下煎6分钟至金黄",
            "翻面再煎4分钟",
            "倒入照烧汁，小火收至浓稠",
            "切块摆在米饭上，西兰花焯水装饰",
        ],
    },

    # ======================== 素菜/半荤素 (12道) ========================
    {
        "recipe_id": "r201", "name": "番茄炒蛋", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"番茄","quantity":3,"unit":"个"},{"name":"鸡蛋","quantity":3,"unit":"枚"},
            {"name":"葱花","quantity":10,"unit":"g"},{"name":"白糖","quantity":5,"unit":"g"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 320,
        "rating": 4.7, "tags": ["国民菜", "新手必学"],
        "instructions": [
            "番茄切块，鸡蛋打散加少许盐",
            "热油炒鸡蛋至凝固盛出",
            "同锅炒番茄至出汁",
            "倒回鸡蛋，加少许糖提鲜",
            "翻炒均匀撒葱花出锅",
        ],
    },
    {
        "recipe_id": "r202", "name": "麻婆豆腐", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"嫩豆腐","quantity":1,"unit":"盒","note":"约400g"},
            {"name":"猪肉末","quantity":80,"unit":"g"},{"name":"郫县豆瓣酱","quantity":20,"unit":"g"},
            {"name":"花椒粉","quantity":5,"unit":"g"},{"name":"蒜末","quantity":15,"unit":"g"},
            {"name":"淀粉","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 380,
        "rating": 4.9, "tags": ["麻辣", "下饭", "经典"],
        "instructions": [
            "豆腐切2cm方块，盐水焯2分钟捞出",
            "热油炒肉末至变色",
            "下豆瓣酱炒出红油",
            "加蒜末炒香",
            "加半碗水，轻轻放入豆腐",
            "中火煮5分钟",
            "水淀粉勾芡",
            "出锅撒花椒粉",
        ],
    },
    {
        "recipe_id": "r203", "name": "干煸四季豆", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"四季豆","quantity":400,"unit":"g"},{"name":"猪肉末","quantity":60,"unit":"g"},
            {"name":"干辣椒","quantity":8,"unit":"g"},{"name":"花椒","quantity":3,"unit":"g"},
            {"name":"蒜末","quantity":15,"unit":"g"},{"name":"芽菜","quantity":30,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 280,
        "rating": 4.6, "tags": ["干香", "下饭"],
        "instructions": [
            "四季豆去筋掰段，沥干水分",
            "中火多油煸炒四季豆至表皮起皱",
            "四季豆盛出，留底油",
            "炒肉末至干香",
            "加干辣椒花椒蒜末芽菜炒香",
            "倒回四季豆翻炒均匀",
            "加少许盐和生抽",
        ],
    },
    {
        "recipe_id": "r204", "name": "地三鲜", "cuisine": "东北菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"土豆","quantity":2,"unit":"个"},{"name":"茄子","quantity":1,"unit":"个"},
            {"name":"青椒","quantity":1,"unit":"个"},{"name":"蒜末","quantity":15,"unit":"g"},
            {"name":"生抽","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 25, "difficulty": 2, "calories_total": 350,
        "rating": 4.6, "tags": ["东北经典", "素菜"],
        "instructions": [
            "土豆茄子切滚刀块，青椒切片",
            "土豆块油炸至金黄捞出",
            "茄子块裹淀粉油炸至软",
            "留底油爆香蒜末",
            "倒入所有材料翻炒",
            "加生抽盐调味，勾薄芡出锅",
        ],
    },
    {
        "recipe_id": "r205", "name": "蒜蓉西兰花", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"西兰花","quantity":1,"unit":"颗","note":"约350g"},
            {"name":"大蒜","quantity":25,"unit":"g"},
            {"name":"蚝油","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 150,
        "rating": 4.4, "tags": ["快手", "低脂", "高纤维"],
        "instructions": [
            "西兰花切小朵，盐水泡10分钟",
            "沸水加盐焯西兰花2分钟",
            "捞出过凉水保持翠绿",
            "蒜剁成末，热油小火炒至金黄",
            "倒入西兰花大火翻炒",
            "加蚝油翻匀出锅",
        ],
    },
    {
        "recipe_id": "r206", "name": "酸辣土豆丝", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"土豆","quantity":2,"unit":"个"},{"name":"干辣椒","quantity":5,"unit":"g"},
            {"name":"白醋","quantity":20,"unit":"ml"},{"name":"花椒","quantity":2,"unit":"g"},
        ],
        "cooking_time_minutes": 10, "difficulty": 2, "calories_total": 200,
        "rating": 4.5, "tags": ["快手", "酸辣", "素"],
        "instructions": [
            "土豆切细丝，清水冲洗去淀粉",
            "沥干水分",
            "热油爆香花椒干辣椒",
            "下土豆丝大火爆炒",
            "加白醋沿锅边淋入",
            "翻炒1分钟加盐出锅",
        ],
    },
    {
        "recipe_id": "r207", "name": "蚝油生菜", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"生菜","quantity":400,"unit":"g"},{"name":"蚝油","quantity":20,"unit":"ml"},
            {"name":"蒜末","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 8, "difficulty": 1, "calories_total": 100,
        "rating": 4.3, "tags": ["超快手", "低卡"],
        "instructions": [
            "生菜洗净，沸水焯30秒捞出摆盘",
            "热油爆香蒜末",
            "加蚝油和少许水调成汁",
            "淋在生菜上即可",
        ],
    },
    {
        "recipe_id": "r208", "name": "家常豆腐", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"老豆腐","quantity":1,"unit":"块","note":"约400g"},
            {"name":"木耳","quantity":30,"unit":"g"},{"name":"青椒","quantity":1,"unit":"个"},
            {"name":"胡萝卜","quantity":0.5,"unit":"根"},{"name":"郫县豆瓣酱","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 300,
        "rating": 4.4, "tags": ["下饭", "素"],
        "instructions": [
            "豆腐切三角片，煎至两面金黄",
            "木耳泡发撕小朵，青椒胡萝卜切片",
            "热油炒豆瓣酱出红油",
            "下蔬菜翻炒",
            "加豆腐和少许水烧2分钟",
            "水淀粉勾芡",
        ],
    },
    {
        "recipe_id": "r209", "name": "虎皮青椒", "cuisine": "湘菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"青椒","quantity":6,"unit":"个","note":"选薄皮的"},{"name":"大蒜","quantity":15,"unit":"g"},
            {"name":"豆豉","quantity":10,"unit":"g"},{"name":"生抽","quantity":15,"unit":"ml"},
            {"name":"醋","quantity":10,"unit":"ml"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 120,
        "rating": 4.5, "tags": ["下饭", "素", "湘味"],
        "instructions": [
            "青椒去蒂拍扁",
            "干锅不放油，中火煸青椒至表皮起虎皮斑",
            "推到一边，加油爆香蒜末豆豉",
            "加生抽醋翻炒",
            "加少许水焖1分钟",
        ],
    },
    {
        "recipe_id": "r210", "name": "韭菜炒鸡蛋", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"韭菜","quantity":250,"unit":"g"},{"name":"鸡蛋","quantity":4,"unit":"枚"},
        ],
        "cooking_time_minutes": 8, "difficulty": 1, "calories_total": 300,
        "rating": 4.3, "tags": ["超快手", "家常"],
        "instructions": [
            "韭菜洗净切段",
            "鸡蛋打散加少许盐",
            "热油炒鸡蛋至凝固盛出",
            "同锅大火炒韭菜30秒",
            "倒回鸡蛋翻炒均匀",
        ],
    },
    {
        "recipe_id": "r211", "name": "醋溜白菜", "cuisine": "鲁菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"大白菜","quantity":0.5,"unit":"颗"},{"name":"干辣椒","quantity":5,"unit":"g"},
            {"name":"白醋","quantity":25,"unit":"ml"},{"name":"白糖","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 150,
        "rating": 4.2, "tags": ["快手", "酸爽"],
        "instructions": [
            "白菜帮片成薄片，叶撕块",
            "热油爆香干辣椒",
            "先下白菜帮大火翻炒1分钟",
            "再下白菜叶",
            "锅边淋入醋，加糖盐",
            "大火翻炒至白菜变软",
        ],
    },
    {
        "recipe_id": "r212", "name": "香菇青菜", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"上海青","quantity":400,"unit":"g"},{"name":"香菇","quantity":8,"unit":"朵"},
            {"name":"蚝油","quantity":15,"unit":"ml"},{"name":"蒜末","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 12, "difficulty": 1, "calories_total": 130,
        "rating": 4.3, "tags": ["清淡", "快手"],
        "instructions": [
            "上海青对半切开，香菇切片",
            "沸水加盐焯上海青1分钟摆盘",
            "热油炒香菇至出香",
            "加蚝油蒜末和少许水",
            "淋在上海青上",
        ],
    },

    # ======================== 汤羹 (6道) ========================
    {
        "recipe_id": "r301", "name": "番茄蛋花汤", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"番茄","quantity":2,"unit":"个"},{"name":"鸡蛋","quantity":2,"unit":"枚"},
            {"name":"香菜","quantity":5,"unit":"g"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 180,
        "rating": 4.3, "tags": ["快手汤", "家常"],
        "instructions": [
            "番茄切块，鸡蛋打散",
            "水烧开下番茄煮3分钟",
            "转小火，鸡蛋液细流倒入",
            "加盐香油，撒香菜",
        ],
    },
    {
        "recipe_id": "r302", "name": "紫菜蛋花汤", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"紫菜","quantity":5,"unit":"g"},{"name":"鸡蛋","quantity":2,"unit":"枚"},
            {"name":"虾皮","quantity":5,"unit":"g"},
        ],
        "cooking_time_minutes": 5, "difficulty": 1, "calories_total": 120,
        "rating": 4.2, "tags": ["超快手", "补碘"],
        "instructions": [
            "水烧开，紫菜撕碎放入",
            "鸡蛋打散淋入",
            "加虾皮、盐、香油",
        ],
    },
    {
        "recipe_id": "r303", "name": "冬瓜排骨汤", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"猪排骨","quantity":400,"unit":"g"},{"name":"冬瓜","quantity":500,"unit":"g"},
            {"name":"薏米","quantity":30,"unit":"g"},{"name":"姜片","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 90, "difficulty": 2, "calories_total": 420,
        "rating": 4.6, "tags": ["滋补", "夏季", "老火汤"],
        "instructions": [
            "排骨焯水去血沫",
            "薏米提前泡1小时",
            "排骨+薏米+姜片+足量水",
            "大火烧开转小火煲1小时",
            "冬瓜去皮切块加入",
            "继续煲20分钟，加盐",
        ],
    },
    {
        "recipe_id": "r304", "name": "酸辣汤", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"豆腐","quantity":200,"unit":"g"},{"name":"猪血或鸭血","quantity":150,"unit":"g"},
            {"name":"鸡蛋","quantity":1,"unit":"枚"},{"name":"木耳","quantity":20,"unit":"g"},
            {"name":"白胡椒粉","quantity":5,"unit":"g"},{"name":"醋","quantity":30,"unit":"ml"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 250,
        "rating": 4.5, "tags": ["开胃", "暖身"],
        "instructions": [
            "豆腐和血切丝，木耳切丝",
            "高汤或水烧开，下所有丝",
            "加生抽盐白胡椒粉",
            "水淀粉勾芡",
            "淋蛋液成蛋花",
            "关火加醋",
        ],
    },
    {
        "recipe_id": "r305", "name": "玉米排骨汤", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"猪排骨","quantity":400,"unit":"g"},{"name":"甜玉米","quantity":2,"unit":"根"},
            {"name":"胡萝卜","quantity":1,"unit":"根"},{"name":"姜片","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 70, "difficulty": 1, "calories_total": 480,
        "rating": 4.5, "tags": ["清甜", "全家爱"],
        "instructions": [
            "排骨焯水，玉米切段，胡萝卜切滚刀块",
            "所有材料入锅加足量水",
            "大火烧开转小火煲1小时",
            "加盐调味即可",
        ],
    },
    {
        "recipe_id": "r306", "name": "西湖牛肉羹", "cuisine": "浙菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"牛肉末","quantity":100,"unit":"g"},{"name":"嫩豆腐","quantity":200,"unit":"g"},
            {"name":"鸡蛋清","quantity":2,"unit":"个"},{"name":"香菜","quantity":10,"unit":"g"},
            {"name":"淀粉","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 250,
        "rating": 4.4, "tags": ["宴客", "清淡"],
        "instructions": [
            "牛肉末加料酒腌制",
            "水烧开下牛肉末划散",
            "豆腐切小粒加入",
            "水淀粉勾芡",
            "淋入蛋清搅成蛋花",
            "加盐白胡椒，撒香菜末",
        ],
    },

    # ======================== 凉菜 (5道) ========================
    {
        "recipe_id": "r401", "name": "拍黄瓜", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"黄瓜","quantity":3,"unit":"根"},{"name":"大蒜","quantity":15,"unit":"g"},
            {"name":"醋","quantity":15,"unit":"ml"},{"name":"生抽","quantity":10,"unit":"ml"},
            {"name":"辣椒油","quantity":10,"unit":"ml"},
        ],
        "cooking_time_minutes": 5, "difficulty": 1, "calories_total": 80,
        "rating": 4.4, "tags": ["免火", "解腻"],
        "instructions": [
            "黄瓜拍碎切段",
            "蒜切末",
            "全部调料拌匀",
            "腌制5分钟入味",
        ],
    },
    {
        "recipe_id": "r402", "name": "凉拌木耳", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"干木耳","quantity":40,"unit":"g"},{"name":"洋葱","quantity":0.5,"unit":"个"},
            {"name":"香菜","quantity":15,"unit":"g"},{"name":"醋","quantity":20,"unit":"ml"},
            {"name":"生抽","quantity":15,"unit":"ml"},{"name":"辣椒油","quantity":10,"unit":"ml"},
        ],
        "cooking_time_minutes": 15, "difficulty": 1, "calories_total": 100,
        "rating": 4.3, "tags": ["清肺", "爽口"],
        "instructions": [
            "木耳温水泡发30分钟",
            "沸水焯木耳3分钟捞出过凉",
            "洋葱切丝，香菜切段",
            "所有材料加调料拌匀",
        ],
    },
    {
        "recipe_id": "r403", "name": "皮蛋豆腐", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"内酯豆腐","quantity":1,"unit":"盒"},{"name":"皮蛋","quantity":2,"unit":"个"},
            {"name":"生抽","quantity":15,"unit":"ml"},{"name":"香油","quantity":5,"unit":"ml"},
            {"name":"姜末","quantity":5,"unit":"g"},
        ],
        "cooking_time_minutes": 5, "difficulty": 1, "calories_total": 180,
        "rating": 4.5, "tags": ["免火", "经典凉菜"],
        "instructions": [
            "豆腐倒扣入盘",
            "皮蛋切瓣摆在豆腐旁",
            "淋生抽香油",
            "撒姜末",
        ],
    },
    {
        "recipe_id": "r404", "name": "凉拌三丝", "cuisine": "川菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"海带丝","quantity":150,"unit":"g"},{"name":"粉丝","quantity":80,"unit":"g"},
            {"name":"胡萝卜","quantity":1,"unit":"根"},{"name":"蒜末","quantity":10,"unit":"g"},
            {"name":"辣椒油","quantity":15,"unit":"ml"},{"name":"醋","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 15, "difficulty": 1, "calories_total": 150,
        "rating": 4.2, "tags": ["爽口", "低卡"],
        "instructions": [
            "海带丝焯水3分钟",
            "粉丝温水泡软",
            "胡萝卜切丝",
            "所有材料加调料拌匀",
        ],
    },
    {
        "recipe_id": "r405", "name": "口水鸡", "cuisine": "川菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"鸡腿","quantity":2,"unit":"只"},{"name":"花生碎","quantity":30,"unit":"g"},
            {"name":"辣椒油","quantity":30,"unit":"ml"},{"name":"花椒油","quantity":10,"unit":"ml"},
            {"name":"芝麻酱","quantity":15,"unit":"g"},{"name":"蒜末","quantity":15,"unit":"g"},
            {"name":"葱花","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 30, "difficulty": 3, "calories_total": 420,
        "rating": 4.7, "tags": ["宴客", "麻辣鲜香"],
        "instructions": [
            "鸡腿冷水下锅加姜片料酒煮20分钟",
            "捞出冰水浸泡10分钟（皮脆肉嫩）",
            "斩块装盘",
            "调汁：辣椒油+花椒油+芝麻酱+生抽+醋+糖+蒜末",
            "淋汁，撒花生碎葱花",
        ],
    },

    # ======================== 主食 (5道) ========================
    {
        "recipe_id": "r501", "name": "蛋炒饭", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"隔夜米饭","quantity":500,"unit":"g"},{"name":"鸡蛋","quantity":3,"unit":"枚"},
            {"name":"火腿肠","quantity":1,"unit":"根"},{"name":"葱花","quantity":15,"unit":"g"},
            {"name":"青豆","quantity":30,"unit":"g"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 700,
        "rating": 4.4, "tags": ["快手", "人人会"],
        "instructions": [
            "鸡蛋打散，火腿肠切丁",
            "热油炒鸡蛋至凝固捣碎盛出",
            "同锅炒火腿丁青豆",
            "下米饭大火翻炒，打散结块",
            "倒回鸡蛋，加盐",
            "大火翻炒均匀，撒葱花",
        ],
    },
    {
        "recipe_id": "r502", "name": "扬州炒饭", "cuisine": "淮扬菜", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"隔夜米饭","quantity":500,"unit":"g"},{"name":"鸡蛋","quantity":2,"unit":"枚"},
            {"name":"虾仁","quantity":80,"unit":"g"},{"name":"火腿","quantity":50,"unit":"g"},
            {"name":"青豆","quantity":30,"unit":"g"},{"name":"玉米粒","quantity":30,"unit":"g"},
            {"name":"胡萝卜","quantity":0.5,"unit":"根"},
        ],
        "cooking_time_minutes": 15, "difficulty": 2, "calories_total": 780,
        "rating": 4.6, "tags": ["经典", "宴客"],
        "instructions": [
            "所有配料切小丁",
            "热油炒虾仁至变色盛出",
            "炒鸡蛋至凝固盛出",
            "炒蔬菜丁",
            "下米饭大火炒散",
            "加所有配料翻炒",
            "加盐白胡椒粉",
        ],
    },
    {
        "recipe_id": "r503", "name": "肉末茄子盖饭", "cuisine": "家常", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"茄子","quantity":2,"unit":"个"},{"name":"猪肉末","quantity":150,"unit":"g"},
            {"name":"米饭","quantity":400,"unit":"g"},{"name":"蒜末","quantity":15,"unit":"g"},
            {"name":"生抽","quantity":15,"unit":"ml"},{"name":"老抽","quantity":5,"unit":"ml"},
            {"name":"郫县豆瓣酱","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 650,
        "rating": 4.5, "tags": ["下饭", "一人食"],
        "instructions": [
            "茄子切条，撒盐腌制10分钟挤水",
            "热油炒肉末至变色",
            "加豆瓣酱炒出红油",
            "下茄子翻炒",
            "加生抽老抽和少许水焖3分钟",
            "盖在热米饭上",
        ],
    },
    {
        "recipe_id": "r504", "name": "西红柿鸡蛋打卤面", "cuisine": "北方", "meal_type": "lunch",
        "ingredients_required": [
            {"name":"手擀面或挂面","quantity":400,"unit":"g"},{"name":"番茄","quantity":3,"unit":"个"},
            {"name":"鸡蛋","quantity":3,"unit":"枚"},{"name":"木耳","quantity":20,"unit":"g"},
            {"name":"黄花菜","quantity":15,"unit":"g"},
        ],
        "cooking_time_minutes": 20, "difficulty": 2, "calories_total": 600,
        "rating": 4.5, "tags": ["北方经典", "快手"],
        "instructions": [
            "番茄切块，木耳黄花菜泡发",
            "鸡蛋炒熟盛出",
            "炒番茄至出汁，加木耳黄花菜",
            "加水烧开煮5分钟",
            "倒回鸡蛋，水淀粉勾芡",
            "面条煮熟浇卤",
        ],
    },
    {
        "recipe_id": "r505", "name": "煲仔饭", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"大米","quantity":300,"unit":"g"},{"name":"腊肠","quantity":2,"unit":"根"},
            {"name":"腊肉","quantity":100,"unit":"g"},{"name":"上海青","quantity":150,"unit":"g"},
            {"name":"生抽","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 35, "difficulty": 3, "calories_total": 750,
        "rating": 4.7, "tags": ["粤式经典", "锅巴"],
        "instructions": [
            "大米泡30分钟",
            "砂锅刷油，下米加水(1:1.2)",
            "大火烧开转小火",
            "米饭8成熟时铺腊肠腊肉",
            "盖盖小火焖10分钟",
            "沿锅边淋油出锅巴",
            "烫上海青摆放，淋生抽",
        ],
    },

    # ======================== 海鲜 (4道) ========================
    {
        "recipe_id": "r601", "name": "白灼虾", "cuisine": "粤菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"基围虾","quantity":500,"unit":"g"},{"name":"姜片","quantity":15,"unit":"g"},
            {"name":"葱段","quantity":10,"unit":"g"},{"name":"料酒","quantity":15,"unit":"ml"},
        ],
        "cooking_time_minutes": 10, "difficulty": 1, "calories_total": 350,
        "rating": 4.6, "tags": ["快手", "原味", "高蛋白"],
        "instructions": [
            "虾剪去须和脚，挑虾线",
            "水烧开加姜葱料酒",
            "下虾煮至变红卷曲（约2-3分钟）",
            "捞出过冰水（肉更弹）",
            "蘸料：生抽+芥末或姜醋汁",
        ],
    },
    {
        "recipe_id": "r602", "name": "红烧带鱼", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"带鱼","quantity":500,"unit":"g"},{"name":"生抽","quantity":20,"unit":"ml"},
            {"name":"老抽","quantity":10,"unit":"ml"},{"name":"白糖","quantity":10,"unit":"g"},
            {"name":"姜片","quantity":15,"unit":"g"},{"name":"葱段","quantity":15,"unit":"g"},
            {"name":"料酒","quantity":20,"unit":"ml"},
        ],
        "cooking_time_minutes": 25, "difficulty": 2, "calories_total": 450,
        "rating": 4.5, "tags": ["下饭", "家常海鲜"],
        "instructions": [
            "带鱼去内脏洗净切段，划花刀",
            "加料酒姜片腌制15分钟",
            "擦干水分，两面煎至金黄",
            "加生抽老抽糖葱姜",
            "加开水没过鱼身一半",
            "中火烧10分钟收汁",
        ],
    },
    {
        "recipe_id": "r603", "name": "辣炒花蛤", "cuisine": "家常", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"花蛤","quantity":750,"unit":"g"},{"name":"干辣椒","quantity":10,"unit":"g"},
            {"name":"蒜末","quantity":15,"unit":"g"},{"name":"姜丝","quantity":10,"unit":"g"},
            {"name":"豆瓣酱","quantity":15,"unit":"g"},{"name":"香菜","quantity":10,"unit":"g"},
        ],
        "cooking_time_minutes": 15, "difficulty": 1, "calories_total": 280,
        "rating": 4.6, "tags": ["下酒", "快手海鲜"],
        "instructions": [
            "花蛤盐水浸泡2小时吐沙",
            "热油爆香干辣椒蒜姜",
            "加豆瓣酱炒出红油",
            "下花蛤大火翻炒",
            "加料酒盖盖焖2分钟",
            "全部开口后撒香菜",
        ],
    },
    {
        "recipe_id": "r604", "name": "清蒸大闸蟹", "cuisine": "苏菜", "meal_type": "dinner",
        "ingredients_required": [
            {"name":"大闸蟹","quantity":4,"unit":"只"},{"name":"生姜","quantity":30,"unit":"g"},
            {"name":"紫苏","quantity":10,"unit":"g"},{"name":"镇江香醋","quantity":30,"unit":"ml"},
        ],
        "cooking_time_minutes": 20, "difficulty": 1, "calories_total": 320,
        "rating": 4.8, "tags": ["秋季", "宴客", "时令"],
        "instructions": [
            "蟹刷洗干净（不解绳子）",
            "蒸锅水开，蟹肚朝上放",
            "每只蟹上放姜片和紫苏",
            "大火蒸12-15分钟（3两蟹12分钟，4两15分钟）",
            "姜切末加醋调蘸料",
        ],
    },
]


# ================================================================
# 工具函数 — 基于真实数据
# ================================================================

def _tokenize_query(query: str) -> list[str]:
    """中文查询分词：jieba 优先（延迟加载），降级为单字切分 + 原始词组"""
    global _JIEBA_AVAILABLE
    if _JIEBA_AVAILABLE is None:
        try:
            import jieba
            _JIEBA_AVAILABLE = True
        except (ImportError, MemoryError):
            _JIEBA_AVAILABLE = False

    if _JIEBA_AVAILABLE:
        import jieba
        tokens = list(jieba.cut(query))
        # 过滤掉纯标点和空白
        tokens = [t.strip() for t in tokens if t.strip() and len(t.strip()) > 1]
        # 始终保留原始查询作为完整词组（处理专有名词如"黄焖鸡"）
        if query not in tokens:
            tokens.append(query)
        # 也加入2-gram滑动窗口，提高召回
        chars = query.replace(" ", "")
        for i in range(len(chars) - 1):
            bigram = chars[i:i+2]
            if bigram not in tokens:
                tokens.append(bigram)
        return tokens
    else:
        # 无 jieba：逐字切分 + 原始查询
        tokens = [query]
        chars = query.replace(" ", "")
        for i in range(len(chars)):
            if chars[i] not in "怎么做如何烹饪":  # 过滤口语助词
                tokens.append(chars[i])
        # 2-gram
        for i in range(len(chars) - 1):
            tokens.append(chars[i:i+2])
        return tokens


def _recipe_search_score(recipe: dict, query_tokens: list[str]) -> float:
    """计算菜谱与查询的相关度分数（0~1）

    搜索范围：
      - 菜名（权重 3.0）
      - 标签（权重 2.0）
      - 菜系（权重 1.5）
      - 食材名称（权重 1.0）
      - 烹饪步骤（权重 0.5，用于匹配烹饪方式如"炒"、"焖"、"炖"）
    """
    name = recipe.get("name", "")
    tags = " ".join(recipe.get("tags", []))
    cuisine = recipe.get("cuisine", "")
    ingredients = " ".join(
        ing["name"] for ing in recipe.get("ingredients_required", [])
    )
    instructions = " ".join(recipe.get("instructions", []))

    # 搜索域及权重
    fields = [
        (name, 3.0),
        (tags, 2.0),
        (cuisine, 1.5),
        (ingredients, 1.0),
        (instructions, 0.5),
    ]

    total_weight = 0.0
    matched_weight = 0.0

    for token in query_tokens:
        token_weight = 1.0
        for field_text, field_weight in fields:
            if token in field_text:
                matched_weight += field_weight * token_weight
            total_weight += field_weight * token_weight

    if total_weight == 0:
        return 0.0
    return matched_weight / total_weight


async def search_recipes(
    query: str = "",
    meal_type: str = "",
    cuisine: str = "",
    max_cooking_time: int = 0,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[Recipe]:
    """搜索菜谱 — 中文分词 + 多维度加权评分

    支持部分匹配："黄焖鸡炒饭" → 匹配"黄焖鸡"和"炒饭"相关菜谱
    """
    query_tokens = _tokenize_query(query) if query else []

    scored_results: list[tuple[float, dict]] = []
    for r in RECIPES:
        # 硬性筛选条件
        if meal_type and r["meal_type"] != meal_type:
            continue
        if cuisine and r["cuisine"] != cuisine:
            continue
        if max_cooking_time > 0 and r["cooking_time_minutes"] > max_cooking_time:
            continue
        if tags:
            recipe_tags = r.get("tags", [])
            if not any(t in recipe_tags for t in tags):
                continue

        # 查询评分
        if query_tokens:
            score = _recipe_search_score(r, query_tokens)
            if score <= 0:
                continue  # 完全不相关，跳过
            scored_results.append((score, r))
        else:
            scored_results.append((0, r))

    # 按评分降序，同分按 rating 降序
    scored_results.sort(key=lambda x: (x[0], x[1].get("rating", 0)), reverse=True)

    # 最低相关度阈值：低于此分数认为"不相关"，触发 fallback
    MIN_RELEVANCE = 0.12

    if scored_results and scored_results[0][0] >= MIN_RELEVANCE:
        return [Recipe(**r) for _, r in scored_results[:limit]]

    # ═══════════════════════════════════════════════════════
    # Fallback: 知识库无匹配 → 返回最接近的菜谱 + 引导LLM自行回答
    # ═══════════════════════════════════════════════════════
    closest = _find_closest_any(query_tokens, limit=5) if query_tokens else RECIPES[:5]
    return {
        "fallback": True,
        "message": (
            f"知识库中没有与「{query}」精确匹配的菜谱。"
            f"以下是最接近的{len(closest)}道菜（仅作参考）："
        ),
        "suggestions": [
            {
                "name": r["name"],
                "cuisine": r["cuisine"],
                "cooking_time_minutes": r["cooking_time_minutes"],
                "difficulty": r["difficulty"],
                "tags": r.get("tags", []),
                "ingredients": [ing["name"] for ing in r.get("ingredients_required", [])[:5]],
            }
            for r in closest
        ],
        "hint": (
            "请使用你的烹饪知识直接为用户解答。"
            "如果用户问的是菜谱做法，请给出详细食材清单和步骤。"
            "如果完全不了解，诚实告知并建议用户换个关键词或补充到知识库。"
        ),
    }


def _find_closest_any(tokens: list[str], limit: int = 5) -> list[dict]:
    """无精确匹配时，找到任意维度有交集的最近菜谱"""
    scored = []
    for r in RECIPES:
        score = _recipe_search_score(r, tokens)
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: (x[0], x[1].get("rating", 0)), reverse=True)
    return [r for _, r in scored[:limit]]


async def get_recipe_detail(recipe_id: str) -> Recipe | None:
    """获取菜谱详情"""
    for r in RECIPES:
        if r["recipe_id"] == recipe_id:
            return Recipe(**r)
    return None


async def match_recipes_by_ingredients(
    fridge_ingredients: list[str],
    meal_type: str = "",
    limit: int = 5,
) -> list[dict]:
    """根据现有食材匹配可做的菜"""
    fridge_set = set(fridge_ingredients)
    scored = []
    for r in RECIPES:
        required = {ing["name"] for ing in r["ingredients_required"]}
        if not required:
            continue
        matched = required & fridge_set
        if not matched:
            continue
        score = len(matched) / len(required)
        missing = required - matched
        scored.append({
            "recipe_id": r["recipe_id"],
            "name": r["name"],
            "cuisine": r["cuisine"],
            "cooking_time_minutes": r["cooking_time_minutes"],
            "difficulty": r["difficulty"],
            "calories_total": r["calories_total"],
            "rating": r["rating"],
            "match_score": round(score, 2),
            "matched_ingredients": list(matched),
            "missing_ingredients": list(missing),
        })

    if meal_type:
        scored = [s for s in scored if any(
            r["meal_type"] == meal_type for r in RECIPES if r["recipe_id"] == s["recipe_id"]
        )]

    scored.sort(key=lambda x: (x["match_score"], x["rating"]), reverse=True)
    return scored[:limit]


async def generate_meal_plan(
    user_id: str,
    fridge_inventory: list[dict],
    preferences: list[str] | None = None,
    allergies: list[str] | None = None,
    start_date: date | None = None,
    days: int = 7,
) -> MealPlan:
    """智能生成一周菜谱 — 优先消耗临期食材，营养均衡"""
    if start_date is None:
        start_date = date.today() + timedelta(days=1)
    elif isinstance(start_date, str):
        # LLM 传参是字符串，需要解析为 date
        start_date = date.fromisoformat(start_date)
    end_date = start_date + timedelta(days=days - 1)

    fridge_names = [item["name"] for item in fridge_inventory]
    meals: dict[str, list[Recipe]] = {}
    daily_cal: dict[str, float] = {}
    used_recipes: set[str] = set()

    for d in range(days):
        day = (start_date + timedelta(days=d)).isoformat()
        day_meals = []
        day_cal = 0.0

        for mt in ["breakfast", "lunch", "dinner"]:
            # 优先匹配冰箱里有食材的
            matches = await match_recipes_by_ingredients(fridge_names, mt, limit=5)

            # 过滤过敏物
            if allergies:
                matches = [
                    m for m in matches
                    if not any(
                        a in [ing["name"] for ing in (
                            next(r for r in RECIPES if r["recipe_id"] == m["recipe_id"])
                        )["ingredients_required"]]
                        for a in allergies
                    )
                ]

            # 避免重复
            for m in matches:
                if m["recipe_id"] not in used_recipes:
                    r = await get_recipe_detail(m["recipe_id"])
                    if r:
                        day_meals.append(r)
                        day_cal += r.calories_total
                        used_recipes.add(m["recipe_id"])
                        break

        meals[day] = day_meals
        daily_cal[day] = round(day_cal, 1)

    plan_id = f"plan_{start_date.isoformat()}_{end_date.isoformat()}"
    # 写入数据库（去重：同一日期范围 → 更新）
    try:
        from sqlalchemy import select
        async for session in get_db():
            dup = (await session.execute(
                select(MealPlanRecord).where(
                    MealPlanRecord.user_id == user_id,
                    MealPlanRecord.start_date == start_date,
                    MealPlanRecord.end_date == end_date,
                )
            )).scalars().first()
            if dup:
                dup.meals = meals
            else:
                session.add(MealPlanRecord(
                    plan_id=plan_id, user_id=user_id,
                    start_date=start_date, end_date=end_date,
                    meals=meals,
                ))
            await session.commit()
    except Exception:
        pass
    return MealPlan(
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date,
        meals=meals,
        total_calories_daily=daily_cal,
        generated_from_fridge=bool(fridge_names),
    )


# ================================================================
# 菜谱向量化索引 — 启动时索引到 Qdrant，支持语义搜索
# ================================================================

_RECIPES_INDEXED = False


async def index_recipes_to_vectordb(force: bool = False) -> int:
    """将所有菜谱文档化后索引到 Qdrant

    每道菜生成一份结构化文本，包含菜名、菜系、食材、做法、标签。
    索引后 BGE-M3 + BM25 混合检索可以直接搜到菜谱。
    """
    global _RECIPES_INDEXED
    if _RECIPES_INDEXED and not force:
        return 0

    try:
        from ..rag.embeddings import get_embedding_generator
        from ..memory.vector_store import get_vector_store
    except ImportError:
        return 0

    vector_store = get_vector_store()

    # 检查是否已索引（通过 collection 中是否有 recipe 标签的文档）
    try:
        if vector_store.collection and vector_store.collection.count() > 0:
            existing = vector_store.collection.get(
                where={"source": "recipe_db"}, limit=1
            )
            if existing and existing.get("ids"):
                _RECIPES_INDEXED = True
                return 0  # 已索引，跳过
    except Exception:
        pass  # 首次启动或无 collection，继续索引

    texts = []
    ids_list = []
    metadatas = []

    for r in RECIPES:
        # 构建结构化文本，让 BGE-M3 能捕获语义
        ingredients_text = "、".join(
            f"{ing['name']}{ing['quantity']}{ing['unit']}"
            for ing in r.get("ingredients_required", [])
        )
        instructions_text = "；".join(r.get("instructions", []))
        tags_text = "、".join(r.get("tags", []))

        doc_text = (
            f"【{r['name']}】{r['cuisine']}菜，{r['meal_type']}类。"
            f"需要食材：{ingredients_text}。"
            f"做法：{instructions_text}。"
            f"烹饪{r['cooking_time_minutes']}分钟，难度{r['difficulty']}星，"
            f"约{r['calories_total']}千卡。标签：{tags_text}。"
        )

        texts.append(doc_text)
        ids_list.append(f"recipe_{r['recipe_id']}")
        metadatas.append({
            "source": "recipe_db",
            "recipe_id": r["recipe_id"],
            "name": r["name"],
            "cuisine": r["cuisine"],
            "meal_type": r["meal_type"],
            "cooking_time": r["cooking_time_minutes"],
            "difficulty": r["difficulty"],
            "calories": r["calories_total"],
            "rating": r["rating"],
        })

    if not texts:
        return 0

    # 用 BGE-M3 批量生成 embedding
    try:
        embedder = get_embedding_generator()
        result = await embedder.embed_documents(texts)
        embeddings = result.get("dense_vecs", [])
    except Exception:
        embeddings = None  # 让 Qdrant 自己处理（可能失败）

    # 入库
    await vector_store.add(
        texts=texts,
        metadatas=metadatas,
        ids=ids_list,
        embeddings=embeddings,
    )

    _RECIPES_INDEXED = True
    from loguru import logger
    logger.success(f"Indexed {len(texts)} recipes into Qdrant (BGE-M3 semantic search ready)")
    return len(texts)


# ================================================================
# 家电保养知识库 — 启动时索引到 Qdrant
# ================================================================

HOUSEHOLD_KNOWLEDGE = [
    {
        "id": "knowledge_appliance_1",
        "title": "扫地机器人保养指南",
        "category": "家电保养",
        "text": (
            "扫地机器人保养指南："
            "1. 滤网每30天用清水冲洗并晾干24小时；"
            "2. 主刷每30天用剪刀和清洁刷清理缠绕毛发；"
            "3. 边刷每90天更换原装边刷；"
            "4. 传感器每30天用干布擦拭保持灵敏；"
            "5. 主刷每180天更换（约79元），滤芯每180天更换（约49元）；"
            "6. 尘盒每60天用清水深度清洁。"
            "定期保养可延长寿命至3-5年，避免维修费用。"
        ),
    },
    {
        "id": "knowledge_appliance_2",
        "title": "洗衣机保养指南",
        "category": "家电保养",
        "text": (
            "洗衣机保养指南："
            "1. 筒自洁每90天运行一次（用专用清洁剂，约25元）；"
            "2. 门封圈每30天用湿布擦拭防止发霉；"
            "3. 洗涤剂盒每30天用热水冲洗防止结块；"
            "4. 排水过滤器每90天清理硬币杂物；"
            "5. 进水管每180天检查有无裂纹老化；"
            "6. 每年进行一次深度除垢（约50元）。"
            "洗完衣服后打开门通风30分钟，防止霉菌滋生。"
        ),
    },
    {
        "id": "knowledge_appliance_3",
        "title": "洗碗机保养指南",
        "category": "家电保养",
        "text": (
            "洗碗机保养指南："
            "1. 滤网每30天用热水和刷子清洗；"
            "2. 喷臂每90天用牙签清除堵塞物保证喷射力；"
            "3. 门封条每60天用湿布清洁防止漏水；"
            "4. 洗碗盐每30天补充（约25元），亮碟剂每30天补充（约35元）；"
            "5. 机体每180天用专用清洁剂深度清洁（约30元）。"
            "碗碟放入前先刮掉大块残渣，不要预冲洗浪费水。"
        ),
    },
    {
        "id": "knowledge_appliance_4",
        "title": "空调保养指南",
        "category": "家电保养",
        "text": (
            "空调保养指南："
            "1. 过滤网每30天拆下清水冲洗晾干再装回；"
            "2. 室外机散热片每180天用专用清洁剂和软刷清理；"
            "3. 制冷剂压力每年检查一次（约200元）；"
            "4. 排水管每180天疏通防堵塞；"
            "5. 蒸发器每年深度清洗一次（约300元）。"
            "夏季使用前务必清洗过滤网，否则制冷效果大打折扣且更费电。"
        ),
    },
    {
        "id": "knowledge_appliance_5",
        "title": "冰箱保养与收纳",
        "category": "家电保养",
        "text": (
            "冰箱保养与收纳指南："
            "1. 门封条每30天用湿布蘸清洁剂擦拭保弹性；"
            "2. 内部每60天用小苏打水擦拭除味；"
            "3. 排水孔每90天用细铁丝疏通防堵塞；"
            "4. 冷凝器每180天用吸尘器清理背面灰尘；"
            "5. 冷藏室温度设3-5°C，冷冻室-18°C最省电。"
            "收纳原则：上层放熟食剩菜，中层放乳制品，下层放生肉海鲜（防交叉污染），"
            "门架放调味品饮料，抽屉放蔬果。遵循先入先出原则，每周检查临期食材。"
        ),
    },
    {
        "id": "knowledge_appliance_6",
        "title": "错峰用电省钱攻略",
        "category": "节能技巧",
        "text": (
            "家庭错峰用电省钱攻略（以北京居民电价为例）："
            "峰电时段8:00-22:00，电价0.53元/度；"
            "谷电时段22:00-次日8:00，电价0.30元/度（节省43%）。"
            "推荐错峰运行顺序：22:00洗碗机→23:30洗衣机→凌晨扫地机器人。"
            "这三台家电错峰运行，每次可省：洗碗机约0.20元，洗衣机约0.06元，扫地机约0.03元。"
            "一个月累计可省约8-15元，一年可省100-180元。"
            "注意：第一档电量0-2880度/年，超量后二档加0.05元，三档加0.30元。"
        ),
    },
    {
        "id": "knowledge_appliance_7",
        "title": "食材保鲜存储指南",
        "category": "生活技巧",
        "text": (
            "食材保鲜存储指南："
            "叶菜类如菠菜生菜，冷藏保存3-5天，用厨房纸巾包好放保鲜袋；"
            "根茎类如土豆胡萝卜，常温阴凉处放1-2周，不要洗；"
            "肉类冷冻可存3-6个月，海鲜冷冻1-2个月，分装成小份避免反复解冻；"
            "蛋类冷藏3-5周，牛奶开封后冷藏3-5天喝完；"
            "干货如香菇木耳，密封常温可存6-12个月。"
            "关键原则：生熟分开、密封防潮、标注日期、先入先出。"
        ),
    },
    {
        "id": "knowledge_appliance_8",
        "title": "家电维保常见故障排查",
        "category": "家电保养",
        "text": (
            "家电常见故障快速排查："
            "扫地机器人不启动→检查电量是否充足，尘盒是否已满；"
            "洗衣机不排水→清理排水过滤器，检查排水管是否弯折；"
            "洗碗机洗不干净→检查喷臂是否堵塞，洗碗盐是否用完；"
            "空调不制冷→清洗过滤网，检查遥控器模式是否为制冷，室外机是否被遮挡；"
            "冰箱结冰严重→检查门封条密封性，确认温度设置合理。"
            "以上问题如自行排查后仍未解决，请联系品牌售后或附近维修师傅。"
        ),
    },
]

_KNOWLEDGE_INDEXED = False


async def index_knowledge_to_vectordb(force: bool = False) -> int:
    """将家电保养等生活知识索引到 Qdrant"""
    global _KNOWLEDGE_INDEXED
    if _KNOWLEDGE_INDEXED and not force:
        return 0

    try:
        from ..rag.embeddings import get_embedding_generator
        from ..memory.vector_store import get_vector_store
    except ImportError:
        return 0

    vector_store = get_vector_store()

    # 检查是否已索引
    try:
        if vector_store.collection and vector_store.collection.count() > 0:
            existing = vector_store.collection.get(
                where={"source": "household_knowledge"}, limit=1
            )
            if existing and existing.get("ids"):
                _KNOWLEDGE_INDEXED = True
                return 0
    except Exception:
        pass

    texts = []
    ids_list = []
    metadatas = []

    for k in HOUSEHOLD_KNOWLEDGE:
        texts.append(k["text"])
        ids_list.append(k["id"])
        metadatas.append({
            "source": "household_knowledge",
            "title": k["title"],
            "category": k["category"],
        })

    try:
        embedder = get_embedding_generator()
        result = await embedder.embed_documents(texts)
        embeddings = result.get("dense_vecs", [])
    except Exception:
        embeddings = None

    await vector_store.add(
        texts=texts,
        metadatas=metadatas,
        ids=ids_list,
        embeddings=embeddings,
    )

    _KNOWLEDGE_INDEXED = True
    from loguru import logger
    logger.success(f"Indexed {len(texts)} household knowledge docs into Qdrant")
    return len(texts)
