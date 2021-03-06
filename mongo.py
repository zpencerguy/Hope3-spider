#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pymongo import MongoClient
from bson import objectid
import datetime

conn = MongoClient('106.15.93.73', 27017)
# 连接NAS数据库，没有则自动创建
db = conn.Hope3
# 使用models集合，没有则自动创建
identity_counter_collection = db.identitycounters
pending_goods_collection = db.hope_pendinggoods
goods_collection = db.hope_goods
goods_color_collection = db.hope_goodscolors
goods_type_collection = db.hope_goodstypes
sku_history_collection = db.hope_sku_history
# goods = db.goods
# skus = db.skus
# goodsTypeColor = db.goodstypecolors


# def get_pending_goods(query):
#     global pendingGoods
#     result = pendingGoods.find(query, {})
#     return result


# def get_one_sku(query, fields={}):
#     global skus
#     result = skus.find_one(query, fields)
#     return result


# def get_one_goods_type_color(query, fields={}):
#     global goodsTypeColor
#     result = goodsTypeColor.find_one(query, fields)
#     return result


# def update_goods_type_color(query, update):
#     global goodsTypeColor
#     goodsTypeColor.update(query, update)

def is_pending_goods_deleted(url):
    global pending_goods_collection
    result = pending_goods_collection.find_one({'url': url}, {'is_deleted': 1})
    if result:
        return result.get('is_deleted', False)
    return False


def is_pending_goods_img_downloaded(url):
    global pending_goods_collection
    result = pending_goods_collection.find_one({'url': url}, {'img_downloaded': 1})
    if result:
        return result.get('img_downloaded', False)
    return False


def get_goods_update_date(url):
    global goods_collection
    goods = goods_collection.find_one({'url': url}, {'update_sku_time': 1})
    if goods:
        return goods.get('update_sku_time', datetime.datetime(1970, 1, 1))
    return datetime.datetime(1970, 1, 1)


def get_pending_goods_id():
    global identity_counter_collection
    result = identity_counter_collection.find_one({'model': 'PendingGoods'})
    if result:
        count = result.get('count', 1)
        identity_counter_collection.update({'model': 'PendingGoods'}, {'$inc': {'count': 1}})
    else:
        count = 0
        identity_counter_collection.insert({'model': 'PendingGoods', 'count': 1, '__v': 0})
    return count + 1


def get_crawl_counter(platform):
    '''
    获取当前爬虫执行的次数
    '''
    global identity_counter_collection
    model_name = '%sCrawlCounter' % platform
    result = identity_counter_collection.find_one({'model': model_name})
    if result:
        count = result.get('count', 1)
        identity_counter_collection.update({'model': model_name}, {'$inc': {'count': 1}})
    else:
        count = 0
        identity_counter_collection.insert({'model': model_name, 'count': 1, '__v': 0})
    return count + 1


def insert_pending_goods(name, number, url, size_price_arr, imgs, gender, color_value, platform, platform_id, crawl_counter, color_name='', img_downloaded=True):
    name = name.upper()
    global pending_goods_collection
    pending_goods = pending_goods_collection.find_one({'url': url})
    if pending_goods:
        global goods_collection
        global sku_history_collection
        goods = goods_collection.find_one({'url': url})
        if goods:
            sku_arr = goods.get('sku')
            # 将已有的sku保存到历史表里
            for sku in sku_arr:
                sku_history = sku_history_collection.find_one({
                    'goods_id': goods.get('_id'),
                    'size': sku.get('size'),
                    'date': goods.get('update_sku_time', datetime.datetime(2018, 8, 1))
                })
                if not sku_history:
                    sku_history_collection.insert({
                        # 'goods_id': objectid.ObjectId(goods.)
                        'goods_id': goods.get('_id'),
                        'size': sku.get('size'),
                        'price': sku.get('price'),
                        # 'date': goods.get('update_sku_time', datetime.datetime.now() - datetime.timedelta(days=1))
                        'date': goods.get('update_sku_time', datetime.datetime(2018, 8, 1))
                    })
            # 将最新的sku数据更新到商品中
            sku_arr = []
            for s in size_price_arr:
                sku_arr.append({
                    '_id': objectid.ObjectId(),
                    'size': s.get('size'),
                    'price': float(s.get('price')),
                    'isInStock': s.get('isInStock')
                })
            goods_collection.update({'_id': goods.get('_id')}, {'$set': {
                'update_sku_time': datetime.datetime.now(),
                'sku': sku_arr,
                'update_counter': crawl_counter,
            }})
        # 将最新的sku数据更新到待处理商品中
        pending_goods_collection.update({'_id': pending_goods.get('_id')}, {'$set': {
            'platform': platform,
            'platform_id': objectid.ObjectId(platform_id),
            'gender': gender,
            'color_value': color_value,
            'color_name': color_name,
            'name': name,
            'number': number,
            'url': url,
            'size_price_arr': size_price_arr,
            'imgs': imgs,
            'is_checked': False,
            'is_deleted': False,
            'img_downloaded': img_downloaded,
        }})
        return False
    id = get_pending_goods_id()
    pending_goods_collection.insert({
        'id': id,
        'platform': platform,
        'platform_id': objectid.ObjectId(platform_id),
        'gender': gender,
        'color_value': color_value,
        'color_name': color_name,
        'name': name,
        'number': number,
        'url': url,
        'size_price_arr': size_price_arr,
        'imgs': imgs,
        'is_checked': False,
        'is_deleted': False,
        'img_downloaded': img_downloaded,
        '__v': 0
    })
    return True


def add_hot_platform_with_number(platform_id, number):
    '''根据平台上的number去增加拥有这个number的配色的热度'''
    platform_id = objectid.ObjectId(platform_id)
    goods_color = goods_color_collection.find_one({'number': number}, {'goods_type_id': 1, 'hot': 1})
    if goods_color:
        hot_platform_list = goods_color.get('hot', [])
        if platform_id not in hot_platform_list:
            hot_platform_list.append(platform_id)
            goods_color_collection.update({"_id": goods_color.get('_id')}, {'$set': {'hot': hot_platform_list, 'hot_degree': len(hot_platform_list)}})
            goods_type_id = goods_color.get('goods_type_id')
            goods_type_collection.update({'_id': goods_type_id}, {'$set': {'is_hot': True}})
        return True
    # 再去看看penging里找找看
    pending_goods = pending_goods_collection.find_one({'number': number, 'platform_id': platform_id}, {'name': 1})
    if pending_goods:
        pending_goods_collection.update({'_id': pending_goods.get('_id')}, {'$set': {'priority': 100}})
        return True
    return False