"""
نظام مراقبة منصة ادرس في مصر - نسخة Playwright
أسرع وأكثر استقراراً للعمل على Render
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
                ]
            )
            
            self.log_message("إنشاء صفحة جديدة...")
            context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = context.new_page()
            
            # زيادة timeout للصفحات البطيئة
            self.page.set_default_timeout(60000)  # 60 ثانية
            
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
            self.page.goto(f"{self.base_url}/login", wait_until="networkidle")
            
            self.log_message("⏳ انتظار تحميل الصفحة...")
            time.sleep(3)
            
            # انتظار ظهور حقول الإدخال
            self.log_message("البحث عن حقل اسم المستخدم...")
            self.page.wait_for_selector('input[name="username"]', timeout=30000)
            
            self.log_message("✅ وجدت حقول الإدخال")
            
            # إدخال البيانات
            self.log_message("إدخال اسم المستخدم...")
            self.page.fill('input[name="username"]', self.username)
            time.sleep(1)
            
            self.log_message("إدخال كلمة المرور...")
            self.page.fill('input[name="password"]', self.password)
            time.sleep(1)
            
            # البحث عن زر تسجيل الدخول والضغط عليه
            self.log_message("البحث عن زر تسجيل الدخول...")
            
            # محاولات متعددة للعثور على الزر
            button_selectors = [
                'button:has-text("تسجيل الدخول")',
                'button[type="submit"]',
                'button:has(span:text("تسجيل الدخول"))',
            ]
            
            clicked = False
            for selector in button_selectors:
                try:
                    self.log_message(f"محاولة: {selector}")
                    self.page.click(selector, timeout=5000)
                    clicked = True
                    self.log_message(f"✅ تم الضغط على الزر بنجاح")
                    break
                except:
                    continue
            
            if not clicked:
                self.log_message("❌ لم أجد زر تسجيل الدخول")
                return False
            
            # انتظار اكتمال تسجيل الدخول
            self.log_message("⏳ انتظار اكتمال تسجيل الدخول...")
            time.sleep(5)
            
            # التحقق من نجاح تسجيل الدخول
            current_url = self.page.url
            self.log_message(f"الصفحة الحالية: {current_url}")
            
            if "login" not in current_url.lower():
                self.log_message("✅✅✅ تم تسجيل الدخول بنجاح! ✅✅✅")
                self.status["state"] = "logged_in"
                return True
            else:
                self.log_message("⚠️ ما زلنا في صفحة تسجيل الدخول - قد تكون بيانات خاطئة")
                
                # محاولة أخذ لقطة شاشة
                try:
                    self.page.screenshot(path="login_failed.png")
                    self.log_message("📸 تم حفظ لقطة شاشة: login_failed.png")
                except:
                    pass
                
                self.status["state"] = "login_failed"
                return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في تسجيل الدخول: {e}")
            
            try:
                self.page.screenshot(path="login_error.png")
                self.log_message("📸 تم حفظ لقطة شاشة: login_error.png")
            except:
                pass
            
            self.status["state"] = "login_failed"
            return False
    
    def check_programs(self, request_url):
        """فحص التخصصات المتاحة"""
        try:
            self.log_message(f"🔍 فتح صفحة التقديم...")
            self.page.goto(request_url, wait_until="networkidle")
            time.sleep(3)
            
            self.log_message("البحث عن القائمة المنسدلة...")
            
            current_programs = set()
            
            try:
                # البحث عن react-select control
                self.log_message("محاولة فتح القائمة المنسدلة...")
                self.page.click('div[class*="react-select__control"]', timeout=10000)
                time.sleep(2)
                
                # الحصول على جميع الخيارات
                options = self.page.query_selector_all('div[class*="react-select__option"]')
                self.log_message(f"✅ وجدت {len(options)} خيار")
                
                for option in options:
                    text = option.inner_text().strip()
                    if text and len(text) > 3:
                        current_programs.add(text)
                        self.log_message(f"  📋 {text}")
                
                # إغلاق القائمة
                self.page.keyboard.press("Escape")
                time.sleep(1)
                
            except Exception as e:
                self.log_message(f"⚠️ خطأ في فتح القائمة: {e}")
                
                # محاولة الحصول على القيمة الحالية
                try:
                    current_value = self.page.query_selector('div[class*="react-select__single-value"]')
                    if current_value:
                        text = current_value.inner_text().strip()
                        if text:
                            current_programs.add(text)
                            self.log_message(f"القيمة الحالية: {text}")
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
                                except:
                                    pass
                                
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
            self.page.click('div[class*="react-select__control"]')
            time.sleep(2)
            
            # البحث والضغط على الخيار
            options = self.page.query_selector_all('div[class*="react-select__option"]')
            
            for option in options:
                if program_name in option.inner_text():
                    option.click()
                    time.sleep(2)
                    self.log_message("✅ تم اختيار التخصص")
                    return True
            
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
                'button:has(span:text("إستمرار"))',
                'button:has(span:text("استمرار"))',
            ]
            
            for selector in button_selectors:
                try:
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
        "service": "Study Egypt Monitor - Playwright",
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
