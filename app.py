from flask import Flask, request, abort, render_template, jsonify, redirect, url_for
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
import json
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

# 從環境變數獲取 LINE Bot 設定
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("請設置 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化資料庫
def init_db():
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        # 創建訂單表
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                items TEXT,
                total REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 創建菜單表
        c.execute('''
            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
                description TEXT,
                image_url TEXT,
                category TEXT,
                available INTEGER DEFAULT 1
            )
        ''')
        
        # 插入示例菜單數據
        c.execute("SELECT COUNT(*) FROM menu")
        if c.fetchone()[0] == 0:
            sample_menu = [
                ("Arm Chair, White", 49.99, "舒適的白色扶手椅", "https://developers-resource.landpress.line.me/fx/img/01_5_carousel.png", "家具", 1),
                ("Metal Desk Lamp", 11.99, "金屬桌燈", "https://developers-resource.landpress.line.me/fx/img/01_6_carousel.png", "燈具", 1),
                ("Energy Drink", 2.99, "提神飲料", "https://example.com/energy_drink.jpg", "飲料", 1),
                ("Chewing Gum", 0.99, "口香糖", "https://example.com/gum.jpg", "零食", 1),
                ("Bottled Water", 3.33, "瓶裝水", "https://example.com/water.jpg", "飲料", 1)
            ]
            c.executemany("INSERT INTO menu (name, price, description, image_url, category, available) VALUES (?, ?, ?, ?, ?, ?)", sample_menu)
        
        conn.commit()
        conn.close()
        print("資料庫初始化成功")
    except Error as e:
        print(f"資料庫初始化錯誤: {e}")

# LINE Webhook 處理
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip().lower()
    
    if text == 'menu':
        send_menu(event)
    elif text == 'order':
        send_order_summary(event)
    elif text == 'confirm':
        confirm_order(event)
    elif text == 'cancel':
        cancel_order(event)
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入 'menu' 查看菜單，'order' 查看當前訂單，'confirm' 確認訂單，或 'cancel' 取消訂單")
        )

# 發送菜單
def send_menu(event):
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute("SELECT * FROM menu WHERE available = 1")
    menu_items = c.fetchall()
    conn.close()
    
    # 載入菜單模板
    with open('menu.txt', 'r') as f:
        flex_template = json.load(f)
    
    # 更新菜單內容
    bubbles = []
    for item in menu_items:
        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover",
                "url": item[4]  # image_url
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": item[1],  # name
                        "wrap": True,
                        "weight": "bold",
                        "size": "xl"
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"${item[2]:.2f}".split('.')[0],
                                "wrap": True,
                                "weight": "bold",
                                "size": "xl",
                                "flex": 0
                            },
                            {
                                "type": "text",
                                "text": f".{str(item[2]).split('.')[1]}",
                                "wrap": True,
                                "weight": "bold",
                                "size": "sm",
                                "flex": 0
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "postback",
                            "label": "加入購物車",
                            "data": f"action=add&item={item[0]}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    # 添加查看更多按鈕
    bubbles.append({
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "flex": 1,
                    "gravity": "center",
                    "action": {
                        "type": "uri",
                        "label": "查看更多",
                        "uri": "https://line.me/"
                    }
                }
            ]
        }
    })
    
    flex_template["contents"] = bubbles
    flex_message = FlexSendMessage(alt_text="菜單", contents=flex_template)
    
    line_bot_api.reply_message(
        event.reply_token,
        flex_message
    )

# 處理 Postback 事件（加入購物車）
@handler.add(MessageEvent, message=TextMessage)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    
    if data.startswith('action=add'):
        item_id = data.split('&')[1].split('=')[1]
        add_to_cart(user_id, item_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="已加入購物車！輸入 'order' 查看當前訂單")
        )

# 添加到購物車
def add_to_cart(user_id, item_id):
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # 檢查是否有未完成的訂單
    c.execute("SELECT id, items FROM orders WHERE user_id = ? AND status = 'pending'", (user_id,))
    order = c.fetchone()
    
    if order:
        order_id, items = order
        items_list = json.loads(items) if items else []
        items_list.append(item_id)
        c.execute("UPDATE orders SET items = ? WHERE id = ?", (json.dumps(items_list), order_id))
    else:
        # 創建新訂單
        items = [item_id]
        c.execute("INSERT INTO orders (user_id, items, status) VALUES (?, ?, 'pending')", 
                 (user_id, json.dumps(items)))
    
    conn.commit()
    conn.close()

# 發送訂單摘要
def send_order_summary(event):
    user_id = event.source.user_id
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # 獲取當前訂單
    c.execute("SELECT items FROM orders WHERE user_id = ? AND status = 'pending'", (user_id,))
    order = c.fetchone()
    
    if not order:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您的購物車是空的。輸入 'menu' 查看菜單")
        )
        return
    
    items = json.loads(order[0])
    
    # 計算總金額和獲取商品詳情
    total = 0
    order_details = []
    
    for item_id in items:
        c.execute("SELECT name, price FROM menu WHERE id = ?", (item_id,))
        item = c.fetchone()
        if item:
            name, price = item
            total += price
            order_details.append({"name": name, "price": price})
    
    conn.close()
    
    # 創建訂單摘要消息
    message = "您的訂單：\n"
    for i, item in enumerate(order_details, 1):
        message += f"{i}. {item['name']} - ${item['price']:.2f}\n"
    
    message += f"\n總計: ${total:.2f}\n\n輸入 'confirm' 確認訂單或 'cancel' 取消訂單"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=message)
    )

