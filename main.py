#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XServer GAME 自动登录和续期脚本
"""

# =====================================================================
#                          导入依赖
# =====================================================================

import asyncio
import time
import re
import datetime
from datetime import timezone, timedelta
import os
import json
import requests
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

# =====================================================================
#                          配置区域
# =====================================================================

# 浏览器配置
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
USE_HEADLESS = IS_GITHUB_ACTIONS or os.getenv("USE_HEADLESS", "false").lower() == "true"
WAIT_TIMEOUT = 10000     # 页面元素等待超时时间（毫秒）
PAGE_LOAD_DELAY = 3      # 页面加载延迟时间（秒）

# XServer登录配置
LOGIN_EMAIL = os.getenv("XSERVER_EMAIL")
LOGIN_PASSWORD = os.getenv("XSERVER_PASSWORD")
TARGET_URL = "https://secure.xserver.ne.jp/xapanel/login/xmgame"

# =====================================================================
#                      Cloudmail配置加载模块
# =====================================================================

def load_cloud_mail_config():
    """从环境变量加载cloudmail配置"""
    cloud_mail_env = os.getenv("CLOUD_MAIL")
    if cloud_mail_env:
        try:
            config = json.loads(cloud_mail_env)
            print("✅ 已从环境变量 CLOUD_MAIL 加载邮箱配置")
            return config
        except json.JSONDecodeError as e:
            print(f"❌ CLOUD_MAIL 环境变量JSON解析失败: {e}")
            return None
    else:
        print("❌ 未找到 CLOUD_MAIL 环境变量")
        return None

# 加载并提取cloudmail配置
CLOUD_MAIL_CONFIG = load_cloud_mail_config() or {}
CLOUDMAIL_API_BASE_URL = CLOUD_MAIL_CONFIG.get("API_BASE_URL")
CLOUDMAIL_EMAIL = CLOUD_MAIL_CONFIG.get("EMAIL")
CLOUDMAIL_PASSWORD = CLOUD_MAIL_CONFIG.get("PASSWORD")
CLOUDMAIL_JWT_SECRET = CLOUD_MAIL_CONFIG.get("JWT_SECRET")
CLOUDMAIL_SEND_EMAIL = CLOUD_MAIL_CONFIG.get("SEND_EMAIL")
CLOUDMAIL_TO_EMAIL = CLOUD_MAIL_CONFIG.get("TO_EMAIL")
CLOUDMAIL_SUBJECT = CLOUD_MAIL_CONFIG.get("SUBJECT")
CLOUDMAIL_LOCAL_FILTER = True  # 启用本地过滤（避免日文主题在API中识别失败）

# =====================================================================
#                        XServer 自动登录类
# =====================================================================

class XServerAutoLogin:
    """XServer GAME 自动登录主类 - Playwright版本"""
    
    def __init__(self):
        """
        初始化 XServer GAME 自动登录器
        使用配置区域的设置
        """
        self.browser = None
        self.context = None
        self.page = None
        self.headless = USE_HEADLESS
        self.email = LOGIN_EMAIL
        self.password = LOGIN_PASSWORD
        self.target_url = TARGET_URL
        self.wait_timeout = WAIT_TIMEOUT
        self.page_load_delay = PAGE_LOAD_DELAY
        self.screenshot_count = 0  # 截图计数器
        
        # 邮箱API配置
        self.cloudmail_api_base_url = CLOUDMAIL_API_BASE_URL
        self.cloudmail_email = CLOUDMAIL_EMAIL
        self.cloudmail_password = CLOUDMAIL_PASSWORD
        self.cloudmail_jwt_secret = CLOUDMAIL_JWT_SECRET
        self.cloudmail_send_email = CLOUDMAIL_SEND_EMAIL
        self.cloudmail_to_email = CLOUDMAIL_TO_EMAIL
        self.cloudmail_subject = CLOUDMAIL_SUBJECT
        self.cloudmail_local_filter = CLOUDMAIL_LOCAL_FILTER
        
        # 续期状态跟踪
        self.old_expiry_time = None      # 原到期时间
        self.new_expiry_time = None      # 新到期时间
        self.renewal_status = "Unknown"  # 续期状态: Success/Unexpired/Failed/Unknown
    
    
    # =================================================================
    #                       1. 浏览器管理模块
    # =================================================================
        
    async def setup_browser(self):
        """设置并启动 Playwright 浏览器"""
        try:
            playwright = await async_playwright().start()
            
            # 配置浏览器选项
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-notifications',
                '--window-size=1920,1080',
                '--lang=ja-JP',
                '--accept-lang=ja-JP,ja,en-US,en'
            ]
            
            # 启动浏览器
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # 创建页面
            self.page = await self.context.new_page()
            
            # 应用stealth插件
            await stealth_async(self.page)
            print("✅ Stealth 插件已应用")
            
            print("✅ Playwright 浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"❌ Playwright 浏览器初始化失败: {e}")
            return False
    
    async def take_screenshot(self, step_name=""):
        """截图功能 - 用于可视化调试"""
        try:
            if self.page:
                self.screenshot_count += 1
                # 使用北京时间（UTC+8）
                beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
                timestamp = beijing_time.strftime("%H%M%S")
                filename = f"step_{self.screenshot_count:02d}_{timestamp}_{step_name}.png"
                
                # 确保文件名安全
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                
                await self.page.screenshot(path=filename, full_page=True)
                print(f"📸 截图已保存: {filename}")
                
        except Exception as e:
            print(f"⚠️ 截图失败: {e}")
    
    def validate_config(self):
        """验证配置信息"""
        if not self.email or not self.password:
            print("❌ 邮箱或密码未设置！")
            return False
        
        print("✅ 配置信息验证通过")
        return True
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            print("🧹 浏览器已关闭")
        except Exception as e:
            print(f"⚠️ 清理资源时出错: {e}")
    
    # =================================================================
    #                       2. 页面导航模块
    # =================================================================
    
    async def navigate_to_login(self):
        """导航到登录页面"""
        try:
            print(f"🌐 正在访问: {self.target_url}")
            await self.page.goto(self.target_url, wait_until='load')
            
            # 等待页面加载
            await self.page.wait_for_selector("body", timeout=self.wait_timeout)
            
            print("✅ 页面加载成功")
            await self.take_screenshot("login_page_loaded")
            return True
            
        except Exception as e:
            print(f"❌ 导航失败: {e}")
            return False
    
    
    # =================================================================
    #                       3. 登录表单处理模块
    # =================================================================
    
    async def find_login_form(self):
        """查找登录表单元素"""
        try:
            print("🔍 正在查找登录表单...")
            
            # 等待页面加载完成
            await asyncio.sleep(self.page_load_delay)
            
            # 查找邮箱输入框
            email_selector = "input[name='memberid']"
            await self.page.wait_for_selector(email_selector, timeout=self.wait_timeout)
            print("✅ 找到邮箱输入框")

            # 查找密码输入框
            password_selector = "input[name='user_password']"
            await self.page.wait_for_selector(password_selector, timeout=self.wait_timeout)
            print("✅ 找到密码输入框")

            # 查找登录按钮
            login_button_selector = "input[value='ログインする']"
            await self.page.wait_for_selector(login_button_selector, timeout=self.wait_timeout)
            print("✅ 找到登录按钮")
            
            return email_selector, password_selector, login_button_selector
            
        except Exception as e:
            print(f"❌ 查找登录表单时出错: {e}")
            return None, None, None
    
    async def human_type(self, selector, text):
        """模拟人类输入行为"""
        for char in text:
            await self.page.type(selector, char, delay=100)  # 100ms delay between characters
            await asyncio.sleep(0.05)  # Additional small delay
    
    async def perform_login(self):
        """执行登录操作"""
        try:
            print("🎯 开始执行登录操作...")
            
            # 查找登录表单元素
            email_selector, password_selector, login_button_selector = await self.find_login_form()
            
            if not email_selector or not password_selector:
                return False
            
            print("📝 正在填写登录信息...")
            
            # 模拟人类行为：慢速输入邮箱
            await self.page.fill(email_selector, "")  # 清空
            await self.human_type(email_selector, self.email)
            print("✅ 邮箱已填写")
            
            # 等待一下，模拟人类思考时间
            await asyncio.sleep(2)
            
            # 模拟人类行为：慢速输入密码
            await self.page.fill(password_selector, "")  # 清空
            await self.human_type(password_selector, self.password)
            print("✅ 密码已填写")
            
            # 等待一下，模拟人类操作
            await asyncio.sleep(2)
            
            # 提交表单
            if login_button_selector:
                print("🖱️ 点击登录按钮...")
                await self.page.click(login_button_selector)
            else:
                print("⌨️ 使用回车键提交...")
                await self.page.press(password_selector, "Enter")
            
            print("✅ 登录表单已提交")
            
            # 等待页面响应
            await asyncio.sleep(5)
            return True
            
        except Exception as e:
            print(f"❌ 登录操作失败: {e}")
            return False
    
    
    # =================================================================
    #                       4. 验证码处理模块
    # =================================================================
    
    async def handle_verification_page(self):
        """处理验证页面 - 检测是否需要验证"""
        try:
            print("🔍 检查是否需要验证...")
            await self.take_screenshot("checking_verification_page")
            
            # 等待页面稳定
            await asyncio.sleep(3)
            
            current_url = self.page.url
            print(f"📍 当前URL: {current_url}")
            
            # 检查是否跳转到验证页面
            if "loginauth/index" in current_url:
                print("🔐 检测到XServer新环境验证页面！")
                print("⚠️ 这是XServer的安全机制，检测到新环境登录")
                
                # 查找发送验证码按钮
                print("🔍 正在查找发送验证码按钮...")
                selector = "input[value*='送信']"
                
                try:
                    await self.page.wait_for_selector(selector, timeout=self.wait_timeout)
                    print("✅ 找到发送验证码按钮")
                    print("📧 点击发送验证码按钮，验证码将发送到您的邮箱")
                    await self.page.click(selector)
                    print("✅ 已点击发送验证码按钮")
                except Exception as e:
                    print(f"❌ 查找发送验证码按钮失败: {e}")
                    return False
                
                # 等待跳转到验证码输入页面
                await asyncio.sleep(5)
                return await self.handle_code_input_page()
            
            return True
            
        except Exception as e:
            print(f"❌ 处理验证页面时出错: {e}")
            return False
    
    async def handle_code_input_page(self):
        """处理验证码输入页面 - 自动获取并输入验证码"""
        try:
            print("🔍 检查是否跳转到验证码输入页面...")
            current_url = self.page.url
            print(f"📍 当前URL: {current_url}")
            
            if "loginauth/smssend" in current_url:
                print("✅ 成功跳转到验证码输入页面！")
                print("📧 验证码已发送到您的邮箱")
                
                # 查找验证码输入框
                print("🔍 正在查找验证码输入框...")
                code_input_selector = "input[id='auth_code'][name='auth_code']"
                
                try:
                    await self.page.wait_for_selector(code_input_selector, timeout=self.wait_timeout)
                    print("✅ 找到验证码输入框")
                    
                    # 自动从cloudmail API获取验证码
                    verification_code = await self.get_verification_code_from_cloudmail()
                    
                    if verification_code:
                        # 输入验证码并提交
                        return await self.input_verification_code(verification_code)
                    else:
                        print("❌ 自动获取验证码失败")
                        return False
                
                except Exception as e:
                    print(f"❌ 未找到验证码输入框: {e}")
                    return False
            else:
                print("⚠️ 未检测到验证码输入页面，可能已直接登录成功")
                return True
            
        except Exception as e:
            print(f"❌ 处理验证码输入页面时出错: {e}")
            return False
    
    async def input_verification_code(self, verification_code: str):
        """输入验证码并提交（供外部调用）"""
        try:
            print(f"🔑 正在输入验证码: {verification_code}")
            
            # 等待页面稳定
            await asyncio.sleep(2)
            
            # 查找验证码输入框
            code_input_selector = "input[id='auth_code'][name='auth_code']"
            
            # 清空并输入验证码
            await self.page.fill(code_input_selector, "")
            await asyncio.sleep(1)
            await self.human_type(code_input_selector, verification_code)
            print("✅ 验证码已输入")
            
            # 等待输入完成
            await asyncio.sleep(2)
            
            # 查找并点击登录按钮
            print("🔍 正在查找ログイン按钮...")
            login_submit_selector = "input[type='submit'][value='ログイン']"
            await self.page.wait_for_selector(login_submit_selector, timeout=self.wait_timeout)
            print("✅ 找到ログイン按钮")
            
            # 等待按钮可点击
            await asyncio.sleep(1)
            await self.page.click(login_submit_selector)
            print("✅ 验证码已提交")
            
            # 等待验证结果
            await asyncio.sleep(8)
            return True
            
        except Exception as e:
            print(f"❌ 输入验证码失败: {e}")
            await self.take_screenshot("verification_input_failed")
            return False
    
    async def get_verification_code_from_cloudmail(self):
        """从cloudmail API获取验证码"""
        try:
            print("📧 开始从cloudmail API获取验证码...")
            
            # 等待邮件发送（验证码邮件需要时间）
            print("⏰ 等待验证码邮件发送（15秒）...")
            await asyncio.sleep(15)
            
            # 步骤1：获取Token
            print("🔑 正在获取邮箱API Token...")
            token_result = self._get_mail_api_token()
            
            if token_result.get("code") != 200:
                print(f"❌ Token获取失败: {token_result.get('message')}")
                return None
            
            token = token_result.get("data", {}).get("token")
            print("✅ Token获取成功")
            
            # 步骤2：查询邮件列表
            print(f"📬 正在查询邮箱 {self.cloudmail_to_email} 的最新验证码邮件...")
            
            # 根据LOCAL_FILTER决定是否在API中过滤主题
            if self.cloudmail_local_filter:
                # 本地过滤：不传递主题到API，获取所有邮件后在本地过滤
                mail_result = self._get_mail_list(
                    token=token,
                    target_email=self.cloudmail_to_email,
                    sender_email=self.cloudmail_send_email,
                    subject=None
                )
            else:
                # API过滤：直接在API请求中过滤主题
                mail_result = self._get_mail_list(
                    token=token,
                    target_email=self.cloudmail_to_email,
                    sender_email=self.cloudmail_send_email,
                    subject=self.cloudmail_subject
                )
            
            if mail_result.get("code") != 200:
                print(f"❌ 邮件查询失败: {mail_result.get('message')}")
                return None
            
            # 步骤3：提取邮件列表
            data_content = mail_result.get("data", [])
            mail_list = data_content if isinstance(data_content, list) else data_content.get("list", [])
            
            if not mail_list:
                print("❌ 未找到邮件")
                return None
            
            # 步骤4：过滤XServer验证码邮件（精确匹配主题）
            xserver_mails = [
                mail for mail in mail_list 
                if mail.get('subject', '').strip() == self.cloudmail_subject
            ]
            
            if not xserver_mails:
                print(f"❌ 未找到主题为 '{self.cloudmail_subject}' 的邮件")
                return None
            
            # 步骤5：只保留最新的一封邮件
            latest_mail = [xserver_mails[0]]
            print(f"✅ 找到最新验证码邮件")
            
            # 步骤6：保存到JSON文件
            json_filename = self._save_mail_to_json(latest_mail)
            print(f"💾 邮件已保存到: {json_filename}")
            
            # 步骤7：从JSON文件读取并提取验证码
            verification_code = self._extract_code_from_json(json_filename)
            
            if verification_code:
                print(f"🎉 成功提取验证码: {verification_code}")
                return verification_code
            else:
                print("❌ 未能从邮件中提取验证码")
                return None
            
        except Exception as e:
            print(f"❌ 从cloudmail获取验证码失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_mail_api_token(self):
        """获取邮箱API Token"""
        url = f"{self.cloudmail_api_base_url}/api/public/genToken"
        headers = {"Authorization": self.cloudmail_jwt_secret}
        payload = {
            "email": self.cloudmail_email,
            "password": self.cloudmail_password
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            return {"code": -1, "message": str(e)}
    
    def _get_mail_list(self, token: str, target_email: str, sender_email: str = None, subject: str = None):
        """查询邮件列表"""
        url = f"{self.cloudmail_api_base_url}/api/public/emailList"
        headers = {"Authorization": token}
        
        payload = {
            "toEmail": target_email,
            "timeSort": "desc",
            "type": 0,
            "num": 1,
            "size": 20
        }
        
        # 添加发件人过滤
        if sender_email:
            payload["sendEmail"] = sender_email
        
        # 添加主题过滤（仅当不使用本地过滤时）
        if subject:
            payload["subject"] = subject
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            return {"code": -1, "message": str(e)}
    
    def _extract_verification_code(self, mail_content: str):
        """从邮件内容中提取验证码"""
        # 验证码匹配模式（格式：【認証コード】　　　　　　　： 88617）
        # 匹配【認証コード】后面跟任意数量的全角/半角空格，然后是冒号，再跟数字
        pattern = r'【認証コード】[\s　]+[：:]\s*(\d{4,8})'
        
        matches = re.findall(pattern, mail_content, re.IGNORECASE | re.MULTILINE)
        if matches:
            # 过滤有效的验证码（4-8位数字）
            valid_codes = [code for code in matches if 4 <= len(code) <= 8]
            if valid_codes:
                return valid_codes[0]
        
        # 如果没匹配到，打印调试信息
        print("❌ 未能匹配到验证码")
        print(f"📝 邮件内容长度: {len(mail_content)} 字符")
        # 尝试查找邮件中包含"認証コード"的行
        for line in mail_content.split('\n'):
            if '認証コード' in line:
                print(f"🔍 包含認証コード的行: {line}")
        
        return None
    
    def _save_mail_to_json(self, mail_list):
        """保存邮件到JSON文件"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"xserver_verification_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(mail_list, f, ensure_ascii=False, indent=2)
        
        return filename
    
    def _extract_code_from_json(self, json_filename):
        """从JSON文件中读取并提取验证码"""
        try:
            # 读取JSON文件
            with open(json_filename, 'r', encoding='utf-8') as f:
                mail_list = json.load(f)
            
            if not mail_list:
                print("❌ JSON文件中没有邮件数据")
                return None
            
            # 获取第一封邮件
            mail = mail_list[0]
            mail_subject = mail.get('subject', '')
            # 邮件内容在'text'字段中
            mail_content = mail.get('text', '') or mail.get('content', '')
            
            print(f"📧 邮件主题: {mail_subject}")
            print(f"📄 邮件内容长度: {len(mail_content)} 字符")
            
            if not mail_content:
                print("❌ 邮件内容为空")
                return None
            
            # 使用正则表达式提取验证码
            verification_code = self._extract_verification_code(mail_content)
            return verification_code
            
        except Exception as e:
            print(f"❌ 从JSON文件提取验证码失败: {e}")
            return None
    
    # =================================================================
    #                       5. 登录结果处理模块
    # =================================================================
    
    async def handle_login_result(self):
        """处理登录结果"""
        try:
            print("🔍 正在检查登录结果...")
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            current_url = self.page.url
            print(f"📍 当前URL: {current_url}")
            
            # 简单直接：只判断是否跳转到成功页面
            success_url = "https://secure.xserver.ne.jp/xapanel/xmgame/index"
            
            if current_url == success_url:
                print("✅ 登录成功！已跳转到XServer GAME管理页面")
                
                # 等待页面加载完成
                print("⏰ 等待页面加载完成...")
                await asyncio.sleep(3)
                
                # 查找并点击"ゲーム管理"按钮
                print("🔍 正在查找ゲーム管理按钮...")
                try:
                    game_button_selector = "a:has-text('ゲーム管理')"
                    await self.page.wait_for_selector(game_button_selector, timeout=self.wait_timeout)
                    print("✅ 找到ゲーム管理按钮")
                    
                    # 点击ゲーム管理按钮
                    print("🖱️ 正在点击ゲーム管理按钮...")
                    await self.page.click(game_button_selector)
                    print("✅ 已点击ゲーム管理按钮")
                    
                    # 等待页面跳转
                    await asyncio.sleep(5)
                    
                    # 验证是否跳转到游戏管理页面
                    final_url = self.page.url
                    print(f"📍 最终页面URL: {final_url}")
                    
                    expected_game_url = "https://secure.xserver.ne.jp/xmgame/game/index"
                    if expected_game_url in final_url:
                        print("✅ 成功点击ゲーム管理按钮并跳转到游戏管理页面")
                        await self.take_screenshot("game_page_loaded")
                        
                        # 获取服务器时间信息
                        await self.get_server_time_info()
                    else:
                        print(f"⚠️ 跳转到游戏页面可能失败")
                        print(f"   预期包含: {expected_game_url}")
                        print(f"   实际URL: {final_url}")
                        await self.take_screenshot("game_page_redirect_failed")
                        
                except Exception as e:
                    print(f"❌ 查找或点击ゲーム管理按钮时出错: {e}")
                    await self.take_screenshot("game_button_error")
                
                return True
            else:
                print(f"❌ 登录失败！当前URL不是预期的成功页面")
                print(f"   预期URL: {success_url}")
                print(f"   实际URL: {current_url}")
                return False
            
        except Exception as e:
            print(f"❌ 检查登录结果时出错: {e}")
            return False
            
    # =================================================================
    #                    6A. 服务器信息获取模块
    # =================================================================
    
    async def get_server_time_info(self):
        """获取服务器时间信息"""
        try:
            print("🕒 正在获取服务器时间信息...")
            
            # 等待页面加载完成
            await asyncio.sleep(3)
            
            # 使用已验证有效的选择器
            try:
                elements = await self.page.locator("text=/残り\\d+時間\\d+分/").all()
                
                for element in elements:
                    element_text = await element.text_content()
                    element_text = element_text.strip() if element_text else ""
                    
                    # 只处理包含时间信息且文本不太长的元素
                    if element_text and len(element_text) < 200 and "残り" in element_text and "時間" in element_text:
                        print(f"✅ 找到时间元素: {element_text}")
                        
                        # 提取剩余时间
                        remaining_match = re.search(r'残り(\d+時間\d+分)', element_text)
                        if remaining_match:
                            remaining_raw = remaining_match.group(1)
                            remaining_formatted = self.format_remaining_time(remaining_raw)
                            print(f"⏰ 剩余时间: {remaining_formatted}")
                        
                        # 提取到期时间
                        expiry_match = re.search(r'\((\d{4}-\d{2}-\d{2})まで\)', element_text)
                        if expiry_match:
                            expiry_raw = expiry_match.group(1)
                            expiry_formatted = self.format_expiry_date(expiry_raw)
                            print(f"📅 到期时间: {expiry_formatted}")
                            # 记录原到期时间
                            self.old_expiry_time = expiry_formatted
                        
                        break
                        
            except Exception as e:
                print(f"❌ 获取时间信息时出错: {e}")
            
            # 点击升级按钮
            await self.click_upgrade_button()
            
        except Exception as e:
            print(f"❌ 获取服务器时间信息失败: {e}")
    
    def format_remaining_time(self, time_str):
        """格式化剩余时间"""
        # 移除"残り"前缀，只保留时间部分
        return time_str  # 例如: "30時間57分"
    
    def format_expiry_date(self, date_str):
        """格式化到期时间"""
        # 直接返回日期，移除括号和"まで"
        return date_str  # 例如: "2025-09-24"
    
    # =================================================================
    #                    6B. 续期页面导航模块
    # =================================================================
    
    async def click_upgrade_button(self):
        """点击升级延长按钮"""
        try:
            print("🔄 正在查找アップグレード・期限延長按钮...")
            
            upgrade_selector = "a:has-text('アップグレード・期限延長')"
            await self.page.wait_for_selector(upgrade_selector, timeout=self.wait_timeout)
            print("✅ 找到アップグレード・期限延長按钮")
            
            # 点击按钮
            await self.page.click(upgrade_selector)
            print("✅ 已点击アップグレード・期限延長按钮")
            
            # 等待页面跳转
            await asyncio.sleep(5)
            
            # 验证URL和检查限制信息
            await self.verify_upgrade_page()
            
        except Exception as e:
            print(f"❌ 点击升级按钮失败: {e}")
    
    async def verify_upgrade_page(self):
        """验证升级页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/index"
            
            print(f"📍 升级页面URL: {current_url}")
            
            if expected_url in current_url:
                print("✅ 成功跳转到升级页面")
                
                # 检查延长限制信息
                await self.check_extension_restriction()
            else:
                print(f"❌ 升级页面跳转失败")
                print(f"   预期URL: {expected_url}")
                print(f"   实际URL: {current_url}")
                
        except Exception as e:
            print(f"❌ 验证升级页面失败: {e}")
    
    async def check_extension_restriction(self):
        """检查期限延长限制信息"""
        try:
            print("🔍 正在检测期限延长限制提示...")
            
            # 查找限制信息
            restriction_selector = "text=/残り契約時間が24時間を切るまで、期限の延長は行えません/"
            
            try:
                element = await self.page.wait_for_selector(restriction_selector, timeout=5000)
                restriction_text = await element.text_content()
                print(f"✅ 找到期限延长限制信息")
                print(f"📝 限制信息: {restriction_text}")
                # 设置状态为未到期
                self.renewal_status = "Unexpired"
                return True  # 有限制，不能续期
                
            except Exception:
                print("ℹ️ 未找到期限延长限制信息，可以进行延长操作")
                # 没有限制信息，执行续期操作
                await self.perform_extension_operation()
                return False  # 无限制，可以续期
                
        except Exception as e:
            print(f"❌ 检测期限延长限制失败: {e}")
            return True  # 出错时默认认为有限制
    
    # =================================================================
    #                    6C. 续期操作执行模块
    # =================================================================
    
    async def perform_extension_operation(self):
        """执行期限延长操作"""
        try:
            print("🔄 开始执行期限延长操作...")
            
            # 查找"期限を延長する"按钮
            await self.click_extension_button()
            
        except Exception as e:
            print(f"❌ 执行期限延长操作失败: {e}")
    
    async def click_extension_button(self):
        """点击期限延长按钮"""
        try:
            print("🔍 正在查找'期限を延長する'按钮...")
            
            # 使用有效的选择器
            extension_selector = "a:has-text('期限を延長する')"
            
            # 等待并点击按钮
            await self.page.wait_for_selector(extension_selector, timeout=self.wait_timeout)
            print("✅ 找到'期限を延長する'按钮")
            
            # 点击按钮
            await self.page.click(extension_selector)
            print("✅ 已点击'期限を延長する'按钮")
            
            # 等待页面跳转
            print("⏰ 等待页面跳转...")
            await asyncio.sleep(5)
            
            # 验证是否跳转到input页面
            await self.verify_extension_input_page()
            return True
            
        except Exception as e:
            print(f"❌ 点击期限延长按钮失败: {e}")
            return False
    
    async def verify_extension_input_page(self):
        """验证是否成功跳转到期限延长输入页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/input"
            
            print(f"📍 当前页面URL: {current_url}")
            
            if expected_url in current_url:
                print("🎉 成功跳转到期限延长输入页面！")
                await self.take_screenshot("extension_input_page")
                
                # 继续执行确认操作
                await self.click_confirmation_button()
                return True
            else:
                print(f"❌ 页面跳转失败")
                print(f"   预期URL: {expected_url}")
                print(f"   实际URL: {current_url}")
                return False
            
        except Exception as e:
            print(f"❌ 验证期限延长输入页面失败: {e}")
            return False
            
    async def click_confirmation_button(self):
        """点击確認画面に進む按钮"""
        try:
            print("🔍 正在查找'確認画面に進む'按钮...")
            
            # 使用button元素的选择器
            confirmation_selector = "button[type='submit']:has-text('確認画面に進む')"
            
            # 等待并点击按钮
            await self.page.wait_for_selector(confirmation_selector, timeout=self.wait_timeout)
            print("✅ 找到'確認画面に進む'按钮")
            
            # 点击按钮
            await self.page.click(confirmation_selector)
            print("✅ 已点击'確認画面に進む'按钮")
            
            # 等待页面跳转
            print("⏰ 等待页面跳转...")
            await asyncio.sleep(5)
            
            # 验证是否跳转到conf页面
            await self.verify_extension_conf_page()
            return True
            
        except Exception as e:
            print(f"❌ 点击確認画面に進む按钮失败: {e}")
            return False
            
    async def verify_extension_conf_page(self):
        """验证是否成功跳转到期限延长确认页面"""
        try:
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/conf"
            
            print(f"📍 当前页面URL: {current_url}")
            
            if expected_url in current_url:
                print("🎉 成功跳转到期限延长确认页面！")
                await self.take_screenshot("extension_conf_page")
                
                # 记录续期后的时间信息
                await self.record_extension_time()
                
                # 查找期限延长按钮
                await self.find_final_extension_button()
                
                return True
            else:
                print(f"❌ 页面跳转失败")
                print(f"   预期URL: {expected_url}")
                print(f"   实际URL: {current_url}")
                return False
            
        except Exception as e:
            print(f"❌ 验证期限延长确认页面失败: {e}")
            return False
    
    async def record_extension_time(self):
        """记录续期后的时间信息"""
        try:
            print("📅 正在获取续期后的时间信息...")
            
            # 使用有效的选择器
            time_selector = "tr:has(th:has-text('延長後の期限'))"
            
            # 等待并获取时间信息
            time_element = await self.page.wait_for_selector(time_selector, timeout=self.wait_timeout)
            print("✅ 找到续期后时间信息")
            
            # 获取整行，然后提取td内容
            td_element = await time_element.query_selector("td")
            if td_element:
                extension_time = await td_element.text_content()
                extension_time = extension_time.strip()
                print(f"📅 续期后的期限: {extension_time}")
                # 记录新到期时间
                self.new_expiry_time = extension_time
            else:
                print("❌ 未找到时间内容")
            
        except Exception as e:
            print(f"❌ 记录续期后时间失败: {e}")
    
    async def find_final_extension_button(self):
        """查找并点击最终的期限延长按钮"""
        try:
            print("🔍 正在查找最终的'期限を延長する'按钮...")
            
            # 基于HTML属性查找按钮
            final_button_selector = "button[type='submit']:has-text('期限を延長する')"
            
            # 等待按钮出现
            await self.page.wait_for_selector(final_button_selector, timeout=self.wait_timeout)
            print("✅ 找到最终的'期限を延長する'按钮")
            
            # 点击按钮执行最终续期
            await self.page.click(final_button_selector)
            print("✅ 已点击最终续期按钮")
            
            # 等待页面跳转
            print("⏰ 等待续期操作完成...")
            await asyncio.sleep(5)
            
            # 验证续期结果
            await self.verify_extension_success()
            
            return True
            
        except Exception as e:
            print(f"❌ 执行最终期限延长操作失败: {e}")
            return False
            
    async def verify_extension_success(self):
        """验证续期操作是否成功"""
        try:
            print("🔍 正在验证续期操作结果...")
            
            current_url = self.page.url
            expected_url = "https://secure.xserver.ne.jp/xmgame/game/freeplan/extend/do"
            
            print(f"📍 当前页面URL: {current_url}")
            
            # 检查条件1：URL是否跳转到do页面
            url_success = expected_url in current_url
            
            # 检查条件2：是否有成功提示文字
            text_success = False
            try:
                success_text_selector = "p:has-text('期限を延長しました。')"
                await self.page.wait_for_selector(success_text_selector, timeout=5000)
                success_text = await self.page.query_selector(success_text_selector)
                if success_text:
                    text_content = await success_text.text_content()
                    print(f"✅ 找到成功提示文字: {text_content.strip()}")
                    text_success = True
            except Exception:
                print("ℹ️ 未找到成功提示文字")
            
            # 任意一项满足即为成功
            if url_success or text_success:
                print("🎉 续期操作成功！")
                if url_success:
                    print(f"✅ URL验证成功: {current_url}")
                if text_success:
                    print("✅ 成功提示文字验证成功")
                
                # 设置状态为成功
                self.renewal_status = "Success"
                await self.take_screenshot("extension_success")
                return True
            else:
                print("❌ 续期操作可能失败")
                print(f"   当前URL: {current_url}")
                print(f"   期望URL: {expected_url}")
                # 设置状态为失败
                self.renewal_status = "Failed"
                await self.take_screenshot("extension_failed")
                return False
            
        except Exception as e:
            print(f"❌ 验证续期结果失败: {e}")
            # 设置状态为失败
            self.renewal_status = "Failed"
            return False
        
    # =================================================================
    #                    6D. 结果记录与报告模块
    # =================================================================
    
    def generate_readme(self):
        """生成README.md文件记录续期情况"""
        try:
            print("📝 正在生成README.md文件...")
            
            # 获取当前时间
            # 使用北京时间（UTC+8）
            beijing_time = datetime.datetime.now(timezone(timedelta(hours=8)))
            current_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 根据状态生成不同的内容
            readme_content = f"**最后运行时间**: `{current_time}`\n\n"
            readme_content += "**运行结果**: <br>\n"
            readme_content += "🖥️服务器：`🇯🇵Xserver(Mc)`<br>\n"
            
            # 根据续期状态生成对应的结果
            if self.renewal_status == "Success":
                readme_content += "📊续期结果：✅Success<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
                readme_content += f"🕡️新到期时间: `{self.new_expiry_time or 'Unknown'}`<br>\n"
            elif self.renewal_status == "Unexpired":
                readme_content += "📊续期结果：ℹ️Unexpired<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            elif self.renewal_status == "Failed":
                readme_content += "📊续期结果：❌Failed<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            else:
                readme_content += "📊续期结果：❓Unknown<br>\n"
                readme_content += f"🕛️旧到期时间: `{self.old_expiry_time or 'Unknown'}`<br>\n"
            
            # 写入README.md文件
            with open("README.md", "w", encoding="utf-8") as f:
                f.write(readme_content)
            
            print("✅ README.md文件生成成功")
            print(f"📄 续期状态: {self.renewal_status}")
            print(f"📅 原到期时间: {self.old_expiry_time or 'Unknown'}")
            if self.new_expiry_time:
                print(f"📅 新到期时间: {self.new_expiry_time}")
            
        except Exception as e:
            print(f"❌ 生成README.md文件失败: {e}")
    
    # =================================================================
    #                       7. 主流程控制模块
    # =================================================================
    
    async def run(self):
        """运行自动登录流程"""
        try:
            print("🚀 开始 XServer GAME 自动登录流程...")
            
            # 步骤1：验证配置
            if not self.validate_config():
                return False
            
            # 步骤2：设置浏览器
            if not await self.setup_browser():
                return False
            
            # 步骤3：导航到登录页面
            if not await self.navigate_to_login():
                return False
            
            # 步骤4：执行登录操作
            if not await self.perform_login():
                return False
            
            # 步骤5：检查是否需要验证
            verification_result = await self.handle_verification_page()
            if verification_result:
                print("✅ 验证流程已处理")
                await asyncio.sleep(3)  # 等待验证完成后的页面跳转
            else:
                print("⚠️ 验证流程未完成，可能需要手动处理")
            
            # 步骤6：检查登录结果
            if not await self.handle_login_result():
                print("⚠️ 登录可能失败，请检查邮箱和密码是否正确")
                return False
            
            print("🎉 XServer GAME 自动登录流程完成！")
            await self.take_screenshot("login_completed")
            
            # 生成README.md文件
            self.generate_readme()
            
            # 保持浏览器打开一段时间以便查看结果
            print("⏰ 浏览器将在 10 秒后关闭...")
            await asyncio.sleep(10)
            
            return True
            
        except Exception as e:
            print(f"❌ 自动登录流程出错: {e}")
            # 即使出错也生成README文件
            self.generate_readme()
            return False
    
        finally:
            await self.cleanup()


