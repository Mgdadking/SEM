"""
نظام مراقبة منصة ادرس في مصر - نسخة Playwright محسّنة
أسرع وأكثر استقراراً للعمل على Clever Cloud
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import os
import threading
from datetime import datetime
import requests
from flask import Flask, jsonify

# إنشاء Flask app
app = Flask(__name__)

class StudyInEgyptMonitor:
    def __init__(self, username, password, target_programs, telegram_token=None, telegram_chat_id=None):
        """
        username: اسم المستخدم للمنصة
        password: كلمة المرور
        target_programs: قائمة بأسماء التخصصات المطلوبة
        telegram_token: توكن بوت التليجرام
        telegram_chat_id: معرف المحادثة في التليجرام
        """
        self.username = username
        self.password = password
        self.target_programs = [p.strip() for p in target_programs]
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.found_programs = set()
        self.last_programs = set()
        self.is_running = False
        self.playwright = None
        self.browser = None
        self.page = None
        self.status = {"state": "initialized", "last_check": None, "checks_count": 0}
        self.base_url = "https://admission.study-in-egypt.gov.eg"
        
    def send_telegram_alert(self, message):
        """إرسال تنبيه عبر التليجرام"""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            return response.json()
        except Exception as e:
            self.log_message(f"خطأ في إرسال التنبيه: {e}")
    
    def send_telegram_photo(self, photo_path, caption=""):
        """إرسال صورة عبر التليجرام"""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': self.telegram_chat_id,
                    'caption': caption
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                return response.json()
        except Exception as e:
            self.log_message(f"خطأ في إرسال الصورة: {e}")
    
    def log_message(self, message):
        """تسجيل رسالة مع الوقت"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log = f"[{timestamp}] {message}"
        print(log, flush=True)
        
        try:
            with open("monitor_log.txt", "a", encoding="utf-8") as f:
                f.write(log + "\n")
        except:
            pass
    
    def init_browser(self):
        """تهيئة المتصفح"""
        try:
            self.log_message("تهيئة Playwright...")
            self.playwright = sync_playwright().start()
            
            self.log_message("تشغيل المتصفح...")
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',  # إخفاء automation
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
            
            self.log_message("إنشاء صفحة جديدة...")
            context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='ar-EG',
                timezone_id='Africa/Cairo',
                # إضافة permissions
                permissions=['geolocation'],
                geolocation={'latitude': 30.0444, 'longitude': 31.2357},  # Cairo
                # إضافة extra headers
                extra_http_headers={
                    'Accept-Language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
            self.page = context.new_page()
            
            # إخفاء webdriver و automation flags
            self.page.add_init_script("""
                // إخفاء webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });
                
                // إخفاء automation
                delete navigator.__proto__.webdriver;
                
                // تعديل permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // إضافة plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // إضافة languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ar-EG', 'ar', 'en-US', 'en']
                });
                
                // Chrome runtime
                window.chrome = {
                    runtime: {}
                };
            """)
            
            # زيادة timeout للصفحات البطيئة
            self.page.set_default_timeout(90000)  # 90 ثانية
            
            self.log_message("✅ تم تهيئة المتصفح بنجاح")
            return True
            
        except Exception as e:
            self.log_message(f"❌ خطأ في تهيئة المتصفح: {e}")
            return False
    
    def login(self):
        """تسجيل الدخول للمنصة"""
        try:
            self.log_message("=" * 50)
            self.log_message("بدء عملية تسجيل الدخول...")
            self.log_message("=" * 50)
            
            self.log_message(f"فتح صفحة تسجيل الدخول: {self.base_url}/login")
            self.page.goto(f"{self.base_url}/login", wait_until="networkidle", timeout=90000)
            
            self.log_message("⏳ انتظار تحميل React App...")
            # انتظار اختفاء شاشة التحميل إن وجدت
            try:
                self.page.wait_for_selector('.ant-spin', state='hidden', timeout=10000)
                self.log_message("✅ اختفى loader")
            except:
                self.log_message("⚠️ مافيش loader أو خلص")
            
            # انتظار إضافي للـ React
            time.sleep(8)
            
            # أخذ لقطة شاشة للتشخيص
            try:
                screenshot_path = "login_page.png"
                self.page.screenshot(path=screenshot_path)
                self.log_message("📸 تم حفظ لقطة شاشة للصفحة: login_page.png")
                self.send_telegram_photo(screenshot_path, "📸 صفحة تسجيل الدخول")
            except Exception as e:
                self.log_message(f"خطأ في لقطة الشاشة: {e}")
            
            # محاولات متعددة للعثور على حقول الإدخال
            username_selectors = [
                'input[name="username"]',
                'input[name="email"]',
                'input[type="text"]',
                'input[type="email"]',
                'input[placeholder*="اسم"]',
                'input[placeholder*="username"]',
                'input[placeholder*="email"]',
                'input[placeholder*="البريد"]',
                'input[id*="username"]',
                'input[id*="email"]',
                '#username',
                '#email',
                'input.ant-input:first-of-type',
                'input.form-control:first-of-type',
                '.ant-form-item:first-child input',
            ]
            
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="كلمة"]',
                'input[placeholder*="password"]',
                'input[placeholder*="Password"]',
                'input[placeholder*="المرور"]',
                'input[id*="password"]',
                '#password',
                '.ant-form-item:nth-child(2) input',
                'input[type="password"].ant-input',
            ]
            
            username_field = None
            password_field = None
            
            # البحث عن حقل اسم المستخدم
            self.log_message("البحث عن حقل اسم المستخدم...")
            
            # أولاً: انتظار ظهور أي input
            try:
                self.log_message("انتظار ظهور حقول الإدخال...")
                self.page.wait_for_selector('input', timeout=15000)
                self.log_message("✅ ظهرت حقول الإدخال")
                time.sleep(2)
            except Exception as e:
                self.log_message(f"⚠️ خطأ في انتظار الحقول: {e}")
            
            for selector in username_selectors:
                try:
                    self.log_message(f"  محاولة: {selector}")
                    if self.page.locator(selector).count() > 0:
                        username_field = selector
                        self.log_message(f"  ✅ وجدت الحقل: {selector}")
                        break
                except:
                    continue
            
            if not username_field:
                self.log_message("❌ لم أجد حقل اسم المستخدم!")
                
                # طباعة جميع الـ inputs الموجودة
                try:
                    all_inputs = self.page.locator('input').all()
                    self.log_message(f"عدد الـ inputs الموجودة: {len(all_inputs)}")
                    
                    for i, inp in enumerate(all_inputs[:5]):  # أول 5 فقط
                        try:
                            inp_type = inp.get_attribute('type') or 'none'
                            inp_name = inp.get_attribute('name') or 'none'
                            inp_id = inp.get_attribute('id') or 'none'
                            inp_class = inp.get_attribute('class') or 'none'
                            inp_placeholder = inp.get_attribute('placeholder') or 'none'
                            
                            self.log_message(f"Input {i+1}:")
                            self.log_message(f"  type={inp_type}")
                            self.log_message(f"  name={inp_name}")
                            self.log_message(f"  id={inp_id}")
                            self.log_message(f"  class={inp_class}")
                            self.log_message(f"  placeholder={inp_placeholder}")
                        except:
                            pass
                except Exception as e:
                    self.log_message(f"خطأ في قراءة الـ inputs: {e}")
                
                # طباعة HTML للتشخيص
                try:
                    content = self.page.content()
                    self.log_message("=" * 60)
                    self.log_message("محتوى صفحة تسجيل الدخول:")
                    self.log_message("=" * 60)
                    # طباعة أول 2000 حرف بدل 500
                    self.log_message(content[:2000])
                    self.log_message("=" * 60)
                    
                    # إرسال HTML كملف نصي على Telegram
                    if self.telegram_token and self.telegram_chat_id:
                        try:
                            with open("page_content.html", "w", encoding="utf-8") as f:
                                f.write(content)
                            
                            url = f"https://api.telegram.org/bot{self.telegram_token}/sendDocument"
                            with open("page_content.html", "rb") as doc:
                                files = {'document': doc}
                                data = {
                                    'chat_id': self.telegram_chat_id,
                                    'caption': '📄 محتوى صفحة تسجيل الدخول'
                                }
                                requests.post(url, data=data, files=files, timeout=30)
                        except Exception as e:
                            self.log_message(f"خطأ في إرسال HTML: {e}")
                            
                except Exception as e:
                    self.log_message(f"خطأ في قراءة المحتوى: {e}")
                
                self.status["state"] = "login_failed"
                return False
            
            # البحث عن حقل كلمة المرور
            self.log_message("البحث عن حقل كلمة المرور...")
            for selector in password_selectors:
                try:
                    self.log_message(f"  محاولة: {selector}")
                    if self.page.locator(selector).count() > 0:
                        password_field = selector
                        self.log_message(f"  ✅ وجدت الحقل: {selector}")
                        break
                except:
                    continue
            
            if not password_field:
                self.log_message("❌ لم أجد حقل كلمة المرور!")
                self.status["state"] = "login_failed"
                return False
            
            # إدخال البيانات
            self.log_message("إدخال اسم المستخدم...")
            
            # النقر على الحقل أولاً (simulate human behavior)
            self.page.click(username_field)
            time.sleep(0.5)
            
            # مسح الحقل
            self.page.fill(username_field, '')
            time.sleep(0.3)
            
            # كتابة البيانات ببطء (محاكاة الإنسان)
            # delay عشوائي بين 80-150ms
            import random
            for char in self.username:
                self.page.type(username_field, char, delay=random.randint(80, 150))
            
            time.sleep(1)
            
            # التأكد من إدخال البيانات
            current_value = self.page.input_value(username_field)
            self.log_message(f"✅ القيمة المدخلة: {current_value[:3]}***")
            
            self.log_message("إدخال كلمة المرور...")
            
            # النقر على الحقل
            self.page.click(password_field)
            time.sleep(0.5)
            
            # مسح الحقل
            self.page.fill(password_field, '')
            time.sleep(0.3)
            
            # كتابة كلمة المرور
            for char in self.password:
                self.page.type(password_field, char, delay=random.randint(80, 150))
            
            time.sleep(1.5)
            
            # البحث عن زر تسجيل الدخول والضغط عليه
            self.log_message("البحث عن زر تسجيل الدخول...")
            
            button_selectors = [
                'button:has-text("تسجيل الدخول")',
                'button:has-text("دخول")',
                'button:has-text("Login")',
                'button[type="submit"]',
                'button:has(span:text("تسجيل الدخول"))',
                'button:has(span:text("دخول"))',
                'input[type="submit"]',
                'button.btn-primary',
                'button.submit',
                'button.ant-btn-primary',
                '.ant-btn-primary',
            ]
            
            clicked = False
            for selector in button_selectors:
                try:
                    self.log_message(f"  محاولة: {selector}")
                    if self.page.locator(selector).count() > 0:
                        # التأكد من أن الزر مرئي وقابل للضغط
                        self.page.wait_for_selector(selector, state='visible', timeout=5000)
                        
                        # تحريك الماوس للزر (simulate human)
                        button = self.page.locator(selector).first
                        box = button.bounding_box()
                        if box:
                            # تحريك الماوس لمنتصف الزر
                            self.page.mouse.move(
                                box['x'] + box['width'] / 2,
                                box['y'] + box['height'] / 2
                            )
                            time.sleep(0.3)
                        
                        # الضغط
                        self.page.click(selector, timeout=5000, force=False)
                        clicked = True
                        self.log_message(f"  ✅ تم الضغط على الزر")
                        break
                except Exception as e:
                    self.log_message(f"  ⚠️ فشلت: {e}")
                    continue
            
            if not clicked:
                # محاولة أخيرة: الضغط على Enter
                self.log_message("محاولة الضغط على Enter...")
                try:
                    self.page.keyboard.press("Enter")
                    clicked = True
                    self.log_message("✅ تم الضغط على Enter")
                except:
                    self.log_message("❌ لم أجد زر تسجيل الدخول")
                    return False
            
            # انتظار اكتمال تسجيل الدخول
            self.log_message("⏳ انتظار اكتمال تسجيل الدخول...")
            time.sleep(5)
            
            # التحقق من وجود رسائل خطأ أولاً
            error_messages = []
            validation_failed = False
            
            try:
                error_selectors = [
                    '.ant-form-item-explain-error',
                    '.ant-alert-error',
                    '.alert-danger',
                    '.error',
                    '.text-danger',
                    '[class*="error"]',
                    '[class*="Error"]',
                ]
                
                for sel in error_selectors:
                    if self.page.locator(sel).count() > 0:
                        messages = self.page.locator(sel).all()
                        for msg in messages:
                            try:
                                text = msg.inner_text().strip()
                                if text and len(text) > 2:
                                    error_messages.append(text)
                                    if 'validation' in text.lower() or 'البريد' in text or 'email' in text.lower():
                                        validation_failed = True
                            except:
                                pass
            except:
                pass
            
            if error_messages:
                self.log_message(f"⚠️ رسائل خطأ: {', '.join(error_messages)}")
                
                # إرسال على Telegram
                error_text = "❌ فشل تسجيل الدخول\n\n"
                error_text += "رسائل الخطأ:\n"
                for err in error_messages:
                    error_text += f"• {err}\n"
                
                self.send_telegram_alert(error_text)
                
                # لو المشكلة في البريد الإلكتروني
                if validation_failed:
                    self.log_message("❌ بيانات الدخول غير صحيحة!")
                    self.log_message("💡 تحقق من:")
                    self.log_message("   1. البريد الإلكتروني صحيح")
                    self.log_message("   2. كلمة المرور صحيحة")
                    self.log_message("   3. الحساب مُفعّل")
            
            # انتظار إضافي
            time.sleep(3)
            
            # التحقق من نجاح تسجيل الدخول
            current_url = self.page.url
            self.log_message(f"الصفحة الحالية: {current_url}")
            
            # أخذ لقطة شاشة بعد المحاولة
            try:
                screenshot_path = "after_login.png"
                self.page.screenshot(path=screenshot_path)
                self.log_message("📸 لقطة شاشة بعد تسجيل الدخول: after_login.png")
                self.send_telegram_photo(screenshot_path, "📸 بعد محاولة تسجيل الدخول")
            except Exception as e:
                self.log_message(f"خطأ في لقطة الشاشة: {e}")
            
            if "login" not in current_url.lower():
                self.log_message("✅✅✅ تم تسجيل الدخول بنجاح! ✅✅✅")
                self.status["state"] = "logged_in"
                self.send_telegram_alert("✅ تم تسجيل الدخول بنجاح!")
                return True
            else:
                # التحقق من وجود رسائل خطأ لم نكتشفها
                if not error_messages:
                    try:
                        error_selectors = [
                            '.ant-form-item-explain-error',
                            '.ant-alert-danger',
                            '.alert-danger',
                            '.error-message',
                        ]
                        for sel in error_selectors:
                            if self.page.locator(sel).count() > 0:
                                msg = self.page.locator(sel).first.inner_text()
                                if msg:
                                    error_messages.append(msg)
                    except:
                        pass
                
                if error_messages:
                    self.log_message(f"⚠️ رسائل خطأ: {', '.join(error_messages)}")
                else:
                    self.log_message("⚠️ ما زلنا في صفحة تسجيل الدخول")
                
                self.status["state"] = "login_failed"
                return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في تسجيل الدخول: {e}")
            
            try:
                screenshot_path = "login_error.png"
                self.page.screenshot(path=screenshot_path)
                self.log_message("📸 تم حفظ لقطة شاشة: login_error.png")
                self.send_telegram_photo(screenshot_path, f"❌ خطأ في تسجيل الدخول: {e}")
            except Exception as screenshot_error:
                self.log_message(f"خطأ في لقطة الشاشة: {screenshot_error}")
            
            self.status["state"] = "login_failed"
            return False
    
    def check_programs(self, request_url):
        """فحص التخصصات المتاحة"""
        try:
            self.log_message(f"🔍 فتح صفحة التقديم...")
            self.page.goto(request_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            
            # أخذ لقطة شاشة
            try:
                screenshot_path = "request_page.png"
                self.page.screenshot(path=screenshot_path)
                self.log_message("📸 لقطة شاشة لصفحة التقديم: request_page.png")
                self.send_telegram_photo(screenshot_path, "📋 صفحة التقديم")
            except Exception as e:
                self.log_message(f"خطأ في لقطة الشاشة: {e}")
            
            self.log_message("البحث عن القائمة المنسدلة...")
            
            current_programs = set()
            
            try:
                # البحث عن react-select control
                select_selectors = [
                    'div[class*="react-select__control"]',
                    'div[class*="select__control"]',
                    '[class*="select-control"]',
                    'select',
                    '[role="combobox"]',
                ]
                
                select_found = None
                for selector in select_selectors:
                    try:
                        if self.page.locator(selector).count() > 0:
                            select_found = selector
                            self.log_message(f"✅ وجدت القائمة: {selector}")
                            break
                    except:
                        continue
                
                if not select_found:
                    self.log_message("⚠️ لم أجد القائمة المنسدلة")
                    return False
                
                self.log_message("محاولة فتح القائمة المنسدلة...")
                self.page.click(select_found, timeout=10000)
                time.sleep(3)
                
                # الحصول على جميع الخيارات
                option_selectors = [
                    'div[class*="react-select__option"]',
                    'div[class*="select__option"]',
                    '[role="option"]',
                    'option',
                ]
                
                options = None
                for selector in option_selectors:
                    try:
                        if self.page.locator(selector).count() > 0:
                            options = self.page.locator(selector).all()
                            self.log_message(f"✅ وجدت الخيارات: {selector}")
                            break
                    except:
                        continue
                
                if options and len(options) > 0:
                    self.log_message(f"✅ وجدت {len(options)} خيار")
                    
                    for option in options:
                        try:
                            text = option.inner_text().strip()
                            if text and len(text) > 3:
                                current_programs.add(text)
                                self.log_message(f"  📋 {text}")
                        except:
                            continue
                    
                    # إغلاق القائمة
                    self.page.keyboard.press("Escape")
                    time.sleep(1)
                else:
                    self.log_message("⚠️ لم أجد خيارات")
                
            except Exception as e:
                self.log_message(f"⚠️ خطأ في فتح القائمة: {e}")
                
                # محاولة الحصول على القيمة الحالية
                try:
                    value_selectors = [
                        'div[class*="react-select__single-value"]',
                        'div[class*="select__value"]',
                        '[class*="selected-value"]',
                    ]
                    
                    for selector in value_selectors:
                        if self.page.locator(selector).count() > 0:
                            text = self.page.locator(selector).first.inner_text().strip()
                            if text:
                                current_programs.add(text)
                                self.log_message(f"القيمة الحالية: {text}")
                                break
                except:
                    pass
            
            self.log_message(f"📊 إجمالي التخصصات: {len(current_programs)}")
            
            # البحث عن تخصصات جديدة
            new_programs = current_programs - self.last_programs
            if new_programs:
                self.log_message(f"🆕 تخصصات جديدة: {len(new_programs)}")
                for prog in new_programs:
                    self.log_message(f"  ➕ {prog}")
            
            self.last_programs = current_programs
            self.status["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status["checks_count"] += 1
            
            # التحقق من التخصصات المستهدفة
            for program in current_programs:
                for target in self.target_programs:
                    if target.lower() in program.lower() and program not in self.found_programs:
                        self.found_programs.add(program)
                        
                        self.log_message("=" * 60)
                        self.log_message(f"🎯🎯🎯 وجدت التخصص: {program} 🎯🎯🎯")
                        self.log_message("=" * 60)
                        
                        # اختيار التخصص
                        if self.select_program(program):
                            # الضغط على استمرار
                            if self.click_continue_button():
                                alert = f"""
🎉🎉🎉 <b>تم العثور على التخصص!</b> 🎉🎉🎉

📚 <b>التخصص:</b>
{program}

✅ <b>تم:</b>
• اختيار التخصص
• الضغط على "استمرار"

⏰ <b>الوقت:</b>
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 <b>الرابط:</b>
{request_url}

⚡⚡⚡ <b>اذهب الآن وأكمل التقديم!</b> ⚡⚡⚡
                                """
                                
                                self.send_telegram_alert(alert)
                                self.status["state"] = "success"
                                
                                # لقطة شاشة
                                try:
                                    filename = f"success_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                    self.page.screenshot(path=filename)
                                    self.log_message(f"📸 لقطة الشاشة: {filename}")
                                    self.send_telegram_photo(filename, f"🎉 نجح! تم اختيار {program}")
                                except Exception as e:
                                    self.log_message(f"خطأ في لقطة الشاشة: {e}")
                                
                                self.log_message("✅ تم! سأتوقف الآن...")
                                self.is_running = False
                                return True
            
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في الفحص: {e}")
            self.status["state"] = "check_error"
            return False
    
    def select_program(self, program_name):
        """اختيار التخصص"""
        try:
            self.log_message(f"اختيار: {program_name}")
            
            # فتح القائمة
            select_selectors = [
                'div[class*="react-select__control"]',
                'div[class*="select__control"]',
            ]
            
            for selector in select_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector)
                        time.sleep(2)
                        break
                except:
                    continue
            
            # البحث والضغط على الخيار
            option_selectors = [
                'div[class*="react-select__option"]',
                'div[class*="select__option"]',
                '[role="option"]',
            ]
            
            for selector in option_selectors:
                try:
                    options = self.page.locator(selector).all()
                    for option in options:
                        if program_name in option.inner_text():
                            option.click()
                            time.sleep(2)
                            self.log_message("✅ تم اختيار التخصص")
                            return True
                except:
                    continue
            
            self.log_message("❌ لم أجد الخيار")
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في الاختيار: {e}")
            return False
    
    def click_continue_button(self):
        """الضغط على زر استمرار"""
        try:
            self.log_message("البحث عن زر استمرار...")
            
            button_selectors = [
                'button:has-text("إستمرار")',
                'button:has-text("استمرار")',
                'button:has-text("Continue")',
                'button:has(span:text("إستمرار"))',
                'button:has(span:text("استمرار"))',
                'button.btn-primary',
                'button[type="submit"]',
            ]
            
            for selector in button_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector, timeout=5000)
                        time.sleep(2)
                        self.log_message("✅ تم الضغط على استمرار")
                        return True
                except:
                    continue
            
            self.log_message("❌ لم أجد زر استمرار")
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ: {e}")
            return False
    
    def start_monitoring(self, request_url, interval=30):
        """بدء المراقبة"""
        self.is_running = True
        self.log_message("=" * 60)
        self.log_message("🚀 بدء نظام المراقبة")
        self.log_message("=" * 60)
        self.log_message(f"📚 التخصصات: {', '.join(self.target_programs)}")
        self.log_message(f"⏱️ فترة الفحص: {interval} ثانية")
        
        if not self.init_browser():
            self.log_message("❌ فشل تهيئة المتصفح")
            return
        
        if not self.login():
            self.log_message("❌ فشل تسجيل الدخول")
            self.log_message("💡 تحقق من بيانات الدخول والـ screenshots")
            self.cleanup()
            return
        
        self.send_telegram_alert("🚀 بدأ النظام!")
        
        check_count = 0
        
        try:
            while self.is_running:
                check_count += 1
                self.log_message(f"\n{'='*60}")
                self.log_message(f"🔍 الفحص رقم {check_count}")
                self.log_message(f"{'='*60}")
                
                found = self.check_programs(request_url)
                
                if found:
                    self.log_message("✅ تم!")
                    break
                else:
                    self.log_message(f"⏳ انتظار {interval} ثانية...")
                    time.sleep(interval)
                
        except KeyboardInterrupt:
            self.log_message("⛔ توقف يدوي")
            self.send_telegram_alert("⛔ توقف النظام")
        except Exception as e:
            self.log_message(f"❌ خطأ: {e}")
            self.send_telegram_alert(f"❌ خطأ: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """تنظيف الموارد"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.log_message("✅ تم التنظيف")
        except:
            pass
    
    def get_status(self):
        """حالة النظام"""
        return self.status
    
    def stop(self):
        """إيقاف"""
        self.is_running = False
        self.cleanup()

# المراقب العام
monitor = None

def start_monitor_thread():
    """بدء المراقبة في خيط منفصل"""
    global monitor
    
    USERNAME = os.environ.get("STUDY_USERNAME")
    PASSWORD = os.environ.get("STUDY_PASSWORD")
    REQUEST_URL = os.environ.get("REQUEST_URL")
    
    target_programs = os.environ.get("TARGET_PROGRAMS", "").split(",")
    target_programs = [p.strip() for p in target_programs if p.strip()]
    
    telegram_token = os.environ.get("TELEGRAM_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not all([USERNAME, PASSWORD, REQUEST_URL, target_programs]):
        print("❌ خطأ: متغيرات البيئة غير مكتملة!")
        print(f"USERNAME: {'✓' if USERNAME else '✗'}")
        print(f"PASSWORD: {'✓' if PASSWORD else '✗'}")
        print(f"REQUEST_URL: {'✓' if REQUEST_URL else '✗'}")
        print(f"TARGET_PROGRAMS: {'✓' if target_programs else '✗'}")
        return
    
    monitor = StudyInEgyptMonitor(
        username=USERNAME,
        password=PASSWORD,
        target_programs=target_programs,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id
    )
    
    interval = int(os.environ.get("CHECK_INTERVAL", "30"))
    monitor.start_monitoring(request_url=REQUEST_URL, interval=interval)

# Flask Routes
@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "service": "Study Egypt Monitor - Playwright (Enhanced)",
        "message": "النظام يعمل"
    })

@app.route('/health')
def health():
    if monitor:
        return jsonify({
            "status": "healthy",
            "monitor_status": monitor.get_status()
        })
    return jsonify({"status": "initializing"})

@app.route('/status')
def status():
    if monitor:
        return jsonify(monitor.get_status())
    return jsonify({"status": "not_started"})

if __name__ == "__main__":
    # بدء المراقبة
    monitor_thread = threading.Thread(target=start_monitor_thread, daemon=True)
    monitor_thread.start()
    
    # بدء Flask
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
