# 问卷星配置示例（请复制为 config.py 并按需填写）

config_data = {
    # 问卷链接
    "questionnaire_url": "https://www.wjx.cn/vm/your_form_id.aspx",

    # 提交次数与间隔
    "number_of_submissions": 5,
    "min_delay_seconds": 70.0,
    "max_delay_seconds": 180.0,

    # 浏览器设置
    "headless": False,
    "window_size": "390,844",
    "mobile_user_agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "chrome_binary_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "chromedriver_path": r"C:\Program Files\Google\Chrome\Application\chromedriver-win64\chromedriver.exe",
    "page_load_timeout_seconds": 20,
    "submit_button_timeout_seconds": 10,

    # 题目配置示例
    "questions": [
        {
            "id": "1",
            "description": "单选示例",
            "type": "single_choice_probabilities",
            "answer_logic": {
                "options_count": 3,
                "probabilities": [0.5, 0.3, 0.2]  # 概率和建议为 1
            },
        },
        {
            "id": "2",
            "description": "多选示例（独立概率命中 + 全空兜底选 1 项）",
            "type": "Multiple_choices_probabilities",
            "answer_logic": {
                "options_count": 4,
                "probabilities": [0.2, 0.4, 0.1, 0.3]  # 每项为独立入选概率
            },
        },
    ],
}

