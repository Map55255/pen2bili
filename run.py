import asyncio
import aiohttp
import json
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os
import nest_asyncio
import re
import requests
import shutil
import sys
import argparse

nest_asyncio.apply()

today = datetime.now().strftime('%Y-%m-%d')
 from cryptography.fernet import Fernet
import argparse
import base64
parser = argparse.ArgumentParser()
parser.add_argument('--encode_code', required=True, help='The encryption password')
#args = parser.parse_args(['--encode_code', OStTDgda8RCfNXo-RJVQI0GADC7Cm2A5unuy7S6wmIE=''])

key_bytes = (args.encode_code.encode())
fernet = Fernet(key_bytes)
cookie_file_path = 'cookie.env'
print(f"key_bytes", key_bytes)
if os.path.exists(cookie_file_path):
    with open(cookie_file_path, 'r') as env_file:
        for line in env_file:
            #print(line)
        #    line = line.decode('utf-8')
            key, encrypted_value = line.strip().split('=', 1)
            if encrypted_value.startswith("b'") and encrypted_value.endswith("'"):
                encrypted_value = encrypted_value[2:-1]

            if key == 'SESSDATA':
                sessdata = fernet.decrypt(encrypted_value).decode()

               # print(f"解码sessdata", sessdata)
            elif key == 'BIILI_JCT':
                bili_jct = fernet.decrypt(encrypted_value).decode()
            elif key == 'REFRESH_TOKEN':
                refresh_token = fernet.decrypt(encrypted_value).decode()
                

data_file_path = 'data.json'
image_directory = 'covers' #路径

async def fetch_product_list(session, nonce, work_id, semaphore):
    async with semaphore:
        product_list_url = f"https://prhcomics.com/wp/wp-admin/admin-ajax.php"
        post_data = {
            'product_load_nonce': nonce,
            'action': 'get_product_list',
            'postType': 'page',
            'postId': '11538',
            'isbns': '[]',
            'filters': '{"l1_category":"all-categories-manga","filters":{"category":[],"sale-status":[{"label":"Coming Soon","filterId":"sale-status","key":"onSaleFrom","value":"tomorrow"}],"format":[],"age":[],"grade":[],"guides":[],"publisher":[],"comics_publisher":[]}}',
            'layout': 'grid-lg',
            'start': work_id,  # 使用work_id作为start值
            'rows': 36,
            'sort': 'frontlistiest_onsale:desc',
            'params': '%7B%22source-page%22%3A%22category-landing-page%22%7D'
        }
       # print(work_id)
        async with session.post(product_list_url, data=post_data) as response:
            text_content = await response.text()
        #   print(text_content)

            # 尝试解析响应为JSON
            try:
                parsed_json = json.loads(text_content)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                parsed_json = None

            # 如果解析成功，使用正则表达式查找所有ISBN
            if parsed_json:
                content = parsed_json.get('data', {}).get('content', '')
                isbn_pattern = r'data-isbn="(\d+)"'
                isbns = re.findall(isbn_pattern, content)
                if isbns:
                    print("ISBNs found:")
                    for isbn in isbns:
                        print(isbn)
                    return isbns
                else:
                    print("No ISBNs found in the response.")
                    return None, False
            else:
                print("Failed to parse JSON.")
                return None, False

            # 返回ISBN列表
            return isbns if isbns else None

async def fetch_cover_md5(session, isbn, semaphore):
  async with semaphore:
    cover_url = f"https://images2.penguinrandomhouse.com/cover/{isbn}?height=1"
    async with session.get(cover_url) as response:
        if response.status == 200:
            data = await response.read()
            return hashlib.md5(data).hexdigest()
        else:
            return None

async def download_cover_image(session, isbn, semaphore):
  async with semaphore:
    cover_url = f"https://images2.penguinrandomhouse.com/cover/tif/{isbn}"
    async with session.get(cover_url) as response:
        if response.status == 200:
            data = await response.read()
            with open(f"{image_directory}/{isbn}.tif.{today}", 'wb') as f:
               # print(f"ok")
                f.write(data)
            return True
        else:
            return False
group_A = set() # 新增
group_B = set() #改变

