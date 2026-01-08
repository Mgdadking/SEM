"""
نظام مراقبة منصة ادرس في مصر للتخصصات - محدث
يراقب ظهور التخصصات المطلوبة ويرسل تنبيه فوري
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
        
        # إعداد Chrome للعمل في الخلفية
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
        print(log)
        
        # حفظ في ملف
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
            
            # انتظار حقل اسم المستخدم
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            password_field = self.driver.find_element(By.NAME, "password")
            
            # إدخال البيانات
            username_field.send_keys(self.username)
            password_field.send_keys(self.password)
            
            # الضغط على زر تسجيل الدخول
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()
            
            time.sleep(5)
            
            self.log_message("تم تسجيل الدخول بنجاح")
            return True
            
        except Exception as e:
            self.log_message(f"خطأ في تسجيل الدخول: {e}")
            return False
    
    def check_programs(self, request_url):
        """فحص التخصصات المتاحة"""
        try:
            self.driver.get(request_url)
            time.sleep(3)
            
            # البحث عن عناصر react-select التي تحتوي على التخصصات
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
            
            # فتح القائمة المنسدلة للحصول على جميع الخيارات
            try:
                # البحث عن عنصر react-select
                select_element = self.driver.find_element(By.XPATH, "//div[contains(@class, 'react-select__control')]")
                select_element.click()
                time.sleep(2)
                
                # الحصول على جميع الخيارات
                options = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'react-select__option')]")
                for option in options:
                    text = option.text.strip()
                    if text and len(text) > 3:
                        current_programs.add(text)
                
                # إغلاق القائمة
                select_element.click()
                
            except Exception as e:
                self.log_message(f"تعذر فتح القائمة المنسدلة: {e}")
            
            self.log_message(f"تم العثور على {len(current_programs)} تخصص")
            
            # البحث عن التخصصات الجديدة
            new_programs = current_programs - self.last_programs
            
            if new_programs:
                self.log_message(f"تخصصات جديدة: {len(new_programs)}")
                for prog in new_programs:
                    self.log_message(f"  - {prog}")
            
            self.last_programs = current_programs
            
            # التحقق من التخصصات المستهدفة
            for program in current_programs:
                for target in self.target_programs:
                    # مقارنة غير حساسة لحالة الأحرف وتحتوي على الكلمة
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
                        
                        # محاولة حفظ لقطة شاشة
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
            return False
    
    def start_monitoring(self, request_url, interval=30):
        """بدء المراقبة المستمرة
        request_url: رابط صفحة التقديم الخاصة بك
        interval: الفترة بين كل فحص بالثواني (افتراضي 30 ثانية)
        """
        self.log_message("=" * 50)
        self.log_message("بدء نظام المراقبة")
        self.log_message("=" * 50)
        self.log_message(f"التخصصات المستهدفة: {', '.join(self.target_programs)}")
        self.log_message(f"فترة الفحص: كل {interval} ثانية")
        
        # تسجيل الدخول
        if not self.login():
            self.log_message("فشل تسجيل الدخول. إيقاف البرنامج.")
            return
        
        # إرسال تنبيه ببدء المراقبة
        self.send_telegram_alert("🚀 تم بدء نظام المراقبة بنجاح!")
        
        check_count = 0
        
        try:
            while True:
                check_count += 1
                self.log_message(f"\n--- الفحص رقم {check_count} ---")
                
                found = self.check_programs(request_url)
                
                if found:
                    self.log_message("✅ تم العثور على تخصص مستهدف!")
                else:
                    self.log_message("⏳ لم يتم العثور على تخصصات جديدة")
                
                self.log_message(f"انتظار {interval} ثانية للفحص التالي...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.log_message("\n⛔ تم إيقاف المراقبة بواسطة المستخدم")
            self.send_telegram_alert("⛔ تم إيقاف نظام المراقبة")
        except Exception as e:
            self.log_message(f"❌ خطأ غير متوقع: {e}")
            self.send_telegram_alert(f"❌ خطأ في النظام: {e}")
        finally:
            self.driver.quit()
    
    def close(self):
        """إغلاق المتصفح"""
        self.driver.quit()


# مثال للاستخدام
if __name__ == "__main__":
    # قراءة الإعدادات من متغيرات البيئة (للأمان)
    USERNAME = os.environ.get("STUDY_USERNAME", "your_username")
    PASSWORD = os.environ.get("STUDY_PASSWORD", "your_password")
    REQUEST_URL = os.environ.get("REQUEST_URL", "https://admission.study-in-egypt.gov.eg/services/admission/requests/617947/edit")
    
    # التخصصات المستهدفة
    target_programs = [
        "طب اسنان الزقازيق",
        "علوم الحاسب",
        # أضف التخصصات المطلوبة هنا
    ]
    
    # معلومات التليجرام
    telegram_token = os.environ.get("TELEGRAM_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # إنشاء المراقب
    monitor = StudyInEgyptMonitor(
        username=USERNAME,
        password=PASSWORD,
        target_programs=target_programs,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id
    )
    
    # بدء المراقبة (فحص كل 30 ثانية)
    monitor.start_monitoring(request_url=REQUEST_URL, interval=30)
