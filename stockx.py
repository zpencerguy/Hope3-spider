#!/usr/bin/env python
# -*- coding: utf-8 -*-

import helper
import re
import qiniuUploader
import json
import mongo
import os
import time
from threading import Thread
try:
    from queue import Queue
except ImportError:
    from Queue import Queue
from pyquery import PyQuery


error_detail_url = {}


class PageSpider(Thread):
    def __init__(self, url, q, error_page_url_queue):
        # 重写写父类的__init__方法
        super(PageSpider, self).__init__()
        self.url = url
        self.q = q
        self.error_page_url_queue = error_page_url_queue


    def run(self):
        try:
            json_txt = helper.get(self.url, returnText=True)
            json_data = json.loads(json_txt)
            products = json_data.get('Products')
            for p in products:
                self.q.put('https://stockx.com/%s' % p.get('urlKey'))
        except:
            helper.log('[ERROR] => ' + self.url, 'stockx')
            self.error_page_url_queue.put(self.url)


class GoodsSpider(Thread):
    def __init__(self, url, q, crawl_counter):
        # 重写写父类的__init__方法
        super(GoodsSpider, self).__init__()
        self.url = url
        self.q = q
        self.crawl_counter = crawl_counter


    def run(self):
        '''
        解析网站源码
        '''
        try:
            pq = helper.get(self.url)
            # 款型名称
            name = pq('h1.name').text()
            number = ''
            color_value = ''
            # price = 0.0
            for div in pq('div.detail'):
                div = PyQuery(div)
                key = div.find('span.title').text()
                if key == 'Style':
                    # 配色的编号
                    number = div.find('span')[-1].text.strip()
                elif key == 'Colorway':
                    color_value = div.find('span')[-1].text.strip()
                # elif key == 'Retail Price':
                #     price = div.find('span')[-1].text.replace('US$', '').strip()
                #     price = float(price)
            # 找出所有尺寸
            size_price_arr = []
            div_list = PyQuery(pq('div.select-options')[0]).find('div.inset div')
            for i in range(0, len(div_list), 2):
                if div_list[i].text == 'All':
                    continue
                if div_list[i + 1].text == 'Bid':
                    size_price_arr.append({
                        'size': div_list[i].text,
                        'price': 0.0,
                        'isInStock': False
                    })
                else:
                    size_price_arr.append({
                        'size': div_list[i].text,
                        'price': float(div_list[i + 1].text.replace('US$', '').replace(',', '').strip()),
                        'isInStock': True
                    })
            mongo.insert_pending_goods(name, number, self.url, size_price_arr, ['%s.jpg' % number], 0, color_value, 'stockx', '5bace180c7e854cab4dbcc83', self.crawl_counter)
            # 下载图片
            img_url = ''
            img_list = pq('div.image-container img')
            if img_list:
                img_url = img_list[-1].get('src')
            else:
                img_url = pq('div.product-media img').attr('src')
            img_url_list = img_url.split('?')
            img_url_query_list = img_url_list[1].split('&')
            for i in range(0, len(img_url_query_list)):
                if img_url_query_list[i].split('=')[0] == 'w':
                    img_url_query_list[i] = 'w=600'
                elif  img_url_query_list[i].split('=')[0] == 'h':
                    img_url_query_list[i] = 'h=600'
            img_url = img_url_list[0] + '?' + '&'.join(img_url_query_list)
            # print(img_url)
            result = helper.downloadImg(img_url, os.path.join('.', 'imgs', 'stockx', '%s.jpg' % number))
            if result == 1:
                # 上传到七牛
                qiniuUploader.upload_2_qiniu('stockx', '%s.jpg' % number, './imgs/stockx/%s.jpg' % number)
        except:
            global error_detail_url
            error_counter = error_detail_url.get(self.url, 1)
            error_detail_url[self.url] = error_counter + 1
            helper.log('[ERROR] error timer = %s, url = %s' % (error_counter, self.url), 'stockx')
            if error_counter < 3:
                self.q.put(self.url)


def fetch_page(url_list, q, error_page_url_queue, crawl_counter):
    page_thread_list = []
    # 构造所有url
    for url in url_list:
        # 创建并启动线程
        time.sleep(1.2)
        page_spider = PageSpider(url, q, error_page_url_queue)
        page_spider.start()
        page_thread_list.append(page_spider)
    for t in page_thread_list:
        t.join()

    goods_thread_list = []
    while True:
        queue_size = q.qsize()
        if queue_size > 0:
            # 每次启动5个抓取商品的线程
            for i in range(5 if queue_size > 5 else queue_size):
                time.sleep(2)
                goods_spider = GoodsSpider(q.get(), q, crawl_counter)
                goods_spider.start()
                goods_thread_list.append(goods_spider)
            for t in goods_thread_list:
                t.join()
            goods_thread_list = []
        else:
            break


def start():
    crawl_counter = mongo.get_crawl_counter('stockx')
    # 创建一个队列用来保存进程获取到的数据
    q = Queue()
    # 有错误的页面链接
    error_page_url_queue = Queue()
    url = 'https://stockx.com/api/browse?order=DESC&page=1&productCategory=sneakers&sort=release_date'
    json_txt = helper.get(url, returnText=True)
    json_data = json.loads(json_txt)
    pagination = json_data.get('Pagination')
    total_page = pagination.get('lastPage')
    fetch_page(['https://stockx.com/api/browse?order=DESC&page=%d&productCategory=sneakers&sort=release_date' % page for page in range(1, total_page + 1)], q, error_page_url_queue, crawl_counter)

    # 处理出错的链接
    while not error_page_url_queue.empty():
        error_page_url_list = []
        while not error_page_url_queue.empty():
            error_page_url_list.append(error_page_url_queue.get())

        fetch_page(error_page_url_list, q, error_page_url_queue, crawl_counter)

    helper.log('done', 'stockx')