async def main():
#   group_A = set() # 新增
#   group_B = set() #改变
    nonce_url = 'https://prhcomics.com/wp/wp-admin/admin-ajax.php?action=get_nonce'
    response = requests.get(nonce_url)
    nonce = response.text.strip()
    nonce = json.loads(nonce)
    nonce = nonce['nonce']  # 假设响应内容是直接包含nonce的文本

    if not os.path.exists(image_directory):
        os.makedirs(image_directory)

    if os.path.exists(data_file_path):
        with open(data_file_path, 'r') as f:
            data = json.load(f)
    else:
        data = {}

    semaphore = asyncio.Semaphore(100)  # 限制并发量为100

    async with aiohttp.ClientSession() as session:
        start = 0
        changed_isbns = set()  #
        all_valid_isbns = []  # 用于存储所有有效的ISBN
        finished = False  # 标记是否应该停止遍历

        while not finished:
            tasks = []
            # 创建任务时，确保 work_id 每次增加36
            for i in range(1):
                work_id = start + i * 36
                tasks.append(fetch_product_list(session, nonce, work_id, semaphore))

            isbns_lists = await asyncio.gather(*tasks)

            # 合并并过滤出有效的ISBN列表
            valid_isbns = [isbn for sublist in isbns_lists for isbn in sublist if sublist]
            all_valid_isbns.extend(valid_isbns)  # 将找到的ISBN添加到所有ISBN列表中

            # 如果这次没有找到任何ISBN，则停止遍历
            if not valid_isbns:
                finished = True
            else:
                # 增加 start 值，准备下一次循环
                start += 36

        # 在循环结束后，下载所有找到的ISBN的封面和MD5
            md5_tasks = [fetch_cover_md5(session, isbn, semaphore) for isbn in all_valid_isbns if isbn]
            md5_results = await asyncio.gather(*md5_tasks)
            # 更新数据字典
            for isbn, md5 in zip(all_valid_isbns, md5_results):
                if md5:
                 if isbn not in data:
                  print(f"不在", isbn)
                  group_A.add(isbn)
                  print(group_A)
                  data[isbn] = [{'date': today, 'md5': md5}]
                  changed_isbns.add(isbn)  # 如果MD5没有，添加到集合中
                 else:
        # Check if the last entry for the isbn has a different md5
                   if data[isbn][-1]['md5'] != md5:
                    group_B.add(isbn)
                    data[isbn].append({'date': today, 'md5': md5})
                    changed_isbns.add(isbn)  # 如果MD5改变，添加到集合中


            # 保存更新后的数据
            with open(data_file_path, 'w') as f:
                json.dump(data, f, indent=4)
                print(f"dump to {data_file_path}")
            for isbn in changed_isbns:
                file_count = len([f for f in os.listdir(image_directory) if f.startswith(isbn)])
                if data[isbn][-1]['date'] == today and file_count < len(data[isbn]):
                    await download_cover_image(session, isbn, semaphore)

            # 增加 start 值，准备下一次循环
         #  start += 36 * 36
            break

# 运行主函数
asyncio.run(main())


import getpass
import os
import subprocess
"""
parser = argparse.ArgumentParser(description='Process some integers.')
# 添加 --token 参数
parser.add_argument('--token', type=str, help='The token to be used')

# 解析命令行参数
args = parser.parse_args()

# 获取命令行传入的 token 参数值
account_name = args.token


# note: to automate this step, inject this env var into your container from a k8s Secret
os.environ["HF_TOKEN"] = account_name

subprocess.run(f'huggingface-cli login --token={os.environ["HF_TOKEN"]}',
               shell=True)

from huggingface_hub import HfApi

api = HfApi()
model_repo_name = "haibaraconan/tif"  # Format of Input  <Profile Name > / <Model Repo Name>

#Create Repo in Hugging Face
folder_path = image_directory
#Upload Model folder from Local to HuggingFace
api.upload_folder(
    folder_path=folder_path,
    repo_id=model_repo_name,
    repo_type="dataset"
)

# Publish Model Tokenizer on Hugging Face

shutil.rmtree(image_directory)
print(f"success")
"""
####

import os
import requests
import subprocess
import json
class ImageInfo:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
uploaded_images_info = []
# 设置缓存目录和图片下载URL模板
cache_directory = 'cache' #路径
image_url_template = 'https://images1.penguinrandomhouse.com/cover/700jpg/{}'
if not os.path.exists(cache_directory):
        os.makedirs(cache_directory)

# 下载图片并获取文件路径
 
import os
import requests

def download_image(isbn, cache_dir):
    image_url = image_url_template.format(isbn)
    image_filename = f"{isbn}.jpg"
    file_path = os.path.join(cache_dir, image_filename)

    # 发送请求下载图片
    response = requests.get(image_url)
    if response.status_code == 200:
        # 检查图片大小是否大于15KB
        if len(response.content) > 15 * 1024:  # 15KB
            with open(file_path, 'wb') as f:
                f.write(response.content)
            return file_path
        else:
            # 图片小于15KB，跳过不保存
            print(f"Image for ISBN: {isbn} is less than 15KB, skipping.")
            return None
    else:
        print(f"Failed to download image for ISBN: {isbn}")
        return None
 