# 確認訂單
def confirm_order(event):
    user_id = event.source.user_id
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # 獲取當前訂單
    c.execute("SELECT id, items FROM orders WHERE user_id = ? AND status = 'pending'", (user_id,))
    order = c.fetchone()
    
    if not order:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="沒有待確認的訂單")
        )
        return
    
    order_id, items_json = order
    items = json.loads(items_json)
    
    # 計算總金額
    total = 0
    order_details = []
    
    for item_id in items:
        c.execute("SELECT name, price FROM menu WHERE id = ?", (item_id,))
        item = c.fetchone()
        if item:
            name, price = item
            total += price
            order_details.append({"name": name, "price": price})
    
    # 更新訂單狀態
    c.execute("UPDATE orders SET status = 'confirmed', total = ? WHERE id = ?", (total, order_id))
    conn.commit()
    conn.close()
    
    # 發送收據
    send_receipt(event, order_details, total, order_id)

# 發送收據
def send_receipt(event, order_details, total, order_id):
    # 載入收據模板
    with open('RECEIPT.txt', 'r') as f:
        receipt_template = json.load(f)
    
    # 更新收據內容
    items_content = []
    for item in order_details:
        items_content.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": item["name"],
                    "size": "sm",
                    "color": "#555555",
                    "flex": 0
                },
                {
                    "type": "text",
                    "text": f"${item['price']:.2f}",
                    "size": "sm",
                    "color": "#111111",
                    "align": "end"
                }
            ]
        })
    
    # 更新收據模板中的項目
    receipt_template["body"]["contents"][4]["contents"][0:3] = items_content
    
    # 更新總金額和訂單ID
    receipt_template["body"]["contents"][4]["contents"][5]["contents"][1]["text"] = f"${total:.2f}"
    receipt_template["body"]["contents"][4]["contents"][8]["contents"][1]["text"] = f"#{order_id}"
    
    flex_message = FlexSendMessage(alt_text="收據", contents=receipt_template)
    
    line_bot_api.reply_message(
        event.reply_token,
        flex_message
    )

# 取消訂單
def cancel_order(event):
    user_id = event.source.user_id
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    c.execute("DELETE FROM orders WHERE user_id = ? AND status = 'pending'", (user_id,))
    conn.commit()
    conn.close()
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="訂單已取消")
    )

# 後台管理路由
@app.route('/admin')
def admin_dashboard():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # 獲取訂單統計
    c.execute("SELECT COUNT(*), SUM(total) FROM orders WHERE status = 'confirmed'")
    orders_stats = c.fetchone()
    total_orders = orders_stats[0] if orders_stats[0] else 0
    total_revenue = orders_stats[1] if orders_stats[1] else 0
    
    # 獲取最近訂單
    c.execute("""
        SELECT o.id, o.user_id, o.total, o.created_at, COUNT(json_each.value) as item_count
        FROM orders o, json_each(o.items)
        WHERE o.status = 'confirmed'
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT 10
    """)
    recent_orders = c.fetchall()
    
    conn.close()
    
    return render_template('admin/dashboard.html', 
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders)

@app.route('/admin/orders')
def admin_orders():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    c.execute("""
        SELECT o.id, o.user_id, o.total, o.status, o.created_at, COUNT(json_each.value) as item_count
        FROM orders o, json_each(o.items)
        GROUP BY o.id
        ORDER BY o.created_at DESC
    """)
    orders = c.fetchall()
    
    conn.close()
    
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/menu')
def admin_menu():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM menu")
    menu_items = c.fetchall()
    
    conn.close()
    
    return render_template('admin/menu.html', menu_items=menu_items)

@app.route('/admin/menu/add', methods=['GET', 'POST'])
def add_menu_item():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        image_url = request.form['image_url']
        category = request.form['category']
        available = 1 if 'available' in request.form else 0
        
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        c.execute("INSERT INTO menu (name, price, description, image_url, category, available) VALUES (?, ?, ?, ?, ?, ?)",
                 (name, price, description, image_url, category, available))
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('admin_menu'))
    
    return render_template('admin/add_menu_item.html')

@app.route('/admin/menu/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_menu_item(item_id):
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        image_url = request.form['image_url']
        category = request.form['category']
        available = 1 if 'available' in request.form else 0
        
        c.execute("UPDATE menu SET name=?, price=?, description=?, image_url=?, category=?, available=? WHERE id=?",
                 (name, price, description, image_url, category, available, item_id))
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('admin_menu'))
    
    c.execute("SELECT * FROM menu WHERE id=?", (item_id,))
    menu_item = c.fetchone()
    conn.close()
    
    return render_template('admin/edit_menu_item.html', menu_item=menu_item)

@app.route('/admin/menu/delete/<int:item_id>')
def delete_menu_item(item_id):
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    c.execute("DELETE FROM menu WHERE id=?", (item_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_menu'))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
