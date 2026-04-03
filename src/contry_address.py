import yaml
import time
import json
import requests
from loguru import logger
from pathlib import Path
from bs4 import BeautifulSoup


# 新的数据源 URL
DATA_SOURCE_URL = "https://www.americaaddress.com/uploads/addressdata/{country}.js"
BASE_URL = "https://addressbritain.github.io"
headers = {
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
}


def get_country_list():
    """获取所有国家地址链接"""
    url = BASE_URL + "/"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 查找所有包含 -address/ 的链接
        links = soup.find_all('a', href=True)
        countries = []
        seen = set()
        for link in links:
            href = link.get('href')
            if href and '-address/' in href and href.count('/') <= 2:
                # 排除子页面（如英国的分省页面）
                if href.count('/') <= 1 or (href.count('/') == 2 and not href.startswith('http')):
                    if href not in seen:
                        # 提取国家名称
                        country_name = href.replace('-address/', '').replace('/', '')
                        countries.append({
                            'path': href,
                            'name': country_name
                        })
                        seen.add(href)

        return countries
    except Exception as e:
        logger.info(f"获取国家列表失败: {e}")
        return []


def fetch_address_data_from_js(country_name):
    """从JS文件获取地址数据"""
    url = DATA_SOURCE_URL.format(country=country_name)
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 提取JSON数据
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        
        if start >= 0 and end > start:
            json_str = text[start:end]
            data = json.loads(json_str)
            return data
        else:
            logger.warning(f"未找到 {country_name} 的地址数据")
            return []
            
    except requests.exceptions.RequestException as e:
        logger.info(f"请求失败: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return []


def extract_address_info(country_name):
    """提取网页中的地址信息（保留原有方法以兼容）"""
    url = f"{BASE_URL}/{country_name}-address/"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 查找所有地址块
        generators = soup.find_all('div', class_='result-box')
        address_info = []
        
        for generator in generators:
            try:
                info_detail = generator.find_all('dl')
                if len(info_detail) < 2:
                    continue
                address_detail = info_detail[1].find_all('dd')

                if len(address_detail) < 5:
                    continue

                street_address = address_detail[0].find('span').text.strip()
                city = address_detail[1].find('span').text.strip()
                fullname_state = address_detail[2].find('span').text.strip()
                zip_code = address_detail[3].find('span').text.strip()
                phone = address_detail[4].find('span').text.strip()

                address_info.append({
                    'Fullname_state': fullname_state,
                    'Street address': street_address,
                    'city': city,
                    'zip': zip_code,
                    'phone': phone
                })
            except Exception as e:
                logger.error(f"  解析地址块失败: {e}")
                continue

        return address_info
    except Exception as e:
        logger.info(f"请求失败: {e}")
        return []


def parse_js_data(data_list, country_name):
    """解析JS数据文件中的地址信息"""
    address_list = []
    
    for item in data_list:
        try:
            # 获取地址部分
            address_data = item.get('data', {}).get('RANDOM ADDRESS', [])
            
            # 提取各个字段
            street = ''
            city = ''
            state = ''
            zip_code = ''
            phone = ''
            
            for addr_item in address_data:
                key = addr_item.get('key', '')
                value = addr_item.get('value', '')
                key_name = addr_item.get('key_name', '')
                
                if '街道' in key_name:
                    street = value
                elif '城市' in key_name or '城市' in key:
                    city = value
                elif '州' in key_name or '省' in key:
                    state = value
                elif '邮' in key_name:
                    zip_code = value
                elif '电话' in key_name:
                    phone = value
            
            # # 也获取基本信息中的全名
            # basic_data = item.get('data', {}).get('基本资料', [])
            # fullname = ''
            # for basic_item in basic_data:
            #     if '全名' in basic_item.get('key', ''):
            #         fullname = basic_item.get('value', '')
            #         break
            
            if street or city or state:  # 至少有一个地址信息
                address_list.append({
                    'country': country_name,
                    'Fullname_state': state,
                    'Street address': street,
                    'city': city,
                    'zip': zip_code,
                    'phone': phone,
                    # 'fullname': fullname
                })
                
        except Exception as e:
            logger.error(f"解析数据失败: {e}")
            continue
    
    return address_list


def load_existing_data(filename):
    """加载已有数据"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or []
    except (FileNotFoundError, yaml.YAMLError):
        return []


def save_to_yaml(data, filename):
    """保存数据到 YAML 文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, indent=4)
    logger.info(f"数据已保存到 {filename}")


