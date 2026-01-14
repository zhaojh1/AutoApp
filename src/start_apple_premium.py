"""
    ld模拟器使用appium实现自动化开googlepay会员
"""
from pdb import post_mortem
import time
import subprocess
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


class LdDeviceError(Exception):
    """模拟器操作异常基类"""
    def __init__(self, message, username=None):
        self.message = message
        self.username = username
        super().__init__(self.message)

class LdDeviceStartError(LdDeviceError):
    """模拟器启动失败"""
    pass

class AppiumStartError(LdDeviceError):
    """Appium链接失败"""
    pass

@dataclass
class LdAppLocators:
    lock_btn = (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="Unlock"]')
    system_app = (AppiumBy.ACCESSIBILITY_ID, 'Folder: 系统应用')
    net_internet = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.LinearLayout").instance(4)')
    wifi_btn = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.widget.RelativeLayout").instance(0)')
    modify_btn = (AppiumBy.ACCESSIBILITY_ID, 'Modify')
    hostname_input = (AppiumBy.ID, 'com.android.settings:id/proxy_hostname')
    port_input = (AppiumBy.ID, 'com.android.settings:id/proxy_port')
    proxy_save_btn = (AppiumBy.ID, 'android:id/button1')
    proxy_select = (AppiumBy.ID, 'android:id/text1')
    manual_option = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Manual")')


class AppiumldAuto:
    LDPLAYER9_DIR = r"E:\leidian\LDPlayer9" 
    appium_server_url = 'http://localhost:4723'
    capabilities = dict(
        platformName='Android',
        automationName='uiautomator2',
        deviceName='Android',
        language='en',
        locale='US',
        noReset=True
        )

    def __init__(self, username, code=None) -> None:
        self.username = username
        self.code = code
        # 启动模拟器、初始化 Appium 驱动
        self.start_device()
        self.driver = self.start_driver()

    def start_driver(self):
        try:
            driver = webdriver.Remote(self.appium_server_url, options=UiAutomator2Options().load_capabilities(self.capabilities))
            return driver
        except AppiumStartError as e:
            logger.error(f"模拟器启动失败: {e}")
            raise

    def start_device(self):
        try:
            logger.info(f"正在启动模拟器: {self.username}")
            result = subprocess.run(
                    f'dnconsole.exe launch --name "{self.username}"',
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

            # 检查模拟器是否打开成功
            if self._check_emulator_process():
                logger.info("模拟器启动成功")
                return True
            else:
                logger.error("模拟器启动失败")
                raise LdDeviceStartError("模拟器启动失败")
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
                    logger.info(f"模拟器 '{self.username}' 状态: 运行中 (检测到 {process_name})")
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
            self.driver.press_keycode(4)
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

            # 解锁图案的坐标点序列
            duration = 1000
            points_list = [(135, 566), (135, 691), (135, 827), (271, 827), (405, 827)]
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
            print(e)

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
                return False

            # 配置代理设置
            if not self._configure_proxy_settings(hostname, port):
                logger.error('配置代理设置失败')
                return False

            logger.info('代理设置完成')
            return True

        except ValueError as e:
            logger.error(f'参数验证失败: {e}')
            return False
        except Exception as e:
            logger.error(f'设置代理时发生错误: {e}')
            return False

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
            return True

        except Exception as e:
            logger.error(f'配置代理设置失败: {e}')
            return False

    def login_gamil(self):
        pass

    def install_apple(self):
        try:
            # 等待并点击Play Store应用
            logger.info("正在启动Play Store...")
            self._click_element((AppiumBy.ACCESSIBILITY_ID, 'Play Store'))
            time.sleep(3)  # 等待Play Store完全加载

            # 点击搜索按钮
            logger.info("正在点击搜索按钮...")
            self._click_element(
                (AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().className("android.view.View").instance(20)')
                )

            # 等待搜索输入框出现并输入搜索内容
            logger.info("正在输入搜索内容...")
            self._input_text(
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    'new UiSelector().className("android.widget.EditText")'
                ), 
                'apple music'
            )

            # 使用回车键搜索
            logger.info("正在执行搜索...")
            self.driver.press_keycode(66)  # 66是Android的KEYCODE_ENTER
            time.sleep(3)  # 等待搜索结果加载

            # 查找并点击Apple Music应用
            logger.info("正在查找Apple Music应用...")
            self._click_element((AppiumBy.ACCESSIBILITY_ID,'Apple Music\nApple\n'))
            time.sleep(2)

            # 点击安装按钮
            logger.info("正在点击安装按钮...")
            self._click_element(
                (AppiumBy.ANDROID_UIAUTOMATOR, 
                'new UiSelector().className("android.widget.Button").instance(0)')
                )

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
                        logger.info(f"下载进行中... ({(i+1)*5}秒)")
                    else:
                        logger.info(f"下载进行中... ({(i+1)*5}秒)")

                except Exception as e:
                    logger.info(f"检查下载状态时出错: {e}")

                time.sleep(5)

            if not download_complete:
                logger.info("⚠ 下载可能未完成，继续执行下一步...")

            # 返回桌面检查是否安装成功
            logger.info("下载完成，返回桌面检查安装状态...")
            self.return_to_home_and_check_installation()

        except TimeoutException as e:
            logger.warning(f"元素等待超时: {e}")
            raise
        except NoSuchElementException as e:
            logger.warning(f"元素未找到: {e}")
            raise
        except Exception as e:
            logger.warning(f"安装过程中出现错误: {e}")
            raise

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
    
    def run(self):
        try:
            self.unlock_device()
            self.set_proxy(port='7471')
            self.login_gamil()
            self.install_apple()
        except LdDeviceStartError:
            logger.warning(f'{self.username} 模拟器启动失败')
        except AppiumStartError:
            logger.warning(f'{self.username}Appium连接失败')

if __name__ == '__main__':
    ldauto = AppiumldAuto(username="adelineelizabeth20@gmail.com")
    ldauto.run()