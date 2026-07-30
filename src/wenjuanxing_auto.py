"""
问卷星自动填写脚本。

执行流程：
1. 读取问卷地址、提交次数和题目答题规则。
2. 根据随机范围或选项概率生成本轮答案。
3. 使用 Selenium 打开问卷并点击对应选项。
4. 提交问卷，等待人工处理可能出现的验证码。
5. 判断提交结果，并按设定的时间间隔重复执行。

当前仅支持普通单选题和多选题。
"""

import time
import random
import os
import logging
import importlib.util  # 用于从.py文件加载模块
import pprint  # 用于美化打印字典到文件

logger = logging.getLogger(__name__)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class WJXSubmitter:
    """负责浏览器初始化、答案生成、页面填写和循环提交。"""

    def __init__(self, config_dict):  # 构造函数接收整个配置字典
        # 保存完整配置，后续所有运行参数和答题规则均从这里读取。
        self.config = config_dict
        self.url = self.config.get("questionnaire_url")

        self.logger = logging.getLogger(__name__)

        # 页面元素的显式等待时间，单位为秒。
        self.page_load_timeout = self.config.get("page_load_timeout_seconds", 20)
        self.submit_button_timeout = self.config.get("submit_button_timeout_seconds", 10)

        # 浏览器实例统一在这里创建，程序结束时由 close_driver() 关闭。
        self.driver = None
        self._create_or_replace_driver()

    def _build_chrome_options(self):
        """根据配置生成 Chrome 浏览器启动参数。"""
        options = webdriver.ChromeOptions()

        # 无头模式不会显示浏览器窗口，调试时建议关闭。
        if self.config.get("headless"):
            options.add_argument('--headless')

        # 可自定义浏览器标识；默认配置通常使用移动端 UA。
        mobile_ua = self.config.get("mobile_user_agent")
        if mobile_ua:
            options.add_argument(f"user-agent={mobile_ua}")

        # 窗口尺寸可配置，默认移动端尺寸
        window_size = self.config.get("window_size", "390,844")
        options.add_argument(f'--window-size={window_size}')

        # 二进制与 driver 路径可从配置读取，若不存在则给出提示
        chrome_binary_path = self.config.get("chrome_binary_path", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if os.path.exists(chrome_binary_path):
            options.binary_location = chrome_binary_path
        else:
            self.logger.warning(f"chrome_binary_path 不存在: {chrome_binary_path}")

        return options

    def _create_or_replace_driver(self):
        """根据当前配置创建或替换 driver。"""
        # 重建浏览器前先关闭旧实例，避免残留 Chrome 进程。
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.warning(f"关闭旧浏览器时发生错误: {e}")

        options = self._build_chrome_options()

        driver_path = self.config.get("chromedriver_path", r"C:\Program Files\Google\Chrome\Application\chromedriver-win64\chromedriver.exe")
        if not os.path.exists(driver_path):
            self.logger.warning(f"chromedriver_path 不存在: {driver_path}")

        service = ChromeService(executable_path=driver_path) if os.path.exists(driver_path) else ChromeService()
        self.driver = webdriver.Chrome(service=service, options=options)

        # 页面脚本执行前调整部分 navigator 属性，使语言和插件信息保持一致。
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                if (navigator.languages && !navigator.languages.includes('zh-CN')) {
                    Object.defineProperty(navigator, "languages", { get: () => ["zh-CN", "zh"] });
                }
                if (navigator.plugins && navigator.plugins.length === 0) {
                     Object.defineProperty(navigator, "plugins", { get: () => [1, 2, 3] }); // 简单伪造
                }
            """
        })
        self.generated_answers_cache = {}  # 用于存储已生成的答案，供条件问题判断

    def get_random_int(self, min_val, max_val):
        """生成包含上下限的随机整数，例如 1～3 会返回 1、2 或 3。"""
        return random.randint(min_val, max_val)

    def get_random_answer_by_probabilities(self, probabilities):
        """
        根据概率列表选择一个选项，返回从 1 开始的选项编号。

        例如 [0.2, 0.3, 0.5] 分别对应选项 1、2、3。
        如果累计概率不足 1，剩余概率会落到最后一个选项。
        """
        rand = random.random()
        cumulative_probability = 0
        for i, prob in enumerate(probabilities):
            cumulative_probability += prob
            if rand < cumulative_probability:
                return i + 1
        return len(probabilities)  # 容错处理

    def generate_answers_from_config(self):
        """
        根据 questions 配置生成本轮提交使用的全部答案。

        单选题答案保存为字符串，例如 "2"；
        多选题答案保存为字符串列表，例如 ["1", "3"]。
        """
        self.generated_answers_cache = {}  # 清空缓存
        question_configs = self.config.get("questions", [])

        for q_config in question_configs:
            q_id = q_config.get("id")
            q_type = q_config.get("type")
            answer_logic = q_config.get("answer_logic", {})
            answer = None

            # 单选题：在 min～max 范围内等概率选择一个选项。
            if q_type == "single_choice_random_int":
                min_val = answer_logic.get("min")
                max_val = answer_logic.get("max")
                if min_val is not None and max_val is not None:
                    answer = str(self.get_random_int(min_val, max_val))
                else:
                    self.logger.warning(f"问题 {q_id} (类型: {q_type}) 的 answer_logic 缺少 min 或 max。")
            # 单选题：按照 probabilities 中配置的概率选择一个选项。
            elif q_type == "single_choice_probabilities":
                probabilities = answer_logic.get("probabilities")
                options_count = answer_logic.get("options_count")
                if probabilities and options_count and len(probabilities) == options_count:
                    answer = str(self.get_random_answer_by_probabilities(probabilities))
                else:
                    self.logger.warning(
                        f"问题 {q_id} (类型: {q_type}) 的概率配置错误 (probabilities长度与options_count不匹配或缺失)。")
            # 多选题：先随机决定选择数量，再从范围内无重复抽取选项。
            elif q_type == "Multiple_choices_random_int":
                min_val = answer_logic.get("min")
                max_val = answer_logic.get("max")
                if min_val is not None and max_val is not None:
                    num_choices = self.get_random_int(1, max_val - min_val + 1)
                    answer = [str(i) for i in random.sample(range(min_val, max_val + 1), num_choices)]
                else:
                    self.logger.warning(f"问题 {q_id} (类型: {q_type}) 的 answer_logic 缺少 min 或 max。")
            # 多选题：每个选项独立按照自身概率判断是否入选。
            elif q_type == "Multiple_choices_probabilities":
                probabilities = answer_logic.get("probabilities")
                options_count = answer_logic.get("options_count")
                if probabilities and options_count and len(probabilities) == options_count:
                    answer = []
                    for i in range(options_count):
                        if random.random() < probabilities[i]:
                            answer.append(str(i + 1))
                    if not answer:
                        # 禁止空选：全部选项都未命中时，随机补选一个。
                        answer = [str(self.get_random_int(1, options_count))]
            else:
                self.logger.warning(f"问题 {q_id} 的类型 '{q_type}' 未知或未实现。")

            # 只有成功生成的答案才写入缓存，条件题判断也使用此缓存。
            if answer is not None:
                self.generated_answers_cache[q_id] = answer
            else:
                self.logger.info(f"问题 {q_id} 未能生成答案。")

        self.logger.info(f"根据配置生成的答案集: {self.generated_answers_cache}")
        return self.generated_answers_cache

    def check_condition(self, condition_config):
        """检查条件题的前置题答案是否满足显示条件。"""
        # 未提供条件配置时，按“满足条件”处理。
        if not condition_config:
            return True

        on_question_id = condition_config.get("on_question_id")
        required_answers = condition_config.get("is_one_of_answers", [])

        actual_answer = self.generated_answers_cache.get(on_question_id)

        if actual_answer is None:
            # print(f"调试：条件判断失败，因为前置问题 {on_question_id} 没有生成答案。")
            return False

        # 当前比较方式主要适用于前置题为单选题的情况。
        return actual_answer in required_answers

    def fill_question(self, question_id_num_str, answer_index_str):
        """
        点击一道单选题或多选题的答案。

        question_id_num_str 是问卷题号；
        answer_index_str 可以是单个选项编号，也可以是多选编号列表。
        """
        try:
            # 根据题号和选项号，拼接问卷星常见 label 结构的 XPath。
            option_xpath_lst = []
            if isinstance(answer_index_str, list):
                for q_id in answer_index_str:
                    option_xpath = f"//div[@id='div{question_id_num_str}']//div[@class='label'][@for='q{question_id_num_str}_{q_id}']"
                    option_xpath_lst.append(option_xpath)
            else:
                option_xpath = f"//div[@id='div{question_id_num_str}']//div[@class='label'][@for='q{question_id_num_str}_{answer_index_str}']"
                option_xpath_lst.append(option_xpath)
            for op_xpath in option_xpath_lst:
                # 等待选项可点击，滚动到屏幕中间后再执行点击。
                option_element = WebDriverWait(self.driver, 7).until(
                    EC.element_to_be_clickable((By.XPATH, op_xpath))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                                           option_element)
                time.sleep(0.2)  # 等待滚动动画（如果有）
                option_element.click()
                time.sleep(random.uniform(0.3, 0.7))
            return True
        except TimeoutException:
            # print(f"调试信息: 问题 div{question_id_num_str} 的选项 q{question_id_num_str}_{answer_index_str} 未找到或不可点击。")
            return False
        except Exception as e:
            self.logger.error(f"填写问题 div{question_id_num_str} 时发生错误: {e}")
            return False

    def submit_once(self):
        """完成一次“打开问卷—生成答案—填写—提交—判断结果”的流程。"""
        # 第一步：打开问卷，并等待第一题出现在页面中。
        self.driver.get(self.url)
        try:
            WebDriverWait(self.driver, self.page_load_timeout).until(EC.presence_of_element_located((By.ID, "div1")))
            self.logger.info("问卷页面加载成功。")
        except TimeoutException:
            self.logger.error("错误: 问卷页面加载超时，尝试刷新。")
            self.driver.refresh()
            time.sleep(5)
            try:
                WebDriverWait(self.driver, self.page_load_timeout).until(EC.presence_of_element_located((By.ID, "div1")))
                self.logger.info("问卷页面加载成功 (刷新后)。")
            except TimeoutException:
                self.logger.error("错误: 问卷页面加载超时 (刷新后仍然失败)。")
                return False

        # 第二步：为本轮提交重新生成一套随机答案。
        self.generate_answers_from_config()

        question_configs = self.config.get("questions", [])
        questions_filled_count = 0
        questions_attempted_to_fill = 0

        # 第三步：按照配置顺序逐题判断条件并填写。
        for q_config in question_configs:
            q_id = q_config.get("id")
            answer_to_fill = self.generated_answers_cache.get(q_id)

            if answer_to_fill is None:
                continue

            is_conditional = q_config.get("is_conditional", False)
            condition_met = True

            if is_conditional:
                condition_config = q_config.get("condition")
                if not self.check_condition(condition_config):
                    condition_met = False

            if condition_met:
                questions_attempted_to_fill += 1
                if self.fill_question(q_id, answer_to_fill):
                    questions_filled_count += 1
                else:
                    self.logger.warning(f"问题 div{q_id} 未能成功填写 (可能是实际隐藏或页面结构不匹配)。")

        self.logger.info(f"成功填写 {questions_filled_count}/{questions_attempted_to_fill} 个激活且配置了答案的问题。")

        # 第四步：找到提交按钮并提交问卷。
        try:
            submit_button = WebDriverWait(self.driver, self.submit_button_timeout).until(
                EC.element_to_be_clickable((By.ID, "ctlNext"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", submit_button)
            time.sleep(random.uniform(3.0, 5.0))  # 提交后等待

            captcha_intervened = False  # 标记是否已因验证码暂停过

            # 第五步：检测 Layui 验证码弹窗，发现后最多等待 5 分钟供人工处理。
            layui_captcha_xpaths = [
                "//div[contains(@class, 'layui-layer-dialog')]//div[@class='layui-layer-content' and contains(text(), '请在当前设备完成验证！')]",
                "//div[contains(@class, 'layui-layer-dialog')]//div[contains(., '点击按钮开始智能验证')]",
                "//div[contains(@class, 'layui-layer') and contains(@class,'layui-layer-dialog')]//div[contains(text(),'智能验证')]"
            ]
            for xpath_str in layui_captcha_xpaths:
                try:
                    layui_dialog_element = self.driver.find_element(By.XPATH, xpath_str)
                    if layui_dialog_element.is_displayed():
                        self.logger.info("检测到弹窗式验证码。需要手动处理。脚本将暂停（最多5分钟）。")
                        captcha_intervened = True
                        main_layui_layer = layui_dialog_element.find_element(By.XPATH,
                                                                             "./ancestor::div[contains(@class, 'layui-layer') and @times]")
                        layer_times_id = main_layui_layer.get_attribute("times")
                        WebDriverWait(self.driver, 300).until_not(
                            EC.presence_of_element_located(
                                (By.XPATH, f"//div[contains(@class, 'layui-layer') and @times='{layer_times_id}']"))
                        )
                        self.logger.info("Layui 验证码弹窗似乎已处理或超时。")
                        time.sleep(2)
                        break
                except NoSuchElementException:
                    continue
                except Exception as e_layui_wait:
                    self.logger.error(f"处理 Layui 弹窗时发生错误或超时: {e_layui_wait}")
                    captcha_intervened = True  # 即使等待出错，也标记为已干预
                    break

            current_url = self.driver.current_url
            page_source = self.driver.page_source

            # 第六步：通过跳转地址和页面提示文字判断提交结果。
            if "aspx?activity" in current_url or "submit_successfully.aspx" in current_url or "感谢您的参与" in page_source:
                self.logger.info("问卷提交成功！")
                return True
            elif "您提交的太快了" in page_source:
                self.logger.warning("提交失败：您提交的太快了，请稍后再试。")
                return False
            elif "此IP在一定时间内不允许再提交" in page_source:
                self.logger.warning("提交失败：此IP在一定时间内不允许再提交。")
                return False
            elif captcha_intervened:  # 如果之前处理过验证码，但结果仍未知
                self.logger.warning("验证码已处理（或超时），但提交后页面状态仍不确定。请检查。")
                return False
            else:  # 没有特定错误信息，也没有成功标志，也不是已知验证码干预后的情况
                error_msg_elements = self.driver.find_elements(By.XPATH,
                                                               "//div[contains(@class, 'errorMessage') or contains(@class, 'error-message')]")
                for err_el in error_msg_elements:
                    if err_el.is_displayed() and err_el.text.strip():
                        self.logger.warning(f"提交失败，问卷页面错误信息：{err_el.text.strip()}")
                        return False
                self.logger.warning("提交状态未知。可能原因：未处理的验证码、提交后页面不符合预期、或网络问题。")
                return False

        except TimeoutException:
            self.logger.error("错误: 提交按钮超时未找到或不可点击。")
            return False
        except Exception as e:
            self.logger.error(f"提交过程中发生错误: {e}")
            return False

    def close_driver(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("浏览器已关闭。")
            except Exception as e:
                self.logger.error(f"关闭浏览器时发生错误: {e}")
            finally:
                # 清空引用，避免主程序 finally 阶段重复关闭同一个浏览器。
                self.driver = None

    def run_loop(self, stop_event=None, progress_callback=None):
        """
        按照提交次数和随机时间间隔，循环执行 submit_once()。

        stop_event 用于图形界面请求停止；不传时保持原命令行行为。
        progress_callback 会在每次尝试结束后接收：
        (已完成次数, 总次数, 成功次数)。
        """
        num_submissions = self.config.get("number_of_submissions", 1)
        min_delay = self.config.get("min_delay_seconds", 60)
        max_delay = self.config.get("max_delay_seconds", 180)

        successful_submissions = 0
        completed_submissions = 0
        for i in range(num_submissions):
            if stop_event is not None and stop_event.is_set():
                self.logger.info("收到停止请求，不再开始新的提交。")
                break

            self.logger.info(f"--- 开始第 {i + 1}/{num_submissions} 次提交 ---")

            try:
                if self.submit_once():
                    successful_submissions += 1
                else:
                    self.logger.warning(f"第 {i + 1} 次提交失败。")
            except Exception as e:
                self.logger.error(f"在第 {i + 1} 次提交过程中发生意外错误: {e}")
                self.close_driver()  # 确保driver被关闭
                if stop_event is not None and stop_event.wait(10):
                    self.logger.info("等待恢复期间收到停止请求。")
                    completed_submissions = i + 1
                    if progress_callback:
                        progress_callback(completed_submissions, num_submissions, successful_submissions)
                    break
                if stop_event is None:
                    time.sleep(10)
                self.logger.info("尝试重新初始化浏览器...")
                # 使用原配置重新初始化当前对象和浏览器。
                self.__init__(self.config)  # 使用保存的config重新初始化

            completed_submissions = i + 1
            if progress_callback:
                progress_callback(completed_submissions, num_submissions, successful_submissions)

            if i < num_submissions - 1:
                # 两次提交之间加入随机延时。
                delay = random.uniform(min_delay, max_delay)
                self.logger.info(f"等待 {delay:.2f} 秒后进行下一次提交...")
                if stop_event is not None:
                    if stop_event.wait(delay):
                        self.logger.info("等待下一次提交期间收到停止请求。")
                        break
                else:
                    time.sleep(delay)
        self.logger.info(
            f"--- 循环提交结束 --- 已完成: {completed_submissions}/{num_submissions}, "
            f"成功: {successful_submissions}"
        )
        self.close_driver()
        return successful_submissions


def generate_config_interactively():
    """通过命令行逐项询问参数，并生成 config.py 配置文件。"""
    logger.info("--- 开始配置问卷信息 ---")
    new_config_data = {}
    new_config_data["questionnaire_url"] = input("请输入问卷的完整URL链接: ").strip()
    while True:
        try:
            num_sub = input("请输入希望自动提交的总次数 (例如 3, 默认为1): ").strip()
            new_config_data["number_of_submissions"] = int(num_sub) if num_sub else 1
            if new_config_data["number_of_submissions"] > 0:
                break
            else:
                logger.warning("提交次数必须大于0。")
        except ValueError:
            logger.warning("请输入有效的数字。")

    default_ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    ua_input = input(f"请输入手机User-Agent (直接回车使用默认值: '{default_ua}'): ").strip()
    new_config_data["mobile_user_agent"] = ua_input if ua_input else default_ua

    while True:
        try:
            min_d = input("最小延时(秒，例如 70, 默认为70): ").strip()
            new_config_data["min_delay_seconds"] = float(min_d) if min_d else 70.0
            break
        except ValueError:
            logger.warning("请输入有效数字。")
    while True:
        try:
            max_d = input("最大延时(秒，例如 180, 默认为180): ").strip()
            new_config_data["max_delay_seconds"] = float(max_d) if max_d else 180.0
            break
        except ValueError:
            logger.warning("请输入有效数字。")
    if new_config_data["max_delay_seconds"] < new_config_data["min_delay_seconds"]:
        logger.warning("警告：最大延时小于最小延时，已将最大延时设为与最小延时相同。")
        new_config_data["max_delay_seconds"] = new_config_data["min_delay_seconds"]

    questions = []
    logger.info("--- 开始配置问卷问题 ---")
    q_counter = 1
    while True:
        q_id_default_prompt = f" (例如 '{q_counter}', 输入 'done' 或直接回车结束添加)"
        q_id = input(f"请输入问题 {q_counter} 的ID{q_id_default_prompt}: ").strip()
        if not q_id or q_id.lower() == 'done':
            if not questions:  # 如果一个问题都没添加，提示一下
                if input("您还没有添加任何问题。确定要结束问题配置吗？(是/否): ").strip().lower() in ['是', 'y', 'yes']:
                    break
                else:
                    continue
            break

        q_config = {"id": q_id}
        q_config["description"] = input(f"  问题 {q_id} 的描述 (可选，例如 '性别'): ").strip()

        logger.info("  请选择问题类型:")
        logger.info("    1: 单选 - 随机整数 (选项值为1,2,3...)")
        logger.info("    2: 单选 - 按概率选择")
        logger.info("    3: 多选 - 随机整数 (选项值为1,2,3...)")
        logger.info("    4: 多选 - 按概率选择")
        # print("    (未来可支持更多类型，如文本输入等)")
        q_type_choice = ""
        while q_type_choice not in ["1", "2", "3", "4"]:
            q_type_choice = input("  请输入类型编号 (1或2): ").strip()

        answer_logic = {}
        if q_type_choice == "1":
            q_config["type"] = "single_choice_random_int"
            while True:
                try:
                    answer_logic["min"] = int(input(f"    问题 {q_id} - 随机整数的最小值 (例如 1): ").strip())
                    break
                except ValueError:
                    logger.warning("    请输入有效数字。")
            while True:
                try:
                    answer_logic["max"] = int(input(f"    问题 {q_id} - 随机整数的最大值 (例如 2): ").strip())
                    break
                except ValueError:
                    logger.warning("    请输入有效数字。")
        elif q_type_choice == "2":
            q_config["type"] = "single_choice_probabilities"
            while True:
                try:
                    options_count_str = input(f"    问题 {q_id} - 总共有几个选项 (例如 5): ").strip()
                    options_count = int(options_count_str)
                    if options_count > 0:
                        break
                    else:
                        logger.warning("    选项数量必须大于0。")
                except ValueError:
                    logger.warning("    请输入有效的数字。")
            answer_logic["options_count"] = options_count
            probabilities = []
            prob_sum = 0.0
            logger.info(f"    请为问题 {q_id} 的 {options_count} 个选项输入概率 (小数形式，如0.2):")
            for i in range(options_count):
                while True:
                    try:
                        prob_str = input(f"      选项 {i + 1} 的概率 (不想选填0.0): ").strip()
                        prob = float(prob_str)
                        if 0.0 <= prob <= 1.0:
                            probabilities.append(prob)
                            prob_sum += prob
                            break
                        else:
                            logger.warning("      概率必须在0.0和1.0之间。")
                    except ValueError:
                        logger.warning("      请输入有效的浮点数。")

            # 检查概率和是否接近1 (允许一定误差)
            if not (abs(prob_sum - 1.0) < 0.01 or (prob_sum == 0 and options_count > 0)):
                logger.warning(f"    问题 {q_id} 的概率总和为 {prob_sum:.3f}，不为1。请仔细检查。")
            answer_logic["probabilities"] = probabilities
        elif q_type_choice == "3":
            q_config["type"] = "Multiple_choices_random_int"
            while True:
                try:
                    answer_logic["min"] = int(input(f"    问题 {q_id} - 随机整数的最小值 (例如 1): ").strip())
                    break
                except ValueError:
                    logger.warning("    请输入有效数字。")
            while True:
                try:
                    answer_logic["max"] = int(input(f"    问题 {q_id} - 随机整数的最大值 (例如 2): ").strip())
                    break
                except ValueError:
                    logger.warning("    请输入有效数字。")
        elif q_type_choice == "4":
            q_config["type"] = "Multiple_choices_probabilities"
            while True:
                try:
                    options_count_str = input(f"    问题 {q_id} - 总共有几个选项 (例如 5): ").strip()
                    options_count = int(options_count_str)
                    if options_count > 0:
                        break
                    else:
                        logger.warning("    选项数量必须大于0。")
                except ValueError:
                    logger.warning("    请输入有效的数字。")
            answer_logic["options_count"] = options_count
            probabilities = []
            prob_sum = 0.0
            logger.info(f"    请为问题 {q_id} 的 {options_count} 个选项输入概率 (小数形式，如0.2):")
            for i in range(options_count):
                while True:
                    try:
                        prob_str = input(f"      选项 {i + 1} 的概率 (不想选填0.0): ").strip()
                        prob = float(prob_str)
                        if 0.0 <= prob <= 1.0:
                            probabilities.append(prob)
                            prob_sum += prob
                            break
                        else:
                            logger.warning("      概率必须在0.0和1.0之间。")
                    except ValueError:
                        logger.warning("      请输入有效的浮点数。")

            # 检查概率和是否接近1 (允许一定误差)
            if not (abs(prob_sum - 1.0) < 0.01 or (prob_sum == 0 and options_count > 0)):
                logger.warning(f"    问题 {q_id} 的概率总和为 {prob_sum:.3f}，不为1。请仔细检查。")
            answer_logic["probabilities"] = probabilities
        q_config["answer_logic"] = answer_logic

        is_cond_input = input(f"  问题 {q_id} 是否为条件问题? (是/否，默认为否): ").strip().lower()
        if is_cond_input in ['是', 'y', 'yes']:
            q_config["is_conditional"] = True
            cond_on_q = input("    依赖于哪个前置问题的ID? (例如 '3'): ").strip()
            cond_answers_str = input("    前置问题的哪些答案会触发此问题? (答案值用英文逗号隔开，例如 '1,2'): ").strip()
            q_config["condition"] = {
                "on_question_id": cond_on_q,
                "is_one_of_answers": [ans.strip() for ans in cond_answers_str.split(',')]
            }
        questions.append(q_config)
        logger.info(f"  问题 {q_id} 添加完毕。")
        q_counter += 1

    new_config_data["questions"] = questions

    config_content = "# 问卷星配置文件 (由此脚本自动生成或手动编辑)\n\n"
    # 使用 pprint.pformat 来格式化字典，使其更易读
    config_content += f"config_data = {pprint.pformat(new_config_data, indent=2, width=120, sort_dicts=False)}\n"  # sort_dicts=False 保持顺序

    try:
        with open("config.py", "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info("--- 配置文件 config.py 已成功生成在脚本同目录下！ ---")
        logger.info("您可以再次运行脚本以使用新配置，或手动修改 config.py 以调整。")
        return new_config_data
    except IOError:
        logger.error("错误：无法写入配置文件 config.py。请检查目录权限。")
        return None


def load_config_from_py(config_path="config.py"):
    """从指定 Python 文件加载名为 config_data 的配置字典。"""
    if not os.path.exists(config_path):
        logger.info(f"提示: 配置文件 {config_path} 未找到。")
        return None
    try:
        spec = importlib.util.spec_from_file_location("config_module", config_path)
        if spec is None or spec.loader is None:  # 检查 spec 和 loader 是否有效
            logger.error(f"错误: 无法为 {config_path} 创建模块规范。")
            return None
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)

        if hasattr(config_module, 'config_data'):
            logger.info(f"配置文件 {config_path} 加载成功。")
            return config_module.config_data
        else:
            logger.error(f"错误: 配置文件 {config_path} 中未找到 'config_data' 字典。")
            return None
    except Exception as e:
        logger.error(f"加载配置文件 {config_path} 时发生错误: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    config_file_name = r"F:\project\AutoApp\config\config.py"
    current_config = load_config_from_py(config_file_name)

    if current_config is None:
        logger.info("将开始引导您创建配置文件。")
        if input("是否现在开始创建新的配置文件 config.py? (是/否): ").strip().lower() in ['是', 'y', 'yes']:
            current_config = generate_config_interactively()
        else:
            logger.info("已取消配置生成。脚本将退出。")
            # current_config 保持为 None

    if current_config:  # 只有当配置加载或生成成功时才继续
        logger.info("--- 使用以下配置运行脚本 ---")
        logger.info(f"问卷URL: {current_config.get('questionnaire_url')}")
        logger.info(f"提交次数: {current_config.get('number_of_submissions')}")
        logger.info("-----------------------------")

        submitter = None  # 先声明
        try:
            submitter = WJXSubmitter(current_config)
            submitter.run_loop()
        except KeyboardInterrupt:
            logger.info("用户手动中断了脚本执行。")
        except Exception as e:
            logger.error(f"脚本运行过程中发生致命错误: {e}")
        finally:
            if submitter and hasattr(submitter, 'driver') and submitter.driver:
                submitter.close_driver()
            elif not submitter and current_config:  # 如果submitter对象未成功创建但配置存在
                logger.error("WJXSubmitter对象未成功初始化。")
    else:
        logger.info("未能加载或生成有效配置，脚本将退出。")
