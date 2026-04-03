"""
    ld模拟器使用appium实现自动化开googlepay会员
"""
import re
import os
import time
import yaml
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from loguru import logger
from appium import webdriver
from dataclasses import dataclass
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# 配置数据库和路径
music_db = ''
base_path = Path(__file__).parent.parent.parent
prepare_file_path = ''
address_yaml_path = ''
addresses = yaml.load(open(address_yaml_path, encoding='utf8'), Loader=yaml.FullLoader)

# 配置日志文件
log_dir = ''
log_fpath = os.path.join(log_dir, f'start_apple_premium_{datetime.now().strftime("%Y-%m-%d")}.log')
logger.add(log_fpath, rotation='1 day', retention='7 days', level='INFO')


class LdDeviceError(Exception):
    """模拟器操作异常基类"""

    def __init__(self, message, username=None):
        self.message = message
        self.gmail_username = username
        super().__init__(self.message)


class LdDeviceStartError(LdDeviceError):
    """模拟器启动失败"""
    pass


class AppiumStartError(LdDeviceError):
    """Appium链接失败"""
    pass


class LdDeviceQuitError(LdDeviceError):
    """模拟器关闭失败"""
    pass


class GmailAccountError(LdDeviceError):
    """Gmail账号不可用"""
    pass


class GmailPhoneError(LdDeviceError):
    """Gmail需要手机验证"""
    pass


class LoginGmailError(LdDeviceError):
    """Gmail账号登录失败"""
    pass


class AccountInfoError(LdDeviceError):
    """账号信息错误"""
    pass


class InstallAppError(LdDeviceError):
    """下载失败"""
    pass


class SetProxyError(LdDeviceError):
    """设置代理发生错误"""
    pass


class UnlockDeviceError(LdDeviceError):
    """设置代理发生错误"""
    pass


class StartPremiumError(LdDeviceError):
    """开会员发生错误"""
    pass


