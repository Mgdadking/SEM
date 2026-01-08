"""
نظام مراقبة منصة ادرس في مصر للتخصصات - نسخة Web Service
محدث للعمل على Render المجاني مع Flask
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import json
from datetime import datetime
import requests
import os
import threading
from flask import Flask, jsonify

# إنشاء Flask app
app = Flask(__name__)

class StudyInEgyptMonitor:
    def __init__(self, username, password, target_programs, telegram_token=None, telegram_chat_id=None):
        """
        username: اسم المستخدم للمنصة
        password: كلمة المرور
        target_programs: قائمة بأسماء التخصصات المطلوبة
        telegram_token: توكن بوت التليجرام (اختياري)
        telegram_chat_id: معرف المحادثة في التليجرام (اختياري)
        """
        self.username = username
        self.password = password
        self.target_programs = [p.strip() for p in target_programs]
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.found_programs = set()
        self.last_programs = set()
        self.is_running = False
        self.driver = None
        self.status = {"state": "initialized", "last_check": None, "checks_count": 0}
        
    def init_driver(self):
        """تهيئة المتصفح"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # للعمل على Render
        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium-browser")
        
        self.driver = webdriver.Chrome(options=chrome_options)
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
    
    def login(self):
        """تسجيل الدخول للمنصة"""
        try:
            self.log_message("جاري تسجيل الدخول...")
            self.driver.get(f"{self.base_url}/login")
            
            wait = WebDriverWait(self.driver, 20)
            
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            password_field = self.driver.find_element(By.NAME, "password")
            
            username_field.send_keys(self.username)
            password_field.send_keys(self.password)
            
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()
            
            time.sleep(5)
            
            self.log_message("تم تسجيل الدخول بنجاح")
            self.status["state"] = "logged_in"
            return True
            
        except Exception as e:
            self.log_message(f"خطأ في تسجيل الدخول: {e}")
            self.status["state"] = "login_failed"
            return False
    
    def check_programs(self, request_url):
        """فحص التخصصات المتاحة"""
        try:
            self.driver.get(request_url)
            time.sleep(3)
            
            selectors = [
                "//div[contains(@class, 'react-select__single-value')]",
                "//div[contains(@class, 'react-select__option')]",
            ]
            
            current_programs = set()
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        if text and len(text) > 3:
                            current_programs.add(text)
                except:
                    continue
            
            try:
                select_element = self.driver.find_element(By.XPATH, "//div[contains(@class, 'react-select__control')]")
                select_element.click()
                time.sleep(2)
                
                options = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'react-select__option')]")
                for option in options:
                    text = option.text.strip()
                    if text and len(text) > 3:
                        current_programs.add(text)
                
                select_element.click()
                
            except Exception as e:
                self.log_message(f"تعذر فتح القائمة المنسدلة: {e}")
            
            self.log_message(f"تم العثور على {len(current_programs)} تخصص")
            
            new_programs = current_programs - self.last_programs
            
            if new_programs:
                self.log_message(f"تخصصات جديدة: {len(new_programs)}")
                for prog in new_programs:
                    self.log_message(f"  - {prog}")
            
            self.last_programs = current_programs
            self.status["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status["checks_count"] += 1
            
            for program in current_programs:
                for target in self.target_programs:
                    if target.lower() in program.lower() and program not in self.found_programs:
                        self.found_programs.add(program)
                        
                        alert = f"""
🎯 <b>تم العثور على التخصص المطلوب!</b>

📚 <b>اسم التخصص:</b>
{program}

🔍 <b>التخصص المستهدف:</b>
{target}

⏰ <b>الوقت:</b>
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 <b>الرابط:</b>
{request_url}

⚡ <b>اذهب الآن للتقديم!</b>
                        """
                        
                        self.log_message(f"🎯 تنبيه: تم العثور على {program}")
                        self.send_telegram_alert(alert)
                        self.status["state"] = "target_found"
                        
                        try:
                            screenshot_name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            self.driver.save_screenshot(screenshot_name)
                            self.log_message(f"تم حفظ لقطة الشاشة: {screenshot_name}")
                        except:
                            pass
                        
                        return True
            
            return False
            
        except Exception as e:
            self.log_message(f"خطأ أثناء الفحص: {e}")
            self.status["state"] = "check_error"
            return False
    
    def start_monitoring(self, request_url, interval=30):
        """بدء المراقبة المستمرة"""
        self.is_running = True
        self.log_message("=" * 50)
        self.log_message("بدء نظام المراقبة")
        self.log_message("=" * 50)
        self.log_message(f"التخصصات المستهدفة: {', '.join(self.target_programs)}")
        self.log_message(f"فترة الفحص: كل {interval} ثانية")
        
        self.init_driver()
        
        if not self.login():
            self.log_message("فشل تسجيل الدخول. إيقاف البرنامج.")
            self.is_running = False
            return
        
        self.send_telegram_alert("🚀 تم بدء نظام المراقبة بنجاح!")
        
        check_count = 0
        
        try:
            while self.is_running:
                check_count += 1
                self.log_message(f"\n--- الفحص رقم {check_count} ---")
                
                found = self.check_programs(request_url)
                
                if found:
                    self.log_message("✅ تم العثور على تخصص مستهدف!")
                else:
                    self.log_message("⏳ لم يتم العثور على تخصصات جديدة")
                
                self.log_message(f"انتظار {interval} ثانية للفحص التالي...")
                time.sleep(interval)
                
        except Exception as e:
            self.log_message(f"❌ خطأ غير متوقع: {e}")
            self.status["state"] = "error"
            self.send_telegram_alert(f"❌ خطأ في النظام: {e}")
        finally:
            if self.driver:
                self.driver.quit()
    
    def get_status(self):
        """الحصول على حالة النظام"""
        return self.status
    
    def stop(self):
        """إيقاف المراقبة"""
        self.is_running = False
        if self.driver:
            self.driver.quit()

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
        print("❌ خطأ: يجب تعيين جميع المتغيرات البيئية المطلوبة!")
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
    """صفحة رئيسية بسيطة"""
    return jsonify({
        "status": "running",
        "service": "Study Egypt Monitor",
        "message": "النظام يعمل بشكل طبيعي"
    })

@app.route('/health')
def health():
    """فحص صحة النظام"""
    if monitor:
        return jsonify({
            "status": "healthy",
            "monitor_status": monitor.get_status()
        })
    return jsonify({"status": "initializing"})

@app.route('/status')
def status():
    """حالة المراقبة التفصيلية"""
    if monitor:
        return jsonify(monitor.get_status())
    return jsonify({"status": "not_started"})

if __name__ == "__main__":
    # بدء المراقبة في خيط منفصل
    monitor_thread = threading.Thread(target=start_monitor_thread, daemon=True)
    monitor_thread.start()
    
    # بدء Flask server
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
