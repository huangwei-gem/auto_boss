"""查看 cityList 中 subLevelModelList 结构"""
import json

with open("city_debug.json", "r", encoding="utf-8") as f:
    data = json.load(f)

zp = data["zpData"]

# 1. cityList 各级城市展开
print("=== cityList ===")
all_cities = {}
for prov in zp["cityList"]:
    name = prov["name"]
    code = prov["code"]
    all_cities[name] = code
    sub = prov.get("subLevelModelList", [])
    for city in sub:
        city_name = city["name"]
        city_code = city["code"]
        all_cities[city_name] = city_code
        sub2 = city.get("subLevelModelList")
        if sub2:
            for district in sub2:
                all_cities[district["name"]] = district["code"]

print(f"cityList 展开后共 {len(all_cities)} 个城市/地区")
# 打印前 20 个
for i, (n, c) in enumerate(all_cities.items()):
    print(f"  {n} => {c}")
    if i > 30:
        print(f"  ... 共 {len(all_cities)} 个")
        break

# 2. hotCityList
print("\n=== hotCityList ===")
for city in zp["hotCityList"]:
    print(f"  {city['name']} => {city['code']}")

# 3. cityList 的顶层省份列表
print(f"\n=== cityList 顶层（省份/直辖市）===")
for prov in zp["cityList"]:
    sub = prov.get("subLevelModelList", [])
    print(f"  {prov['name']} ({prov['code']}) -> {len(sub)} 个子城市")
    # 打印子城市
    for city in sub:
        sub2 = city.get("subLevelModelList", [])
        print(f"    {city['name']} ({city['code']}) -> {len(sub2)} 个区")