# 上传图片
def upload_image(file_path, sessdata, bili_jct):
    preupload_image = f"curl 'https://api.bilibili.com/x/dynamic/feed/draw/upload_bfs' " \
                      f"-F 'file_up=@{file_path}' " \
                      f"-F 'category=daily' " \
                      f"-b 'SESSDATA={sessdata}' " \
                      f"-F 'csrf={bili_jct}'"

    process = subprocess.Popen(preupload_image, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    curl_output, error = process.communicate()
    curl_output_str = curl_output.decode('utf-8')
    response_json = json.loads(curl_output_str)

    if response_json.get('code') == 0:
        return response_json['data']['image_url']
    else:
        print(f"Failed to upload image: {file_path}", response_json['data']['image_url'])
        return None
print(f"okkkk")
print(group_B)
# 准备上传图片
for isbn in group_A.union(group_B):
    # 下载图片
    file_path = download_image(isbn, cache_directory) # 小图路径，要上传b站图床的
    print(f"ok", isbn)
    # 如果下载成功，上传图片
    if file_path:
        image_url = upload_image(file_path, sessdata=sessdata, bili_jct=bili_jct)

        # 如果上传成功，处理上传结果
        if image_url: #图片在b站图床的链接
            file_size = os.path.getsize(file_path)

            pattern = re.compile(rf"({isbn})\.tif")
            additional_file_size = next((os.path.getsize(os.path.join(image_directory, f)) for f in os.listdir(image_directory) if pattern.search(f)), None)
            additional_file_size = int(additional_file_size / (1024 * 1024))
            # 添加到 uploaded_images_info 列表
            uploaded_images_info.append(ImageInfo(isbn=isbn, img_filename=os.path.basename(file_path), image_url=image_url, additional_file_size=additional_file_size))

#
for images_info in uploaded_images_info:
  print(images_info.additional_file_size, images_info.isbn)

# ... 省略之前的代码 ...

# 上传完成后，对A组和B组图片进行排序和分组
sorted_uploaded_images_info_A = sorted([img_info for img_info in uploaded_images_info if img_info.isbn in group_A], key=lambda x: x.additional_file_size, reverse=True)
sorted_uploaded_images_info_B = sorted([img_info for img_info in uploaded_images_info if img_info.isbn in group_B], key=lambda x: x.additional_file_size, reverse=True)
img_height_fixed = 500
img_width_fixed = 500
# 分组，每组最多九个

def group_images(image_info_list, group_name):
    grouped_images_info = [image_info_list[i:i + 9] for i in range(0, len(image_info_list), 9)]
    for group in grouped_images_info:
        # 构建raw_text，标注组别
        raw_text = f"{group_name}" + "\\n" + "\\n".join([f"{image_info.additional_file_size}MB" for image_info in group])
        # 构建pics json数组
        pics_json = json.dumps([{
            "img_src": image_info.image_url,
            "img_width": img_width_fixed,
            "img_height": img_height_fixed,
            "img_size": image_info.additional_file_size
        } for image_info in group])

        # 构建curl命令字符串
        curl_command = (
            f"curl -X POST 'https://api.bilibili.com/x/dynamic/feed/create/dyn?csrf={bili_jct}' \\\n"
            f"-b 'buvid3=114514;SESSDATA={sessdata};' \\\n"
            "--header 'Content-Type: application/json' \\\n"
            f"--data-raw '"
            + f"""
            {{
                "dyn_req": {{
                    "content": {{
                        "contents": [
                            {{
                                "raw_text": "{raw_text}",
                                "type": 1,
                                "biz_id": ""
                            }}
                        ]
                    }},
                    "pics": {pics_json},
                    "scene": 2
                }}
            }}
            '
            """
        )

        # 使用subprocess.Popen执行curl命令
        process = subprocess.Popen(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        curl_output, error = process.communicate()

        # 打印输出和错误信息
        print(curl_output.decode())
        if error:
            print(error.decode())

# 先上传A组图片
group_images(sorted_uploaded_images_info_A, "A组,新增")

# 然后上传B组图片
group_images(sorted_uploaded_images_info_B, "B组,改变")

import os
import shutil

# Define the folder to be deleted
temp_folder = 'image_directory'

# Check if the folder exists
if os.path.exists(temp_folder):
    # Delete the folder and all its contents
    shutil.rmtree(temp_folder)
    deletion_status = f"Folder '{temp_folder}' has been deleted."
else:
    deletion_status = f"Folder '{temp_folder}' does not exist."

deletion_status

import os
import shutil

# Define the folder to be deleted
temp_folder = 'cache_directory'

# Check if the folder exists
if os.path.exists(temp_folder):
    # Delete the folder and all its contents
    shutil.rmtree(temp_folder)
    deletion_status = f"Folder '{temp_folder}' has been deleted."
else:
    deletion_status = f"Folder '{temp_folder}' does not exist."

deletion_status

import os

# 尝试删除文件
file_path = 'data.json'
try:
    os.remove(file_path)
    deletion_status = f"文件 {file_path} 已被删除。"
except FileNotFoundError:
    deletion_status = f"文件 {file_path} 不存在，无法删除。"

deletion_status
