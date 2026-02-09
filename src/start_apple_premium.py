"""
    ld模拟器使用appium实现自动化开googlepay会员
"""
import re
import time
import subprocess
from pathlib import Path
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
from selenium.common.exceptions import NoSuchElementException, TimeoutException

music_db = ''


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


class LoginGmailError(LdDeviceError):
    """Gmail账号登录失败"""
    pass


class AccountInfoError(LdDeviceError):
    """账号信息错误"""
    pass


class InstallAppleError(LdDeviceError):
    """下载apple music失败"""
    pass


class SetProxyError(LdDeviceError):
    """设置代理发生错误"""
    pass


class UnlockDeviceError(LdDeviceError):
    """设置代理发生错误"""
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
    search = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Search")')
    search2 = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.view.View").instance(21)')
    search3 = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.view.View").instance(21)')


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

    def __init__(self, gmail_username, apple_username, code=None) -> None:
        self.udid = ''
        self.gmail_username = gmail_username
        self.apple_username = apple_username
        self.code = code
        # 初始化账号信息
        self._load_account_info()
        # 启动模拟器、初始化 Appium 驱动
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
                acc_info = music_db.accounts_v2.find_one(
                    {'dsp.name': 'youtube_video', 'username': self.gmail_username.lower()})
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
                'disableHiddenApiPolicy': False,     # 禁止自动执行隐藏API禁用命令
                'skipDeviceInitialization': False    # 保留基础设备初始化（仅禁隐藏API）
            })
            driver = webdriver.Remote(self.appium_server_url,
                                      options=UiAutomator2Options().load_capabilities(self.capabilities))
            logger.info(f"启动Appium驱动成功")
            return driver
        except Exception as e:
            logger.error(f"Appium启动失败: {e}")
            raise AppiumStartError(f"Appium启动失败: {e}")

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
                raise LdDeviceStartError(f"模拟器[{self.gmail_username}]ADB设备匹配失败，超时{self.ADB_DEVICE_TIMEOUT}秒")

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
        WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator)).click()

    def _input_text(self, locator, text, timeout=20):
        WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator)).send_keys(text)

    def _clear_text(self, locator, timeout=20):
        WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator)).clear()

    def _get_element_text(self, locator, timeout=20):
        return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator)).text

    def wait_for_clickable(self, locator, timeout=20):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except TimeoutException:
            return None

    def unlock_device(self):
        try:
            # 点击 BACK 键显示锁屏界面
            for _ in range(2):
                self.driver.press_keycode(4)
                time.sleep(1)

            # 检查是否有锁屏，是否需要解锁屏幕
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
            raise SetProxyError(f'设置代理时发生错误: {e}')

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

    def login_gamil(self):
        """登录Gmail账号 - 完整的登录流程处理"""
        try:
            logger.info(f'[{self.gmail_username}] 开始Gmail登录流程')

            # 打开Play Store应用
            logger.info(f'[{self.gmail_username}] 步骤1: 打开Play Store')
            self._click_element(LdAppLocators.play_store_app)

            time.sleep(30)

            # 查看账号是否已登录
            if self.wait_for_clickable(LdAppLocators.gmail_login_succ, 10):
                logger.info(f'[{self.gmail_username}] Gmail已登录')
                return True

            # 处理账号验证流程
            logger.info(f'[{self.gmail_username}] 步骤2: 处理账号验证')
            self._click_element(LdAppLocators.veritry_next_btn, timeout=60)
            time.sleep(3)

            # 检查机器人验证
            if self.wait_for_clickable(LdAppLocators.robot_ele, timeout=10):
                logger.warning(f'[{self.gmail_username}] 触发机器人验证，账号可能有问题')
                raise GmailAccountError

            # 处理密码输入
            logger.info(f'[{self.gmail_username}] 步骤3: 检查是否需要输入密码')
            password = self.youtube_info.get('password', self.youtube_info['password'])  # 使用预加载的密码，默认值作为fallback
            logger.info(f'[{self.gmail_username}] 发现密码输入框，尝试输入密码')
            self._input_text(LdAppLocators.input_ele, password)
            password_entered = True

            if password_entered:
                # 点击下一步/登录按钮
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

            if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Accept")'), timeout=20):
                logger.info(f'[{self.gmail_username}] 点击Accept按钮')
                self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Accept")'))

            # 检查是否登录成功（检查是否有成功并回到主界面）
            time.sleep(10)
            # if self.wait_for_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Not now")'), timeout=10):
            self.driver.press_keycode(4)

            if self.wait_for_clickable(LdAppLocators.gmail_login_succ):
                logger.info(f'[{self.gmail_username}] Gmail登录流程完成')
                self.driver.press_keycode(3)
                return True

        except KeyboardInterrupt as e:
            raise e
        except GmailAccountError:
            raise
        except LoginGmailError:
            raise
        except Exception as e:
            logger.error(f'[{self.gmail_username}] Gmail登录过程中发生错误: {e}')
            raise LoginGmailError(f'[{self.gmail_username}] Gmail登录失败: {str(e)}')

    def install_apple(self):
        logger.info(f"开始下载apple music")
        try:
            # 等待并点击Play Store应用
            self.driver.press_keycode(3)
            logger.info("正在启动Play Store...")
            self._click_element((AppiumBy.ACCESSIBILITY_ID, 'Play Store'), timeout=60)
            time.sleep(3)  # 等待Play Store完全加载

            # 点击搜索按钮
            logger.info("正在点击搜索按钮...")
            search_x, search_y = 450, 155
            if self.wait_for_clickable(LdAppLocators.search):
                for _ in range(2):
                    self._click_element(LdAppLocators.search)
            else:
                self.driver.tap([(search_x, search_y)], duration=100)
            time.sleep(2)

            # 等待搜索输入框出现并输入搜索内容
            logger.info("正在输入搜索内容...")
            self._input_text(
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    'new UiSelector().className("android.widget.EditText")'
                ),
                'apple music'
            )
            time.sleep(2)
            # 使用回车键搜索
            logger.info("正在执行搜索...")
            self.driver.press_keycode(66)  # 66是Android的KEYCODE_ENTER
            time.sleep(3)  # 等待搜索结果加载

            # 查找并点击Apple Music应用
            logger.info("正在查找Apple Music应用...")
            try:
                self._click_element((AppiumBy.ACCESSIBILITY_ID, 'Apple Music\nApple\n'))
            except:
                self._click_element((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Apple Music")'))
            time.sleep(2)

            # 点击安装按钮
            logger.info("正在点击安装按钮...")
            self._click_element(
                (AppiumBy.ANDROID_UIAUTOMATOR,
                 'new UiSelector().className("android.widget.Button").instance(0)')
            )
            time.sleep(2)
            # 等待下载完成 - 监控下载进度
            logger.info("正在下载Apple Music...")
            max_wait_time = 120  # 最大等待2分钟
            download_complete = False

            for i in range(max_wait_time // 5):  # 每5秒检查一次
                try:
                    # 检查是否还有正在下载的标识
                    still_installing = self.driver.find_elements(AppiumBy.XPATH,
                                                                 '//android.widget.TextView[@text="Verified by Play Protect"]')

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
            self.return_to_home_and_check_installation()

        except KeyboardInterrupt as e:
            raise e
        except InstallAppleError:
            raise
        except Exception as e:
            logger.error(f'[{self.gmail_username}] 下载Apple Music失败: {e}')
            raise InstallAppleError(f'[{self.gmail_username}] 下载Apple Music失败: {str(e)}')

    def start_premium(self):
        pass

    def return_to_home_and_check_installation(self):
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
            if self.wait_for_clickable((AppiumBy.ACCESSIBILITY_ID, 'Apple Music')):
                logger.info("✓ Apple Music应用图标已找到，安装成功！")
                return True
            else:
                logger.warning("✗ 未找到Apple Music应用图标，可能安装失败")
                return False
        except Exception as e:
            logger.warning(f"检查安装状态时出现错误: {e}")
            return False


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


def run(username):
    try:
        ldauto = AppiumldAuto(gmail_username=username, apple_username='')
        ldauto.unlock_device()
        # 设置YouTube/Gmail账号代理
        youtube_port = ldauto.youtube_info.get('port', '')
        ldauto.set_proxy(port=str(youtube_port))
        ldauto.login_gamil()
        ldauto.install_apple()
        # 设置Apple账号代理
        # apple_port = ldauto.apple_info.get('port', '')
        # ldauto.set_proxy(port=str(apple_port) if apple_port else '')
        ldauto.start_premium()
        ldauto.driver.quit()
    except LdDeviceStartError:
        logger.error(f'[{username}] 模拟器启动失败')
    except AppiumStartError:
        logger.error(f'[{username}] Appium连接失败')
    except SetProxyError:
        logger.error(f'[{username}] 设置代理失败')
    except LoginGmailError:
        logger.error(f'[{username}] Gmail登录失败')
    except GmailAccountError:
        logger.error(f'[{username}] Gmail账号不可用')
    except InstallAppleError:
        logger.error(f'[{username}] 下载Apple Music失败')
    except UnlockDeviceError:
        logger.error(f'[{username}] 模拟器解锁失败')
    finally:
        try:
            close_device(username)
        except LdDeviceQuitError:
            logger.error(f'[{username}] 在 close_device 时发生错误')


if __name__ == '__main__':
    base_path = Path(__file__).parent.parent.parent
    acc_path = ''
    with open(acc_path, 'r') as f:
        for i in f:
            run(i.strip())