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
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
        
        # للعمل على Render - تجربة مسارات مختلفة
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            chrome_options.binary_location = chrome_bin
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.base_url = "https://admission.study-in-egypt.gov.eg"
        except Exception as e:
            self.log_message(f"خطأ في تهيئة ChromeDriver: {e}")
            raise
        
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
            
            wait = WebDriverWait(self.driver, 30)
            
            # انتظار حقول الإدخال
            self.log_message("انتظار ظهور حقول تسجيل الدخول...")
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            password_field = wait.until(EC.presence_of_element_located((By.NAME, "password")))
            
            self.log_message("إدخال اسم المستخدم وكلمة المرور...")
            username_field.clear()
            username_field.send_keys(self.username)
            time.sleep(1)
            
            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(1)
            
            # البحث عن زر تسجيل الدخول بطرق مختلفة
            self.log_message("البحث عن زر تسجيل الدخول...")
            
            # الطريقة 1: بالنص العربي
            try:
                login_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(), 'تسجيل الدخول')]]")
                ))
                self.log_message("وجدت زر تسجيل الدخول (الطريقة 1)")
            except:
                # الطريقة 2: button مع div و span
                try:
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[.//div/span[text()='تسجيل الدخول']]")
                    ))
                    self.log_message("وجدت زر تسجيل الدخول (الطريقة 2)")
                except:
                    # الطريقة 3: أي زر submit
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[@type='submit']")
                    ))
                    self.log_message("وجدت زر تسجيل الدخول (الطريقة 3)")
            
            self.log_message("الضغط على زر تسجيل الدخول...")
            login_button.click()
            
            # انتظار اكتمال تسجيل الدخول
            time.sleep(5)
            
            # التحقق من نجاح تسجيل الدخول
            current_url = self.driver.current_url
            self.log_message(f"الصفحة الحالية: {current_url}")
            
            if "login" not in current_url.lower():
                self.log_message("✅ تم تسجيل الدخول بنجاح")
                self.status["state"] = "logged_in"
                return True
            else:
                self.log_message("⚠️ ما زلنا في صفحة تسجيل الدخول - قد تكون بيانات خاطئة")
                self.status["state"] = "login_failed"
                return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في تسجيل الدخول: {e}")
            self.log_message(f"الصفحة الحالية: {self.driver.current_url}")
            
            # محاولة أخذ لقطة شاشة للتشخيص
            try:
                self.driver.save_screenshot("login_error.png")
                self.log_message("تم حفظ لقطة شاشة للخطأ: login_error.png")
            except:
                pass
            
            self.status["state"] = "login_failed"
            return False
    
    def check_programs(self, request_url):
        """فحص التخصصات المتاحة"""
        try:
            self.log_message(f"فتح صفحة التقديم: {request_url}")
            self.driver.get(request_url)
            time.sleep(5)
            
            # فتح القائمة المنسدلة للحصول على جميع الخيارات
            self.log_message("البحث عن القائمة المنسدلة للتخصصات...")
            
            current_programs = set()
            
            try:
                # البحث عن react-select control
                select_control = self.driver.find_element(By.XPATH, "//div[contains(@class, 'react-select__control')]")
                self.log_message("✅ وجدت القائمة المنسدلة")
                
                # الضغط لفتح القائمة
                select_control.click()
                time.sleep(2)
                
                # الحصول على جميع الخيارات
                options = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'react-select__option')]")
                self.log_message(f"وجدت {len(options)} خيار في القائمة")
                
                for option in options:
                    text = option.text.strip()
                    if text and len(text) > 3:
                        current_programs.add(text)
                        self.log_message(f"  - {text}")
                
            except Exception as e:
                self.log_message(f"⚠️ خطأ في فتح القائمة: {e}")
                # محاولة الحصول على القيمة المحددة حالياً
                try:
                    current_value = self.driver.find_element(By.XPATH, "//div[contains(@class, 'react-select__single-value')]")
                    if current_value.text.strip():
                        current_programs.add(current_value.text.strip())
                        self.log_message(f"القيمة الحالية: {current_value.text.strip()}")
                except:
                    pass
            
            self.log_message(f"إجمالي التخصصات المتاحة: {len(current_programs)}")
            
            # البحث عن التخصصات الجديدة
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
                        
                        self.log_message(f"🎯🎯🎯 وجدت التخصص المطلوب: {program} 🎯🎯🎯")
                        
                        # محاولة اختيار التخصص
                        if self.select_program(program):
                            # الضغط على زر الاستمرار
                            if self.click_continue_button():
                                alert = f"""
🎉🎉🎉 <b>تم العثور على التخصص وتم اختياره!</b> 🎉🎉🎉

📚 <b>التخصص:</b>
{program}

✅ <b>الحالة:</b>
تم اختيار التخصص والضغط على زر "استمرار"

⏰ <b>الوقت:</b>
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 <b>الرابط:</b>
{request_url}

⚡⚡⚡ <b>اذهب الآن وأكمل التقديم يدوياً!</b> ⚡⚡⚡

النظام سيتوقف الآن - أكمل أنت الخطوات المتبقية.
                                """
                                
                                self.log_message("📤 إرسال تنبيه التليجرام...")
                                self.send_telegram_alert(alert)
                                self.status["state"] = "target_found_and_selected"
                                
                                # حفظ لقطة شاشة
                                try:
                                    screenshot_name = f"success_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                    self.driver.save_screenshot(screenshot_name)
                                    self.log_message(f"📸 تم حفظ لقطة الشاشة: {screenshot_name}")
                                except:
                                    pass
                                
                                self.log_message("✅ تم! النظام سيتوقف الآن...")
                                self.log_message("👉 أكمل التقديم يدوياً من الرابط")
                                
                                # إيقاف المراقبة
                                self.is_running = False
                                return True
                            else:
                                self.log_message("⚠️ لم أستطع الضغط على زر الاستمرار")
                        else:
                            self.log_message("⚠️ لم أستطع اختيار التخصص تلقائياً")
            
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ أثناء الفحص: {e}")
            self.status["state"] = "check_error"
            return False
    
    def select_program(self, program_name):
        """اختيار التخصص من القائمة المنسدلة"""
        try:
            self.log_message(f"محاولة اختيار التخصص: {program_name}")
            
            # فتح القائمة إذا لم تكن مفتوحة
            select_control = self.driver.find_element(By.XPATH, "//div[contains(@class, 'react-select__control')]")
            select_control.click()
            time.sleep(2)
            
            # البحث عن الخيار المطلوب والضغط عليه
            options = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'react-select__option')]")
            
            for option in options:
                if program_name in option.text:
                    self.log_message(f"✅ وجدت الخيار، سأضغط عليه...")
                    option.click()
                    time.sleep(2)
                    self.log_message("✅ تم اختيار التخصص بنجاح")
                    return True
            
            self.log_message("❌ لم أجد الخيار في القائمة")
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في اختيار التخصص: {e}")
            return False
    
    def click_continue_button(self):
        """الضغط على زر الاستمرار"""
        try:
            self.log_message("البحث عن زر الاستمرار...")
            
            wait = WebDriverWait(self.driver, 10)
            
            # محاولات متعددة للعثور على زر الاستمرار
            continue_selectors = [
                "//button[.//span[contains(text(), 'إستمرار')]]",
                "//button[.//div/span[text()='إستمرار']]",
                "//div[contains(text(), 'إستمرار')]/..",
                "//span[text()='إستمرار']/../..",
            ]
            
            for selector in continue_selectors:
                try:
                    continue_button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    self.log_message(f"✅ وجدت زر الاستمرار")
                    continue_button.click()
                    time.sleep(2)
                    self.log_message("✅ تم الضغط على زر الاستمرار")
                    return True
                except:
                    continue
            
            self.log_message("❌ لم أجد زر الاستمرار")
            return False
            
        except Exception as e:
            self.log_message(f"❌ خطأ في الضغط على زر الاستمرار: {e}")
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