# =====================================================================
#                          主程序入口
# =====================================================================

async def main():
    """主函数"""
    print("=" * 60)
    print("XServer GAME 自动登录脚本 - Playwright版本")
    print("基于 Playwright + stealth")
    print("=" * 60)
    print()
    
    # 显示当前配置
    print("📋 当前配置:")
    print(f"   XServer邮箱: {LOGIN_EMAIL}")
    print(f"   XServer密码: {'*' * len(LOGIN_PASSWORD)}")
    print(f"   目标网站: {TARGET_URL}")
    print(f"   无头模式: {USE_HEADLESS}")
    print()
    
    # 显示邮箱配置
    if CLOUD_MAIL_CONFIG:
        is_github = os.getenv("GITHUB_ACTIONS") == "true"
        if is_github:
            print("📧 邮箱API配置 (从 CLOUD_MAIL 环境变量):")
        else:
            print("📧 邮箱API配置 (从 CLOUD_MAIL.json 文件):")
        
        print(f"   API地址: {CLOUDMAIL_API_BASE_URL}")
        print(f"   登录邮箱: {CLOUDMAIL_EMAIL}")
        print(f"   目标邮箱: {CLOUDMAIL_TO_EMAIL}")
        print(f"   发件人: {CLOUDMAIL_SEND_EMAIL}")
        if CLOUDMAIL_JWT_SECRET and len(CLOUDMAIL_JWT_SECRET) > 8:
            print(f"   JWT密钥: {CLOUDMAIL_JWT_SECRET[:8]}{'*' * (len(CLOUDMAIL_JWT_SECRET) - 8)}")
        elif CLOUDMAIL_JWT_SECRET:
            print(f"   JWT密钥: {'*' * len(CLOUDMAIL_JWT_SECRET)}")
    else:
        print("⚠️ 邮箱API配置未加载，验证码功能不可用")
    print()
    
    # 确认配置
    if LOGIN_EMAIL == "your_email@example.com" or LOGIN_PASSWORD == "your_password":
        print("❌ 请先在代码开头的配置区域设置正确的邮箱和密码！")
        return
    
    print("🚀 配置验证通过，自动开始登录...")
    
    # 创建并运行自动登录器
    auto_login = XServerAutoLogin()
    
    success = await auto_login.run()
    
    if success:
        print("✅ 登录流程执行成功！")
        exit(0)
    else:
        print("❌ 登录流程执行失败！")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