def merge_and_deduplicate(existing_data, new_data):
    """合并数据并去重"""
    valid_new_data = [item for item in new_data if item and isinstance(item, dict)]
    all_data = existing_data + valid_new_data
    unique_data = list({frozenset(item.items()): item for item in all_data}.values())
    return unique_data


def select_countries(countries):
    """让用户选择要抓取的国家"""
    print("\n" + "=" * 60)
    print("可用国家列表：")
    print("=" * 60)
    
    # 按字母顺序排序
    sorted_countries = sorted(countries, key=lambda x: x['name'].lower())
    
    # 显示国家列表
    for i, c in enumerate(sorted_countries, 1):
        print(f"{i:3}. {c['name']:<40}", end="")
        if i % 3 == 0:
            print()
    
    print("\n" + "=" * 60)
    print("请选择要抓取的国家（输入编号，多个用逗号分隔，输入 all 抓取全部）：")
    print("例如: 1,3,5 或 america,china,japan 或 all")
    print("=" * 60)
    
    selection = input("请输入: ").strip()
    
    if selection.lower() == 'all':
        return countries
    
    selected = []
    
    # 处理输入（支持编号和国家名称）
    selection = selection.replace('，', ',')  # 替换中文逗号
    parts = selection.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 尝试解析为数字
        try:
            idx = int(part)
            if 1 <= idx <= len(sorted_countries):
                selected.append(sorted_countries[idx - 1])
            else:
                logger.info(f"  警告: 编号 {idx} 超出范围，已跳过")
        except ValueError:
            # 不是数字，尝试匹配国家名称
            part_lower = part.lower()
            matched = [c for c in countries if c['name'].lower() == part_lower or c['name'].lower().replace('-', ' ') == part_lower.replace(' ', ' ')]
            if matched:
                selected.extend(matched)
            else:
                logger.info(f"  警告: 未找到国家 '{part}'，已跳过")
    
    # 去重
    seen = set()
    unique_selected = []
    for c in selected:
        if c['path'] not in seen:
            seen.add(c['path'])
            unique_selected.append(c)
    
    return unique_selected


if __name__ == "__main__":
    current_file_dir = Path(__file__).parent.parent
    save_dir = current_file_dir / "res"
    save_dir.mkdir(exist_ok=True)

    # 1. 获取所有国家列表
    logger.info("=" * 60)
    logger.info("正在获取国家列表...")
    countries = get_country_list()
    logger.info(f"找到 {len(countries)} 个国家地址")
    
    # 2. 让用户选择国家
    selected_countries = select_countries(countries)
    
    if not selected_countries:
        logger.info("未选择任何国家，程序退出")
        exit(0)
    
    logger.info(f"\n已选择 {len(selected_countries)} 个国家: {[c['name'] for c in selected_countries]}")

    # 3. 从JS数据源抓取每个国家的50条地址
    logger.info("\n" + "=" * 60)
    logger.info("开始从数据源抓取地址（每个国家50条）...")
    total = len(selected_countries)
    saved_count = 0

    for idx, country in enumerate(selected_countries, 1):
        country_name = country['name']
        
        logger.info(f"[{idx}/{total}] 正在抓取: {country_name}...", end=" ")

        # 从JS文件获取数据（每个国家50条）
        data_list = fetch_address_data_from_js(country_name)
        
        if data_list:
            # 解析数据
            data = parse_js_data(data_list, country_name)
            
            if data:
                # 每个国家保存到单独的 YAML 文件
                country_file = save_dir / f"{country_name}.yaml"
                
                # 如果文件已存在，先加载并合并
                existing_data = load_existing_data(country_file)
                
                # 合并新数据和已有数据
                merged_data = merge_and_deduplicate(existing_data, data)
                
                # 保存到以国家名命名的文件
                save_to_yaml(merged_data, country_file)
                
                logger.info(f"获取 {len(data)} 条，已保存到 {country_name}.yaml")
                saved_count += 1
            else:
                logger.info("解析数据失败")
        else:
            logger.info("无数据")

        # 避免请求过快
        time.sleep(0.3)

    logger.info(f"\n本次共抓取并保存了 {saved_count} 个国家的地址")
    logger.info(f"文件保存在: {save_dir}")
    logger.info("\n" + "=" * 60)
    logger.info("完成！")
