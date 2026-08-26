from DrissionPage import ChromiumPage
from urllib3.util.url import Url
# 实例化浏览器，应用配置
dp = ChromiumPage()
# 访问网址
base_url = f'https://www.zhipin.com'
dp.get(base_url)


# 监听这个端口
dp.listen.start('data/city.json')  # 开始监听，指定获取包含该文本的数据包



un_text = dp.ele(".user-nav").text
# print(type(un_text))
# print(un_text)
# 判断需不需要登录,看里面包不包含登录/注册
if "登录/注册" in un_text:
    # 需要登录
    print("需要登录")
    dp.get("https://www.zhipin.com/web/user/?ka=header-login")
    input("请手动登录，登录后按任意键继续")
    # 保存登录状态
    dp.save_cookies("zhipin_cookies")
    print("登录状态已保存")
else:
    # 不需要登录
    print("不需要登录")


# print(dp.url)
# print(dp.title)
# print("登录完成")

# 先刷新页面，获取城市数据
dp.refresh()
dp.wait(2)


# 建立城市和code的映射
city_dict = {}
# 获取数据包并且
for packet in dp.listen.steps():
    res = packet.response.body
    # 处理数据，提取城市列表
    city_list = res["zpData"]["hotCityList"]

    for city in city_list:
        city_dict[city["name"]] = city["code"]
        print(city["name"],city["code"])
    break



# 选择城市
city = "上海"
code = city_dict[city]

print("目前只支持热门城市:",city_dict.keys())
# 访问指定岗位岗位
job = "数据分析"
dp.get(f"https://www.zhipin.com/web/geek/jobs?query={job}&city={code}&industry=&position=")


# 滑到底部加载更多岗位，5次
for _ in range(5):
    try:
        dp.scroll.to_bottom()
        dp.wait(2)
    except Exception:
        print("页面被刷新，等待页面加载完成后重试...")
        dp.wait(3)
        dp.scroll.to_bottom()
        dp.wait(2)

job_url_elements = dp.eles(".job-name")
full_job_urls = []
for elem in job_url_elements:
    href = elem.attr("href")  # 获取href属性
    if href:
        full_url = href
        full_job_urls.append(full_url)
print("岗位链接列表:")
for url in full_job_urls:
    print(url)


# 返回岗位名称
job_name_list = dp.ele(".rec-job-list").texts()
# print(job_name_list)

# 处理数据，将URL与岗位信息匹配
processed_jobs = []
for i, job_str in enumerate(job_name_list):
    parts = job_str.split('\n')
    if len(parts) >= 4:
        job_info = {
            'job_name': '',
            'salary': '',
            'experience': parts[1],
            'education': parts[2],
            'company_location': parts[3],
            'raw': job_str,
            'url': full_job_urls[i] if i < len(full_job_urls) else ''  # 匹配对应的URL
        }
        # 处理职位名和薪资（第一部分）
        first_part = parts[0]
        # 尝试分离：找薪资部分的特征
        salary_markers = ['K', '元/月', '元/天', '薪']
        salary_start = len(first_part)
        for marker in salary_markers:
            idx = first_part.find(marker)
            if idx != -1 and idx < salary_start:
                salary_start = idx
        if salary_start < len(first_part):
            job_info['job_name'] = first_part[:salary_start].strip()
            job_info['salary'] = first_part[salary_start:].strip()
        else:
            job_info['job_name'] = first_part
        processed_jobs.append(job_info)


# 打印处理后的数据
# print("\n处理后的岗位信息:")
# for i, job in enumerate(processed_jobs, 1):
#     print(f"\n岗位 {i}:")
#     print(f"  职位名: {job['job_name']}")
#     print(f"  薪资: {job['salary']}")
#     print(f"  经验: {job['experience']}")
#     print(f"  学历: {job['education']}")
#     print(f"  公司/地点: {job['company_location']}")
#     print(f"  链接: {job['url']}")

for url in full_job_urls:
    # 访问岗位详情
    print(url)
    dp.get(url)
    # 如果之前已经沟通过，就不需要再沟通
    if dp.ele(".btn btn-startchat").text in "继续沟通":
        print("之前已经沟通过，不需要再沟通")
        continue
    
    # 活跃度
    boss_active_time = dp.ele(".boss-active-time").text
    print(boss_active_time)
    # 公司人数
    icon_scale = dp.ele(".icon-scale").text
    print(icon_scale)
    # 岗位描述
    job_sec_text = dp.ele(".job-sec-text").text
    print(job_sec_text)
    # 薪资
    salary = dp.ele(".salary").text
    print(salary)

    # # 访问岗位详情（只发文字版本）
    # dp.get(url)
    # # 点击立即沟通
    # dp.ele(".btn btn-startchat").click()
    # # 输入文字
    # message = "你好，？"
    # dp.ele(".input-area").input(message)
    # # 点击发送
    # dp.ele(".send-message").click()
    # dp.wait(1)


    # 访问岗位详情（发文字加上图片版本）
    dp.get(url)
    # 点击立即沟通
    dp.ele(".btn btn-startchat").click()
    # 输入文字
    message = "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。十分认可贵公司，希望能获得面试机会。"
    dp.ele(".input-area").input(message)
    # 点击发送
    dp.ele(".send-message").click()
    # 关闭当前窗口
    dp.ele(".icon-close").click()
    # 点击继续沟通
    dp.ele(".btn btn-startchat").click()
    # 上传图片 - 一次上传所有三个看板
    dp.ele(".toolbar-btn-content icon btn-sendimg tooltip tooltip-top").click.to_upload(r"./数据分析看板/看板1.png")
    dp.ele(".toolbar-btn-content icon btn-sendimg tooltip tooltip-top").click.to_upload(r"./数据分析看板/看板2.png")
    dp.ele(".toolbar-btn-content icon btn-sendimg tooltip tooltip-top").click.to_upload(r"./数据分析看板/看板3.png")
    # 测试一下
    break
    dp.wait(1)