@dataclass
class LdAppLocators:
    lock_btn = (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="Unlock"]')
    system_app = (
        AppiumBy.XPATH,
        '//android.widget.FrameLayout[@content-desc="Folder: 系统应用" or @content-desc="Folder: System Apps"]'
    )
    net_internet = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.LinearLayout").instance(4)')
    account_btn = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.LinearLayout").instance(12)')
    wifi_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.RelativeLayout").instance(0)')
    modify_btn = (AppiumBy.ACCESSIBILITY_ID, 'Modify')
    hostname_input = (AppiumBy.ID, 'com.android.settings:id/proxy_hostname')
    port_input = (AppiumBy.ID, 'com.android.settings:id/proxy_port')
    proxy_save_btn = (AppiumBy.ID, 'android:id/button1')
    proxy_select = (AppiumBy.ID, 'android:id/text1')
    manual_option = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Manual")')
    play_store_app = (AppiumBy.ACCESSIBILITY_ID, 'Play Store')
    veritry_next_btn = (AppiumBy.CLASS_NAME, 'android.widget.Button')
    robot_ele = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Confirm you’re not a robot")')
    input_ele = (AppiumBy.CLASS_NAME, 'android.widget.EditText')
    next_button = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Next")')
    confirm_email = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Confirm your recovery email")')
    confirm_email_input = (AppiumBy.CLASS_NAME, 'android.widget.EditText')
    gmail_login_succ = (  # new UiSelector().resourceId("com.android.vending:id/0_resource_name_obfuscated")
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().resourceId("com.android.vending:id/0_resource_name_obfuscated")')
    search_input = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.EditText")')
    install_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Install")')
    gmail_account = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.LinearLayout").instance(9)')
    remove_btn = (AppiumBy.ID, 'com.android.settings:id/button')
    confirm_remove = (AppiumBy.ID, 'android:id/button1')
    add_account_btn = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.RelativeLayout").instance(0)')
    choose_google_ele = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Personal (IMAP)")')
    choose_google = (AppiumBy.ANDROID_UIAUTOMATOR,
                     'new UiSelector().className("android.widget.RelativeLayout").instance(1)')
    skip_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Skip")')
    agree_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("I agree")')
    more_btn = (AppiumBy.CLASS_NAME, 'android.widget.Button')
    confirm_phone = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Confirm your recovery phone number")')
    apple_continue = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().resourceId("com.apple.android.music:id/signin_continue_button")')
    do_not_send = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("DON\'T SEND")')
    more_option = (AppiumBy.ACCESSIBILITY_ID, 'More options')
    setting = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Settings")')
    apple_account = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Account")')
    apple_login = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.LinearLayout").instance(5)')
    apple_username_input = (AppiumBy.ID, 'com.apple.android.music:id/signin_id')
    apple_password_input = (AppiumBy.ID, 'com.apple.android.music:id/signin_password')
    appel_login_continue = (AppiumBy.ID, 'com.apple.android.music:id/signin_continue_button')
    theme_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Theme")')
    navigate_up = (AppiumBy.ACCESSIBILITY_ID, 'Navigate up')
    subscribe_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Subscribe Now")')
    start_subscribe = (
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceId("com.apple.android.music:id/offer_btn")')
    street_address_locator = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Street address")')
    complete_account_locator = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Complete account setup")')
    complete_continue = (AppiumBy.XPATH, '//android.widget.Button[@resource-id="com.android.vending:id/0_resource_name_obfuscated"]')

class AppiumldAuto:
    LDPLAYER9_DIR = r"D:\leidian\LDPlayer9"
    appium_server_url = 'http://localhost:4723'
    ADB_DEVICE_PATTERN = re.compile(r"emulator-\d+\s+device")  # 匹配emulator-xxxx device的正则
    ADB_DEVICE_TIMEOUT = 120
    ADB_CHECK_INTERVAL = 5
    capabilities = dict(
        platformName='Android',
        automationName='uiautomator2',
        deviceName='Android',
        language='en',
        locale='US',
        noReset=True
    )

    def __init__(self, gmail_username, apple_username, code=None, mode=None, accspy=None) -> None:
        self.udid = ''
        self.gmail_username = gmail_username
        self.apple_username = apple_username
        self.code = code
        self.accspy = accspy
        # 初始化账号信息
        self._load_account_info()
        # 启动模拟器、初始化 Appium 驱动
        if mode != 'create':
            # 配置模拟器设置
            self.modify_emulator(
                username=self.gmail_username,
                resolution='1080,1920,480',
                cpu=2,
                memory=2048
            )
            self.start_device()
            self.driver = self.start_driver()

    def _load_account_info(self):
        """在初始化时加载账号信息"""
        # 初始化账号信息存储
        self.youtube_info = {
            'password': '',
            'confirm_email': '',
            'proxy_str': '',
            'port': None
        }

        self.apple_info = {
            'password': '',
            'proxy_str': '',
            'port': None
        }

        # 加载YouTube账号信息
        if self.gmail_username:
            try:
                acc_info = music_db.accounts_v2.find_one({
                    'dsp.name': {"$in":['youtube_channel', 'youtube_video', 'youtube']},
                    'username': {
                        '$regex': f'^{self.gmail_username.lower()}$',  # ^和$确保完全匹配（避免部分匹配）
                        '$options': 'i'  # i = ignore case，忽略大小写
                    }
                })
                if acc_info:
                    self.youtube_info.update({
                        'password': acc_info.get('password', ''),
                        'confirm_email': acc_info.get('dsp', {}).get('help', ''),
                        'proxy_str': acc_info.get('identity', {}).get('proxy', '')
                    })
                    self._load_proxy_port('youtube')
                else:
                    logger.warning(f"未找到YouTube账号信息: {self.gmail_username}")
            except Exception as e:
                logger.error(f"加载YouTube账号信息失败: {e}")

        # 加载Apple账号信息
        if self.apple_username:
            try:
                acc_info = music_db.accounts_v2.find_one({'dsp.name': 'apple', 'username': self.apple_username})
                if acc_info:
                    self.apple_info.update({
                        'password': acc_info.get('password', ''),
                        'proxy_str': acc_info.get('identity', {}).get('proxy', '')
                    })
                    self._load_proxy_port('apple')
                else:
                    logger.warning(f"未找到Apple账号信息: {self.apple_username}")
            except Exception as e:
                logger.error(f"加载Apple账号信息失败: {e}")

    def _load_proxy_port(self, platform):
        """加载指定平台的代理端口"""
        if platform == 'youtube':
            proxy_str = self.youtube_info['proxy_str']
        elif platform == 'apple':
            proxy_str = self.apple_info['proxy_str']
        else:
            return

        if proxy_str:
            try:
                proxy_docs = list(music_db.proxy.find({"proxy": proxy_str.strip()}))
                if proxy_docs:
                    port = proxy_docs[0]['tdm_port']
                    if platform == 'youtube':
                        self.youtube_info['port'] = port
                    else:  # apple
                        self.apple_info['port'] = port
                else:
                    logger.error(f"未找到{proxy_str}的代理端口映射")
            except Exception as e:
                logger.error(f"获取{platform}代理端口失败: {e}")

    def start_driver(self):
        try:
            logger.info(f"开始启动Appium驱动，目标设备UDID: {self.udid}")
            # 自动设置UDID到capabilities
            self.capabilities.update({
                'udid': self.udid,
                'androidDeviceReadyTimeout': 240,
                'adbExecTimeout': 120000,
                'newCommandTimeout': 120,
                'ignoreHiddenApiPolicyError': True,  # 忽略隐藏API配置错误
                'disableHiddenApiPolicy': False,  # 禁止自动执行隐藏API禁用命令
                'skipDeviceInitialization': False  # 保留基础设备初始化（仅禁隐藏API）
            })
            driver = webdriver.Remote(self.appium_server_url,
                                      options=UiAutomator2Options().load_capabilities(self.capabilities))
            logger.info(f"启动Appium驱动成功")
            return driver
        except Exception as e:
            logger.error(f"Appium启动失败: {e}")
            raise AppiumStartError(f"Appium启动失败: {e}")

    def create_emulator(self, username=None):
        """创建新的模拟器实例

        Args:
            username: 模拟器名称，默认使用 gmail_username

        Returns:
            bool: 创建是否成功
        """
        name = username or self.gmail_username
        try:
            logger.info(f"开始创建模拟器: {name}")

            # 先检查模拟器是否已存在
            if self._check_emulator_exists(name):
                logger.info(f"模拟器 {name} 已存在，跳过创建")
                return True

            result = subprocess.run(
                f'dnconsole.exe add --name "{name}"',
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")

            # 等待一下让模拟器创建完成
            time.sleep(3)

            # 最可靠的检查方式：再次检查模拟器是否存在于列表中
            if self._check_emulator_exists(name):
                logger.info(f"模拟器 {name} 创建成功")
                return True

            # 如果上面没找到，再检查命令输出中是否有明显的成功标识
            stdout_lower = (result.stdout or "").lower()
            # add命令成功时可能返回空或者包含一些信息
            # 只要没有明显的错误标识，就认为是成功
            stderr_lower = (result.stderr or "").lower()
            critical_errors = ["error", "failed", "cannot", "不支持"]

            # 如果stderr中有严重错误关键词，且模拟器未创建成功，才判定为失败
            if any(kw in stderr_lower for kw in critical_errors):
                if not self._check_emulator_exists(name):
                    logger.error(f"模拟器创建失败: {result.stderr}")
                    return False

            # 如果命令执行完成（没超时）且模拟器存在，认为成功
            logger.info(f"模拟器 {name} 创建成功")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"创建模拟器 {name} 命令超时")
            return False
        except Exception as e:
            logger.error(f"创建模拟器 {name} 时发生错误: {e}")
            return False

    def delete_emulator(self, username=None):
        """删除模拟器实例

        Args:
            username: 模拟器名称，默认使用 gmail_username

        Returns:
            bool: 删除是否成功
        """
        name = username or self.gmail_username
        try:
            logger.info(f"开始删除模拟器: {name}")

            # 先检查模拟器是否已存在
            if not self._check_emulator_exists(name):
                logger.info(f"模拟器 {name} 已存在，跳过创建")
                return True

            result = subprocess.run(
                f'dnconsole.exe remove --name "{name}"',
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")

            # 等待一下让模拟器创建完成
            time.sleep(3)

            # 最可靠的检查方式：再次检查模拟器是否存在于列表中
            if not self._check_emulator_exists(name):
                logger.info(f"模拟器 {name} 删除成功")
                return True

        except subprocess.TimeoutExpired:
            logger.error(f"删除模拟器 {name} 命令超时")
            return False
        except Exception as e:
            logger.error(f"删除模拟器 {name} 时发生错误: {e}")
            return False

    def _check_emulator_exists(self, name):
        """检查模拟器是否已存在

        Args:
            name: 模拟器名称

        Returns:
            bool: 是否存在
        """
        try:
            result = subprocess.run(
                'dnconsole.exe list2',
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.stdout:
                # list2 返回格式: 索引,标题,顶层窗口句柄,绑定窗口句柄,是否进入android,进程PID,VBox进程PID
                for line in result.stdout.strip().split('\n'):
                    if name in line:
                        logger.info(f"找到已存在的模拟器: {name}")
                        return True

            return False
        except Exception as e:
            logger.warning(f"检查模拟器是否存在时出错: {e}")
            return False

    def modify_emulator(self, username=None, resolution=None, cpu=None, memory=None):
        """修改模拟器属性

        Args:
            username: 模拟器名称，默认使用 gmail_username
            resolution: 分辨率，格式 '宽,高,DPI'，如 '1080,1920,480'
            cpu: CPU核心数，值为 1, 2, 3, 4
            memory: 内存大小，值为 512, 1024, 2048, 4096, 8192

        Returns:
            bool: 修改是否成功
        """
        name = username or self.gmail_username
        try:
            logger.info(f"开始修改模拟器属性: {name}")

            # 构建修改参数
            cmd_parts = [f'dnconsole.exe modify --name "{name}" --root 0']

            if resolution:
                cmd_parts.append(f"--resolution {resolution}")

            if cpu:
                cmd_parts.append(f"--cpu {cpu}")

            if memory:
                cmd_parts.append(f"--memory {memory}")

            # 添加 imei auto 随机生成
            cmd_parts.append("--imei auto")

            cmd = ' '.join(cmd_parts)
            logger.info(f"执行命令: {cmd}")

            result = subprocess.run(
                cmd,
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")

            # 检查是否修改成功
            stderr_lower = (result.stderr or "").lower()
            error_keywords = ["error", "失败", "failed", "not found", "不存在", "cannot"]

            if result.returncode != 0 or any(kw in stderr_lower for kw in error_keywords):
                logger.error(f"模拟器属性修改失败: {result.stderr}")
                return False

            logger.info(f"模拟器 {name} 属性修改成功")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"修改模拟器 {name} 属性命令超时")
            return False
        except Exception as e:
            logger.error(f"修改模拟器 {name} 属性时发生错误: {e}")
            return False

    def set_proxy_cmd(self, port):
        try:
            logger.info(f"开始设置代理: {port}")
            adb_cmd = f'adb -s {self.udid} shell settings put global http_proxy 10.200.10.209:{port}'
            result = subprocess.run(adb_cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")

            if result.returncode != 0:
                logger.error(f"设置代理失败，退出码: {result.returncode}")
                return False

            # 验证代理是否设置成功
            if not self._verify_proxy_cmd(port):
                logger.error("代理验证失败")
                return False

            return True
        except Exception as e:
            logger.error(f'设置代理时发生错误: {e}')
            raise SetProxyError(f'设置代理时发生错误: {e}')

    def _verify_proxy_cmd(self, port):
        """验证代理是否设置成功"""
        try:
            expected_proxy = f"10.200.10.209:{port}"
            verify_cmd = f'adb -s {self.udid} shell settings get global http_proxy'
            result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=10)
            current_proxy = result.stdout.strip()

            if current_proxy == expected_proxy:
                logger.info(f"代理验证成功: {current_proxy}")
                return True
            else:
                logger.warning(f"代理验证失败，当前代理: {current_proxy}, 预期: {expected_proxy}")
                return False
        except Exception as e:
            logger.error(f"验证代理时发生错误: {e}")
            return False

    def start_device(self):
        try:
            logger.info(f"正在启动模拟器: {self.gmail_username}")

            base_adb_devices = self._get_adb_devices()
            logger.info(f"模拟器启动前，ADB已存在设备: {base_adb_devices if base_adb_devices else '空'}")

            result = subprocess.run(
                f'dnconsole.exe launch --name "{self.gmail_username}"',
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                check=False,  # 不抛出异常，因为退出码不可靠
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(30)
            # 输出命令的输出信息
            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")
                # 只在stderr包含错误关键词时才抛出异常
                error_keywords = ["error", "失败", "failed", "not found", "不存在", "cannot"]
                stderr_lower = result.stderr.lower()
                if any(error_kw in stderr_lower for error_kw in error_keywords):
                    raise LdDeviceStartError(f"模拟器启动失败: {result.stderr}")

            # 检查模拟器是否打开成功 → 递进检测：进程存在 → ADB就绪
            logger.info(f"开始验证模拟器[{self.gmail_username}]是否就绪...")
            if not self._check_emulator_process():
                logger.error("模拟器进程检测失败，启动失败")
                raise LdDeviceStartError("模拟器启动失败：未检测到dnplayer.exe进程")

            # 等待ADB新增设备，获取目标UDID
            target_udid = self._wait_for_new_adb_device(base_adb_devices)
            if not target_udid:
                raise LdDeviceStartError(
                    f"模拟器[{self.gmail_username}]ADB设备匹配失败，超时{self.ADB_DEVICE_TIMEOUT}秒")

            self.udid = target_udid
            logger.info(f"模拟器[{self.gmail_username}]启动成功，ADB设备标识: {self.udid}")
            return True
        except LdDeviceStartError as e:
            logger.error(f"模拟器启动失败: {e}")
            raise

    def _check_emulator_process(self):
        """通过检查进程来验证模拟器是否运行"""
        try:
            logger.info("通过进程检查模拟器状态...")
            # 检查 LDPlayer 相关进程
            process_name = 'dnplayer.exe'

            try:
                result = subprocess.run(
                    f'tasklist /FI "IMAGENAME eq {process_name}" /NH',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if process_name in result.stdout:
                    logger.info(f"检测到 {process_name} 进程正在运行")
                    logger.debug(f"进程详情: {result.stdout.strip()}")
                    # 只要进程存在，就认为模拟器正在运行
                    logger.info(f"模拟器 '{self.gmail_username}' 状态: 运行中 (检测到 {process_name})")
                    return True
            except subprocess.TimeoutExpired:
                logger.warning(f"检查 {process_name} 进程超时")

            except Exception as e:
                logger.warning(f"检查 {process_name} 进程时出错: {e}")

            logger.warning("未检测到正在运行的模拟器进程")
            return False
        except Exception as e:
            logger.error(f"进程检查时发生错误: {e}")
            return False

    def _get_adb_devices(self):
        """
        获取当前ADB识别的所有设备，返回「设备标识列表」（如[emulator-6174, emulator-5554]）
        过滤状态为device的设备，仅保留有效标识
        """
        try:
            # 先执行adb devices刷新列表，避免缓存
            subprocess.run(
                "adb devices",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8"
            )
            # 再次执行，获取最新结果
            result = subprocess.run(
                "adb devices",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8"
            )
            # 用正则匹配所有emulator-xxxx device的行，提取设备标识
            devices = self.ADB_DEVICE_PATTERN.findall(result.stdout)
            # 提取纯设备标识（去掉后面的device），去重
            device_ids = [re.search(r"emulator-\d+", d).group() for d in devices if re.search(r"emulator-\d+", d)]
            return list(set(device_ids))
        except Exception as e:
            logger.warning(f"获取ADB设备列表失败: {str(e)[:50]}")
            return []

    def _wait_for_new_adb_device(self, base_devices):
        """
        等待新增的ADB设备（对比启动前的基础设备列表）
        base_devices: 启动前的ADB设备列表
        返回：新增的设备标识（如emulator-6174），超时返回None
        """
        logger.info(f"开始监控ADB新增设备，基础设备列表: {base_devices if base_devices else '空'}")
        start_time = time.time()
        stable_check_count = 0  # 设备稳定检测计数器，连续3次存在则确认
        target_device = None  # 临时保存疑似新增设备

        while time.time() - start_time < self.ADB_DEVICE_TIMEOUT:
            current_devices = self._get_adb_devices()
            # 计算新增设备：当前列表 - 基础列表
            new_devices = [d for d in current_devices if d not in base_devices]
            if new_devices:
                # 取第一个新增设备（批量启动单实例，只会有一个新增）
                target_device = new_devices[0]
                # 检测该设备是否连续存在，连续3次则认为稳定
                if target_device in current_devices:
                    stable_check_count += 1
                    logger.debug(f"疑似新增设备{target_device}已连续检测到{stable_check_count}次，需连续3次确认稳定")
                    # 连续3次检测到，说明设备标识稳定，返回
                    if stable_check_count >= 3:
                        logger.info(f"检测到ADB稳定新增设备: {target_device}，状态为device（就绪）")
                        return target_device
                else:
                    stable_check_count = 0  # 设备消失，重置计数器
            else:
                stable_check_count = 0  # 无新增设备，重置计数器
                target_device = None

            logger.debug(
                f"当前ADB设备列表: {current_devices}，未检测到稳定新增设备，{self.ADB_CHECK_INTERVAL}秒后重试...")
            time.sleep(self.ADB_CHECK_INTERVAL)

        # 超时后，若有疑似设备，最后验证一次是否存在
        if target_device and target_device in self._get_adb_devices():
            logger.warning(f"超时但检测到疑似设备{target_device}，尝试返回")
            return target_device

        logger.error(f"等待{self.ADB_DEVICE_TIMEOUT}秒后，未检测到ADB稳定新增设备")
        return None

    def _click_element(self, locator, timeout=20):
        WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator)).click()

    def _input_text(self, locator, text, timeout=20):
        WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator)).send_keys(text)

    def _clear_text(self, locator, timeout=20):
        WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator)).clear()

    def _get_element_text(self, locator, timeout=20):
        return WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator)).text

    def wait_for_clickable(self, locator, timeout=20):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except TimeoutException:
            return None

    def swipe_to_bottom(self, max_swipes=10, min_swipes=2, length=0.3):
        """
        循环滑动到底部
        @param max_swipes: 最大滑动次数，默认10次
        @param min_swipes: 最小滑动次数，默认3次（确保滑得够深）
        """
        screen_size = self.driver.get_window_size()
        width = screen_size['width']
        height = screen_size['height']

        start_x = width / 2
        start_y = height * 0.8
        end_x = width / 2
        end_y = height * length

        # 记录滑动前页面高度
        last_page_height = 0
        for i in range(max_swipes):
            self.driver.swipe(start_x, start_y, end_x, end_y, duration=800)
            time.sleep(0.5)
            if i >= min_swipes:
                logger.info(f'已滑动{i + 1}次')
                break
        else:
            print(f'已达到最大滑动次数{max_swipes}')

    def unlock_device(self):
        try:
            # 点击 BACK 键显示锁屏界面
            for _ in range(2):
                self.driver.press_keycode(4)
                time.sleep(1)

            # 检查是否有锁屏，是否需要解锁屏幕
            time.sleep(5)
            if self.wait_for_clickable(LdAppLocators.system_app):
                logger.info('模拟器解锁成功！')
                return True

            # 先尝试点击解锁按钮（如果存在），很多设备会先展示解锁入口
            try:
                self._click_element(LdAppLocators.lock_btn)
                time.sleep(0.5)
            except Exception:
                # 没有可点击的解锁入口也继续尝试滑动解锁
                pass

            # 使用坐标点击来绘制解锁图案
            # 坐标顺序（：(135,566)->(135,691)->(135,827)->(271,827)->(405,827)
            logger.info("开始执行解锁图案绘制")

            # 解锁图案的坐标点序列，不同设备需要不同设置
            duration = 1000
            points_list = [(265, 1113), (265, 1386), (265, 1658), (542, 1658), (814, 1658)]
            touch_input = PointerInput(interaction.POINTER_TOUCH, "touch")
            actions = ActionChains(self.driver)
            actions.w3c_actions = ActionBuilder(self.driver, mouse=touch_input)

            # 第一步：按下第一个坐标点（解锁开始，必须按下）
            actions.w3c_actions.pointer_action.move_to_location(points_list[0][0], points_list[0][1])
            actions.w3c_actions.pointer_action.pointer_down()  # 手指按下屏幕
            actions.pause(0.1)

            # 第二步：循环滑动经过所有坐标点（核心：连贯滑动）
            for point in points_list[1:]:
                actions.w3c_actions.pointer_action.move_to_location(point[0], point[1])
                actions.pause(duration / len(points_list) / 1000)  # 均分滑动时间

            # 第三步：抬起手指
            actions.w3c_actions.pointer_action.pointer_up()
            actions.perform()

            # 验证是否解锁成功
            if self.wait_for_clickable(LdAppLocators.system_app):
                logger.info('模拟器解锁成功！')
            else:
                logger.warning('模拟器解锁失败!')
        except Exception as e:
            raise UnlockDeviceError('模拟器解锁失败!')

    def set_proxy(self, port, hostname='10.200.10.209'):
        """设置代理服务器

        Args:
            port (str): 代理端口号
            hostname (str): 代理主机地址，默认 '10.200.10.209'
        """
        try:
            # 参数验证
            if not isinstance(port, str) or not port.isdigit():
                raise ValueError(f"端口号必须是字符串格式的数字，收到: {port}")

            logger.info(f'开始设置代理 - 主机: {hostname}, 端口: {port}')

            # 导航到代理设置界面
            if not self._navigate_to_proxy_settings():
                logger.error('导航到代理设置界面失败')
                raise SetProxyError('导航到代理设置界面失败')

            # 配置代理设置
            if not self._configure_proxy_settings(hostname, port):
                logger.error('配置代理设置失败')
                raise SetProxyError('配置代理设置失败')

            logger.info('代理设置完成')
            return True
        except ValueError as e:
            logger.error(f'参数验证失败: {e}')
            return False
        except Exception as e:
            logger.error(f'设置代理时发生错误: {e}')
            raise

    def _navigate_to_proxy_settings(self):
        """导航到代理设置界面"""
        try:
            logger.info('打开设置应用')
            self.driver.activate_app('com.android.settings')
            time.sleep(2)

            logger.info('点击 Network & Internet')
            self._click_element(LdAppLocators.net_internet)

            logger.info('点击 Wi-Fi, 并选择当前wifi网络')
            self._click_element(LdAppLocators.wifi_btn)
            time.sleep(2)
            self._click_element(LdAppLocators.wifi_btn)

            logger.info('点击网络修改按钮')
            self._click_element(LdAppLocators.modify_btn)

            return True

        except Exception as e:
            logger.error(f'导航到代理设置界面失败: {e}')
            return False

    def _configure_proxy_settings(self, hostname, port):
        """配置代理设置"""
        try:
            # 检查是否已有代理配置
            hostname_element = self.wait_for_clickable(LdAppLocators.hostname_input, timeout=5)

            if not hostname_element:
                # 没有代理配置，需要选择Manual模式
                logger.info('选择代理模式：Manual')
                self._click_element(LdAppLocators.proxy_select)
                self._click_element(LdAppLocators.manual_option)

                # 等待代理输入框出现
                time.sleep(1)

                # 输入代理配置
                logger.info(f'设置代理 - 主机: {hostname}, 端口: {port}')
                hostname_element = self.wait_for_clickable(LdAppLocators.hostname_input, timeout=10)

                if hostname_element:
                    hostname_element.send_keys(hostname)
                    self._input_text(LdAppLocators.port_input, port)
                else:
                    logger.error('无法找到hostname输入框')
                    return False

            else:
                # 已有代理配置，检查是否需要修改
                current_port = self._get_element_text(LdAppLocators.port_input)
                logger.info(f'当前代理端口: {current_port}')

                if current_port == port:
                    logger.info('代理端口已正确，无需修改')
                    self._click_element(LdAppLocators.proxy_save_btn)
                    self.driver.press_keycode(3)
                    return True
                else:
                    logger.info(f'修改代理端口: {current_port} -> {port}')
                    self._clear_text(LdAppLocators.port_input)
                    self._input_text(LdAppLocators.port_input, port)

            # 保存设置
            logger.info('保存代理设置')
            self._click_element(LdAppLocators.proxy_save_btn)

            # 等待设置保存
            time.sleep(2)
            self.driver.press_keycode(3)
            return True

        except Exception as e:
            logger.error(f'配置代理设置失败: {e}')
            return False

    def login_gmail(self):
        """登录Gmail账号 - 完整的登录流程处理"""
        try:
            logger.info(f'[{self.gmail_username}] 开始Gmail登录流程')
            # 返回到setting主界面
            logger.info('打开设置应用')
            self.driver.activate_app('com.android.settings')
            time.sleep(2)

            # 滑动找到账号选项
            self.swipe_to_bottom()
            self._click_element(LdAppLocators.account_btn)

            # 删除员账号
            target_username = self.gmail_username.lower()
            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR,
                                        f'new UiSelector().text("{target_username}")')):
                logger.info(f'[{self.gmail_username}] 步骤1: 删除账号')
                self._click_element(LdAppLocators.gmail_account)
                time.sleep(1)
                self._click_element(LdAppLocators.remove_btn)
                time.sleep(1)
                self._click_element(LdAppLocators.confirm_remove)
                time.sleep(20)

                if not self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR,
                                                f'new UiSelector().text("{target_username}")')):
                    logger.info(f'[{self.gmail_username}] 删除账号成功')
                else:
                    logger.warning(f'[{self.gmail_username}] 退出失败')
                    raise LoginGmailError(f'[{self.gmail_username}] 退出失败')

            # 开始添加，输入账号密码账号
            logger.info(f'[{self.gmail_username}] 步骤2: 输入账号')
            self._click_element(LdAppLocators.add_account_btn)

            if self.wait_for_clickable(LdAppLocators.choose_google_ele):
                self._click_element(LdAppLocators.choose_google)

            time.sleep(30)
            logger.info(f'开始输入账号')
            self._input_text(LdAppLocators.input_ele, self.gmail_username)
            logger.info(f'[{self.gmail_username}] 点击确认按钮')
            self._click_element(LdAppLocators.next_button)
            time.sleep(3)

            # 检查机器人验证
            if self.wait_for_clickable(LdAppLocators.robot_ele, timeout=10):
                logger.error(f'[{self.gmail_username}] 触发机器人验证，账号可能有问题')
                raise GmailAccountError(f'[{self.gmail_username}] 触发机器人验证，账号可能有问题')

            # 处理密码输入
            logger.info(f'[{self.gmail_username}] 步骤3: 要输入密码')
            password = self.youtube_info.get('password', self.youtube_info['password'])  # 使用预加载的密码，默认值作为fallback
            self._input_text(LdAppLocators.input_ele, password)
            if self.wait_for_clickable(LdAppLocators.next_button, timeout=5):
                logger.info(f'[{self.gmail_username}] 点击确认按钮')
                self._click_element(LdAppLocators.next_button)
                time.sleep(3)

            # 验证登录结果
            logger.info(f'[{self.gmail_username}] 步骤4: 验证登录结果、查看是否需要验证')
            # 等待登录完成
            time.sleep(5)
            # 检查是否需要输入辅助邮箱
            if self.wait_for_clickable(LdAppLocators.confirm_email, timeout=5):
                logger.debug(f'[{self.gmail_username}] 需要输入辅助邮箱')
                self._click_element(LdAppLocators.confirm_email)
                confirm_email = self.youtube_info.get('confirm_email', self.youtube_info['confirm_email'])
                self._input_text(LdAppLocators.confirm_email_input, confirm_email)
                self._click_element(LdAppLocators.next_button)

            if self.wait_for_clickable(LdAppLocators.confirm_phone):
                logger.error(f'[{self.gmail_username}] 需要验证手机号')
                input(f'[{self.gmail_username}] 需要验证手机号')

            # 检查是否需要确认使用人
            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceId("headingText")')):
                head_txt = self._get_element_text(
                    (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceId("headingText")'), 20)
                if head_txt == 'Who will be using this device?':
                    self._click_element(LdAppLocators.next_button)
                    time.sleep(2)

            # 点击skip和accept
            time.sleep(5)
            self.swipe_to_bottom()
            if self.wait_for_clickable(LdAppLocators.skip_btn):
                self._click_element(LdAppLocators.skip_btn)
            self._click_element(LdAppLocators.agree_btn)

            # 滑动到底部
            time.sleep(5)
            if self.wait_for_clickable(LdAppLocators.more_btn):
                self.swipe_to_bottom()
                self._click_element(LdAppLocators.more_btn)

            # 检查是否登录成功（检查是否有成功并回到主界面）
            self.driver.press_keycode(3)

            logger.info("正在启动Play Store...")
            self._click_element((AppiumBy.ACCESSIBILITY_ID, 'Play Store'), timeout=60)
            time.sleep(3)  # 等待Play Store完全加载

            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Accept")')):
                self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Accept")'))
            else:
                self.driver.press_keycode(4)

            if self.wait_for_clickable(LdAppLocators.gmail_login_succ):
                logger.info(f'[{self.gmail_username}] Gmail登录流程完成')
                self.driver.press_keycode(3)
                return True

        except KeyboardInterrupt as e:
            raise e
        except GmailAccountError:
            raise
        except GmailPhoneError:
            raise
        except LoginGmailError:
            raise
        except Exception as e:
            logger.error(f'[{self.gmail_username}] Gmail登录过程中发生错误: {e}')
            raise LoginGmailError(f'[{self.gmail_username}] Gmail登录过程中发生错误: {e}')

    def install_apple(self):
        logger.info(f"开始下载apple music")
        try:
            if self.return_to_home_and_check_installation(target_app='Apple Music'):
                logger.info(f'[{self.gmail_username}] 已下载Apple Music')
                return True

            # 等待并点击Play Store应用
            self.driver.press_keycode(3)
            logger.info("正在启动Play Store...")
            self._click_element((AppiumBy.ACCESSIBILITY_ID, 'Play Store'), timeout=60)
            time.sleep(5)  # 等待Play Store完全加载

            # 点击搜索按钮
            logger.info("正在点击搜索按钮...")
            search_x, search_y = 450, 155
            self.driver.tap([(search_x, search_y)], duration=100)
            time.sleep(2)

            # 等待搜索输入框出现并输入搜索内容
            logger.info("正在输入搜索内容...")
            if self.wait_for_clickable(LdAppLocators.search_input):
                self._input_text(LdAppLocators.search_input, 'apple music')
                time.sleep(2)
            else:
                logger.error("搜索输入框未找到，开始重试")
                self.driver.press_keycode(4)
                self.driver.tap([(search_x, search_y)], duration=100)
                time.sleep(2)
                self._input_text(LdAppLocators.search_input, 'apple music')
                time.sleep(2)

            # 使用回车键搜索
            logger.info("正在执行搜索...")
            self.driver.press_keycode(66)  # 66是Android的KEYCODE_ENTER
            time.sleep(3)  # 等待搜索结果加载

            # 查找并点击Apple Music应用
            logger.info("正在查找Apple Music应用...")
            apple_music_ele = ['Apple Music, Apple, Star rating: 4.6, Teen, In-app purchases',
                               'Apple Music, Apple, Star rating: 4.3, Parental guidance, In-app purchases']
            for ele in apple_music_ele:
                if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().description("{ele}")')):
                    self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().description("{ele}")'),
                                        timeout=10)
                    break
            time.sleep(2)

            # 点击安装按钮
            logger.info("正在点击安装按钮...")
            self._click_element(LdAppLocators.install_btn)
            time.sleep(2)
            
            # 检查是否需要确认账号
            if self.wait_for_clickable(LdAppLocators.complete_account_locator, timeout=10):
                self._click_element(LdAppLocators.complete_continue)
                self._click_element(LdAppLocators.skip_btn)
                time.sleep(5)

            # 等待下载完成 - 监控下载进度
            logger.info("正在下载Apple Music...")
            max_wait_time = 120  # 最大等待2分钟
            download_complete = False

            for i in range(max_wait_time // 5):  # 每5秒检查一次
                try:
                    # 检查是否还有正在下载的标识
                    still_installing = self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                                                                 'new UiSelector().text("Verified by Play Protect")')

                    if not still_installing:
                        logger.info("✓ 下载完成，应用已安装")
                        download_complete = True
                        break
                    elif still_installing:
                        # 如果既没有Install按钮也没有Open按钮，可能是其他状态
                        logger.info(f"下载进行中... ({(i + 1) * 5}秒)")
                    else:
                        logger.info(f"下载进行中... ({(i + 1) * 5}秒)")

                except Exception as e:
                    logger.info(f"检查下载状态时出错: {e}")

                time.sleep(5)

            if not download_complete:
                logger.info("⚠ 下载可能未完成，继续执行下一步...")

            # 返回桌面检查是否安装成功
            logger.info("下载完成，返回桌面检查安装状态...")
            return self.return_to_home_and_check_installation(target_app='Apple Music')

        except KeyboardInterrupt as e:
            raise e
        except Exception as e:
            logger.error(f'[{self.gmail_username}] 下载Apple Music失败: {e}')
            raise InstallAppError(f'[{self.gmail_username}] 下载Apple Music失败: {str(e)}')

    def start_premium(self, card_4):
        try:
            logger.info(f'[{self.apple_username}] 开始开会员流程')
            self.driver.activate_app('com.apple.android.music')
            time.sleep(5)
            logger.info("关闭弹窗按钮")
            for locators in [LdAppLocators.apple_continue, LdAppLocators.do_not_send]:
                if self.wait_for_clickable(locators, timeout=10):
                    self._click_element(locators)

            time.sleep(5)
            logger.info("返回Apple Music主界面")
            if self.wait_for_clickable((AppiumBy.ACCESSIBILITY_ID, 'Close page'), timeout=8):
                self.driver.press_keycode(4)
            time.sleep(3)

            # 检查是否登录
            have_login = False
            logger.info("检查是否已登录账号")
            self._click_element(LdAppLocators.more_option)
            if self.wait_for_clickable(LdAppLocators.apple_account, timeout=10):
                have_login = True
                logger.debug(f"[{self.apple_username}] 已登录")

            if not have_login:
                self._click_element(LdAppLocators.setting)
                time.sleep(2)

                logger.info("正在点击登录按钮...")
                self._click_element(LdAppLocators.apple_login)

                logger.info(f"[{self.apple_username}] 开始登录apple账号")
                self._input_text(LdAppLocators.apple_username_input, self.apple_username)
                self._input_text(LdAppLocators.apple_password_input, self.apple_info['password'])
                self._click_element(LdAppLocators.appel_login_continue)
                time.sleep(10)

                if self.wait_for_clickable(LdAppLocators.theme_btn):
                    logger.info(f'[{self.apple_username}] 登录成功')
                    self._click_element(LdAppLocators.navigate_up)

                self._click_element(LdAppLocators.more_option)
                self._click_element(LdAppLocators.apple_account)
                time.sleep(2)
            else:
                self._click_element(LdAppLocators.apple_account)

            logger.info(f"[{self.apple_username}] 开始开通会员")
            self._click_element(LdAppLocators.subscribe_btn)
            time.sleep(5)
            self._click_element(LdAppLocators.start_subscribe)
            time.sleep(2)

            logger.info(f"[{self.apple_username}] 开始检查卡号")
            card_selector = f'new UiSelector().text("Visa-{card_4}")'
            if not self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, card_selector)):
                logger.warning(f'[{self.apple_username}] 卡号不正确，重新选取卡号')
                self._click_element((AppiumBy.ANDROID_UIAUTOMATOR,
                                     'new UiSelector().className("android.widget.ImageView").instance(5)'))
                time.sleep(5)
                self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, card_selector))
            else:
                logger.info(f'[{self.apple_username}] 卡号正确')
            time.sleep(5)

            logger.info(f"[{self.apple_username}] 开始付费")
            self._click_element((AppiumBy.CLASS_NAME, 'android.widget.Button'))
            time.sleep(1)
            if self.wait_for_clickable((AppiumBy.CLASS_NAME, 'android.widget.CheckBox')):
                logger.info(f'[{self.apple_username}] 输入密码确认账号')
                self._click_element((AppiumBy.CLASS_NAME, 'android.widget.CheckBox'))
                self._input_text(LdAppLocators.input_ele, self.youtube_info['password'])
                self._click_element((AppiumBy.CLASS_NAME, 'android.widget.Button'))

            logger.info(f'[{self.apple_username}] 等待支付过程...')
            
            # 处理需要填写地址的情况 
            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Street address")')):
                logger.debug(f"[{self.apple_username}] 需要填写地址")
                self.swipe_to_bottom(max_swipes=1, min_swipes=0, length=0.7)

                # 获取当前页面的zip文本，匹配对应zip的Street address
                zip_text = self._get_element_text((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.EditText").instance(4)'))
                street_address = None
                for addr in addresses:
                    if addr.get("zip") == zip_text:
                        street_address = addr.get("Street address", "")
                        logger.debug(f"[{self.apple_username}] 匹配到地址: {street_address}")
                        break
                else:
                    logger.warning(f"[{self.apple_username}] 未在YAML中找到邮编 {zip_text} 对应的地址")
                    street_address = "14386 SW 36th St"  # 兜底地址

                # 步骤3：定位Street Address输入框并填写
                if street_address:
                    # 输入匹配到的街道地址
                    self._input_text(LdAppLocators.street_address_locator, street_address)
                    logger.debug(f"[{self.apple_username}] 成功填写街道地址: {street_address}")

                    self.swipe_to_bottom(max_swipes=10, min_swipes=4, length=0.7)
                    self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Save")'))
                    time.sleep(2)
                    self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Confirm")'))
                    time.sleep(5)
                    self._click_element((AppiumBy.CLASS_NAME, 'android.widget.Button'))
                    time.sleep(10)

            for btn_text in ["Not now", "No thanks"]:
                if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{btn_text}")'), timeout=3):
                    self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{btn_text}")'))
                    break

            time.sleep(10)

            logger.info(f"[{self.apple_username}] 检查是否开通成功")
            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Upgrade to Family")')):
                logger.info(f"[{self.apple_username}] 开通成功")
                return True
            elif self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Error")')):
                logger.warning(f"[{self.apple_username}] 支付失败")
                return False
            else:
                logger.warning(f"[{self.apple_username}] 检查异常 - 未检测到会员开通标志")
                return False

        except KeyboardInterrupt as e:
            raise e
        except InstallAppError:
            raise
        except Exception as e:
            logger.error(f'[{self.apple_username}] 开通会员失败: {str(e)}')
            raise StartPremiumError(f'[{self.apple_username}] 开通会员失败: {str(e)}')

    def return_to_home_and_check_installation(self, target_app):
        """返回桌面并检查Apple Music是否安装成功"""
        try:
            # 方法1: 使用HOME键返回桌面
            logger.info("按下HOME键返回桌面...")
            self.driver.press_keycode(3)  # 3是Android的KEYCODE_HOME

            # 简化的桌面等待方法 - 直接等待一段时间，不依赖activity检测
            logger.info("等待桌面加载...")
            time.sleep(5)  # 给桌面足够的时间加载

            # 可选：简单检查当前是否在桌面环境
            try:
                current_activity = self.driver.current_activity
                logger.info(f"当前Activity: {current_activity}")
            except Exception as e:
                logger.warning(f"无法获取当前activity: {e}")
                # 即使无法获取activity也继续执行

            # 检查Apple Music应用图标是否存在
            logger.info("正在检查Apple Music应用图标...")
            if self.wait_for_clickable((AppiumBy.ACCESSIBILITY_ID, target_app)):
                logger.info(f"✓ {target_app}应用图标已找到，安装成功！")
                return True
            else:
                logger.warning(f"✗ 未找到{target_app}应用图标，可能安装失败")
                return False
        except Exception as e:
            logger.warning(f"检查安装状态时出现错误: {e}")
            return False

    def uninstall_google_apps(self):
        """卸载 Google 系统应用 + YouTube / YouTube Music"""
        # 系统应用需要用 ADB 命令卸载
        adb_system_apps = [
            "com.google.android.gms",  # Google Play services
        ]
        # 普通应用可以用 dnconsole 命令
        dnconsole_apps = [
            "com.android.vending",  # Google Play Store
            "com.google.android.gsf",  # Google Services Framework
            "com.apple.android.music",  # Apple Music
            "com.google.android.youtube",  # YouTube
            "com.google.android.apps.youtube.music",  # YouTube Music
        ]

        # 先用 ADB 卸载系统应用
        for pkg in adb_system_apps:
            logger.info(f"正在通过ADB卸载系统应用: {pkg}")

            # 先尝试停用应用
            adb_disable_cmd = f'adb -s {self.udid} shell pm disable-user --user 0 {pkg}'
            subprocess.run(adb_disable_cmd, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1)

            # 再尝试卸载
            adb_cmd = f'adb -s {self.udid} shell pm uninstall --user 0 {pkg}'
            result = subprocess.run(
                adb_cmd,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(2)
            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")
            # 检查是否成功 - Success 表示成功
            if "Success" in result.stdout:
                logger.info(f"卸载 {pkg} 成功")
            elif "DELETE_FAILED_DEVICE_POLICY_MANAGER" in result.stderr:
                # 设备策略管理失败，尝试强制停用
                logger.warning(f"设备策略保护，无法卸载 {pkg}，尝试强制停用...")
                force_disable_cmd = f'adb -s {self.udid} shell pm disable-user --user 0 --stream {pkg}'
                subprocess.run(force_disable_cmd, shell=True, check=False)
                logger.info(f"已强制停用 {pkg}")
            else:
                logger.warning(f"卸载 {pkg} 结果: {result.stdout} {result.stderr}")

        # 再用 dnconsole 卸载普通应用
        for pkg in dnconsole_apps:
            logger.info(f"正在卸载: {pkg}")
            result = subprocess.run(
                f'dnconsole.exe uninstallapp --name "{self.gmail_username}" --packagename {pkg}',
                cwd=self.LDPLAYER9_DIR,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(2)
            if result.stdout:
                logger.info(f"[STDOUT] {result.stdout}")
            if result.stderr:
                logger.warning(f"[STDERR] {result.stderr}")
            # 检查是否成功卸载
            if "success" in result.stdout.lower() or not result.stderr:
                logger.info(f"卸载 {pkg} 成功")
            else:
                logger.warning(f"卸载 {pkg} 结果未知: {result.stdout} {result.stderr}")

    def install_google_service(self):
        try:
            logger.info(f'{self.gmail_username} 开始重新安装google框架')
            self.driver.activate_app('com.android.googleinstaller')

            if self.wait_for_clickable((AppiumBy.CLASS_NAME, 'android.widget.Button')):
                self._click_element((AppiumBy.CLASS_NAME, 'android.widget.Button'))

            # 等待下载完成 - 监控下载进度
            logger.info("正在下载google框架")
            max_wait_time = 240  # 最大等待2分钟
            download_complete = False

            for i in range(max_wait_time // 5):  # 每5秒检查一次
                try:
                    # 检查是否还有正在下载的标识
                    finish_install = self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                                                               'new UiSelector().text("安装完成")')

                    if finish_install:
                        logger.info("✓ 下载完成，应用已安装")
                        download_complete = True
                        break
                    elif not finish_install:
                        # 如果既没有Install按钮也没有Open按钮，可能是其他状态
                        logger.info(f"下载进行中... ({(i + 1) * 5}秒)")
                    else:
                        logger.info(f"下载进行中... ({(i + 1) * 5}秒)")

                except Exception as e:
                    logger.info(f"检查下载状态时出错: {e}")

                time.sleep(5)
            if not download_complete:
                logger.info("⚠ 下载可能未完成，继续执行下一步...")

            # 返回桌面检查是否安装成功
            logger.info("下载完成，返回桌面检查安装状态...")
            if self.return_to_home_and_check_installation(target_app='Play Store'):
                return True
            else:
                return False
        except KeyboardInterrupt as e:
            raise e
        except InstallAppError:
            raise
        except Exception as e:
            logger.error(f'[{self.gmail_username}] 下载google框架失败: {e}')
            raise InstallAppError(f'[{self.gmail_username}] 下载google框架失失败: {str(e)}')

def close_device(username):
    """关闭模拟器，包含命令存在校验、重试、超时与结果验证。"""
    cmd = f'dnconsole.exe quit --name "{username}"'
    try:
        logger.info(f"关闭模拟器: {username}")

        logger.info(f"执行命令: {cmd}")
        try:
            result = subprocess.run(
                cmd,
                cwd=r"D:\leidian\LDPlayer9",
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as e:
            logger.warning(f"dnconsole 命令超时: {e}")
            raise LdDeviceQuitError("dnconsole quit 命令超时", username=username) from e

        time.sleep(2)
        # 日志输出
        if result.stdout:
            logger.info(f"[STDOUT] {result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"[STDERR] {result.stderr.strip()}")

        stderr_lower = (result.stderr or "").lower()
        error_keywords = ["error", "失败", "failed", "not found", "不存在", "cannot"]

        # 根据 returncode 与 stderr 判断是否成功
        if result.returncode != 0 or any(kw in stderr_lower for kw in error_keywords):
            logger.warning(f"dnconsole 返回异常 (code={result.returncode})")
            raise LdDeviceQuitError(f"模拟器关闭失败: returncode={result.returncode}")
        else:
            logger.info(f'{username} 模拟器关闭成功')

    except LdDeviceQuitError as e:
        logger.error(f"模拟器关闭失败: {e}")
        raise
    except Exception as e:
        logger.exception(f"关闭模拟器时发生未知错误: {e}")
        raise LdDeviceQuitError(f"关闭模拟器过程中发生错误: {e}")


def read_file(file_path):
    try:
        with open(file_path, 'r') as f:
            return [i.strip() for i in f]
    except FileNotFoundError:
        logger.error(f"File {file_path} not found.")
        return []


def write_file(file_name, data):
    try:
        with open(file_name, 'a') as f:
            f.write(f'{data}\n')
    except Exception as e:
        logger.error(f"写入失败文件时出错: {e}")


def run():
    acc_list = read_file(prepare_file_path / 'new_device.txt')
    apple_list = read_file(prepare_file_path / 'succ_apple.txt')
    robot_list = read_file(prepare_file_path / 'robot_gmail.txt')
    phone_list = read_file(prepare_file_path / 'phone_gmail.txt')
    for username in acc_list:
        if username in apple_list:
            logger.info(f'{username} 已安装Apple Music')
            continue
        if username in robot_list:
            logger.warning(f'{username} 触发人机验证')
            continue
        if username in phone_list:
            logger.warning(f'{username} 需要手机验证')
            continue

        # 需要重试的异常（整体重试）
        retry_exceptions = (LdDeviceStartError, AppiumStartError, SetProxyError, UnlockDeviceError, LoginGmailError)
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                ldauto = AppiumldAuto(gmail_username=username, apple_username='')
                ldauto.unlock_device()
                # 设置YouTube/Gmail账号代理
                youtube_port = ldauto.youtube_info.get('port', '')
                ldauto.set_proxy(port=str(youtube_port))
                ldauto.login_gmail()

                # InstallAppError 单独重试，只重试 install_apple
                install_success = False
                try:
                    install_success = ldauto.install_apple()
                except InstallAppError:
                    logger.warning(f'[{username}] 安装Apple Music失败，尝试重试')
                    try:
                        install_success = ldauto.install_apple()
                    except InstallAppError as e:
                        logger.error(f'[{username}] 重试安装Apple Music仍然失败: {e}')
                        # 继续执行，记录失败但不中断流程

                if install_success:
                    write_file(prepare_file_path / 'succ_apple.txt', username)
                ldauto.driver.quit()
                break  # 成功，跳出重试循环
            except (GmailAccountError, GmailPhoneError) as e:
                logger.error(f'[{username}] {e}')
                if isinstance(e, GmailAccountError):
                    write_file(prepare_file_path / 'robot_gmail.txt', username)
                elif isinstance(e, GmailPhoneError):
                    write_file(prepare_file_path / 'phone_gmail.txt', username)
                break  # 跳过当前账号，继续处理下一个
            except retry_exceptions as e:
                logger.warning(f'[{username}] 第 {attempt} 次执行失败: {e}')
                if attempt < max_retries:
                    logger.info(f'[{username}] 准备第 {attempt + 1} 次重试')
                    try:
                        close_device(username)
                    except LdDeviceQuitError:
                        pass
                else:
                    logger.error(f'[{username}] 达到最大重试次数 {max_retries}，执行失败')
            except Exception as e:
                logger.error(f'[{username}] 未知异常: {e}')
                raise
            finally:
                try:
                    close_device(username)
                except Exception as e:
                    logger.error(f'[{username}] 在 close_device 时发生错误: {e}')


def run_install_google():
    """安装 Google 框架的流程"""
    acc_list = read_file(prepare_file_path / 'new_device.txt')
    google_list = read_file(prepare_file_path / 'succ_google.txt')
    for username in acc_list:
        if username in google_list:
            logger.info(f'{username} 已安装Google框架')
            continue
        try:
            ldauto = AppiumldAuto(gmail_username=username, apple_username='')
            ldauto.unlock_device()
            youtube_port = ldauto.youtube_info.get('port', '')
            ldauto.set_proxy(port=str(youtube_port))
            # 卸载旧的 Google 应用
            ldauto.uninstall_google_apps()
            # 安装 Google 服务框架
            if ldauto.install_google_service():
                write_file(prepare_file_path / 'succ_google.txt', username)
            ldauto.driver.quit()
        except LdDeviceStartError:
            logger.error(f'[{username}] 模拟器启动失败')
        except AppiumStartError:
            logger.error(f'[{username}] Appium连接失败')
        except UnlockDeviceError:
            logger.error(f'[{username}] 模拟器解锁失败')
        except InstallAppError:
            logger.error(f'[{username}] 安装Google框架失败')
        finally:
            try:
                close_device(username)
            except LdDeviceQuitError:
                logger.error(f'[{username}] 在 close_device 时发生错误')


def run_create_emulator():
    """创建模拟器并设置属性的流程"""
    acc_list = read_file(prepare_file_path / 'new_device.txt')
    created_list = read_file(prepare_file_path / 'created_emulator.txt')

    for username in acc_list:
        if username in created_list:
            logger.info(f'{username} 已创建模拟器')
            continue
        try:
            # 创建模拟器实例（不启动）
            ldauto = AppiumldAuto(gmail_username=username, apple_username='', mode='create')

            # 步骤1: 创建模拟器
            logger.info(f'[{username}] 步骤1: 创建模拟器')
            if not ldauto.create_emulator(username):
                logger.error(f'[{username}] 创建模拟器失败')
                continue

            # 步骤2: 修改模拟器属性
            logger.info(f'[{username}] 步骤2: 修改模拟器属性')
            if not ldauto.modify_emulator(
                    username=username,
                    resolution='1080,1920,480',
                    cpu=2,
                    memory=2048
            ):
                logger.error(f'[{username}] 修改模拟器属性失败')
                continue

            # 记录成功的用户名
            write_file(prepare_file_path / 'created_emulator.txt', username)
            logger.info(f'[{username}] 模拟器创建并配置成功')

        except Exception as e:
            logger.error(f'[{username}] 创建模拟器时发生错误: {e}')
            continue


def run_start_premium():
    """开通Appel google pay会员的流程"""
    acc_list = read_file(prepare_file_path / 'premium_acc.txt')
    premium_list = read_file(prepare_file_path / 'succ_premium.txt')
    for acc_info in acc_list:
        g_username = acc_info.split(':')[0]
        a_username = acc_info.split(':')[1]
        card_num = acc_info.split(':')[2]
        if a_username in premium_list:
            logger.info(f'{a_username} 已成功开通Google Pay')
            continue
        try:
            ldauto = AppiumldAuto(gmail_username=g_username, apple_username=a_username)
            ldauto.unlock_device()
            # 开通Apple Music的 Google Pay会员
            if ldauto.start_premium(card_num[-4:]):
                write_file(prepare_file_path / 'succ_premium.txt', a_username)
            ldauto.driver.quit()
        except LdDeviceStartError:
            logger.error(f'[{g_username}] 模拟器启动失败')
        except AppiumStartError:
            logger.error(f'[{g_username}] Appium连接失败')
        except UnlockDeviceError:
            logger.error(f'[{g_username}] 模拟器解锁失败')
        except StartPremiumError:
            logger.error(f'[{a_username}] 开通apple会员失败')
        finally:
            try:
                close_device(g_username)
            except LdDeviceQuitError:
                logger.error(f'[{g_username}] 在 close_device 时发生错误')


def run_delete_emulator():
    """删除模拟器流程"""
    acc_list = read_file(prepare_file_path / 'new_device.txt')
    delete_list = read_file(prepare_file_path / 'delete_emulator.txt')

    for username in acc_list:
        if username in delete_list:
            logger.info(f'{username} 已删除模拟器')
            continue
        try:
            # 创建模拟器实例（不启动）
            ldauto = AppiumldAuto(gmail_username=username, apple_username='', mode='create')

            # 步骤1: 创建模拟器
            logger.info(f'[{username}] 步骤1: 删除模拟器')
            if not ldauto.delete_emulator(username):
                logger.error(f'[{username}] 删除模拟器失败')
                continue

            # 记录成功的用户名
            write_file(prepare_file_path / 'delete_emulator.txt', username)
            logger.info(f'[{username}] 模拟器删除成功')

        except Exception as e:
            logger.error(f'[{username}] 创建模拟器时发生错误: {e}')
            continue


TASK_OPTIONS = [
    ('install_apple', '安装Apple Music'),
    ('install_google', '安装Google框架'),
    ('create_emulator', '创建模拟器'),
    ('delete_emulator', '删除模拟器'),
    ('start_premium', '开通Apple Music会员')
]


def parse_arguments():
    parser = argparse.ArgumentParser(description="Apple 账号自动化任务入口")
    parser.add_argument(
        '--task',
        choices=[option[0] for option in TASK_OPTIONS],
        help='指定要执行的任务'
    )
    return parser.parse_args()


def prompt_task_selection():
    print("请选择要执行的任务：")
    for idx, (value, description) in enumerate(TASK_OPTIONS, start=1):
        print(f"{idx}. {value} - {description}")
    choice = input("请输入选项数字，默认 1: ").strip()
    try:
        choice_idx = int(choice) - 1 if choice else 0
        if 0 <= choice_idx < len(TASK_OPTIONS):
            return TASK_OPTIONS[choice_idx][0]
    except ValueError:
        pass
    return TASK_OPTIONS[0][0]


if __name__ == '__main__':
    args = parse_arguments()
    task = args.task or prompt_task_selection()

    if task == 'install_apple':
        run()
    elif task == 'install_google':
        run_install_google()
    elif task == 'create_emulator':
        run_create_emulator()
    elif task == 'start_premium':
        run_start_premium()
    elif task == 'delete_emulator':
        run_delete_emulator()
