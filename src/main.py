import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / 'config'
DEFAULT_CONFIG = CONFIG_DIR / 'config.yaml'
def main():
    logging.info('AutoApp 启动成功')
    logging.info('当前配置路径: %s', DEFAULT_CONFIG)
    
    
    
if __name__ == '__main__':
    main()
