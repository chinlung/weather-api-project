import os
import sys
from typing import Any, Optional, List, Dict
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from weather_api import CWAWeatherAPI
from logger_config import server_logger as logger, warnings_logger, forecast_logger, observations_logger

# 載入環境變數
load_dotenv()

# 初始化 CWA API 客戶端
cwa_api = CWAWeatherAPI()

# 初始化 FastMCP 伺服器
mcp = FastMCP("taiwan-weather")

@mcp.tool()
async def get_weather_forecast(location: Optional[str] = None, forecast_type: str = "36h", element_types: Optional[str] = None) -> dict:
    """Get weather forecast for a location in Taiwan.

    Args:
        location: City or district name in Taiwan (e.g. 臺北市, 高雄市)
        forecast_type: Type of forecast, either "36h" for 36-hour forecast or "7d" for 7-day forecast
        element_types: Optional comma-separated list of weather element types to include (七日預報專用)
                      預設只包含「天氣預報綜合描述」
                      可用類型：平均溫度、最高溫度、最低溫度、平均露點溫度、平均相對濕度、
                              最高體感溫度、最低體感溫度、最大舒適度指數、最小舒適度指數、
                              風速、風向、12小時降雨機率、天氣現象、紫外線指數、天氣預報綜合描述
    """
    try:
        # 確保地名使用正確的格式
        if location:
            if not any(suffix in location for suffix in ['市', '縣', '鄉', '鎮']):
                location = f"{location}市"
            forecast_logger.info(f"查詢天氣預報，地點: {location}")
        
        # 根據 forecast_type 參數選擇不同的預報類型
        forecast_logger.info(f"查詢{forecast_type}天氣預報，地點: {location if location else '全部地區'}")
        
        # 處理元素類型參數（僅適用於七日預報）
        parsed_element_types = None
        if forecast_type == "7d" and element_types:
            # 將逗號分隔的元素類型字串轉換為列表
            parsed_element_types = [elem.strip() for elem in element_types.split(',')]
            forecast_logger.info(f"指定的天氣元素類型: {parsed_element_types}")
        
        data = await cwa_api.get_weather_forecast(
            location=location, 
            forecast_type=forecast_type, 
            filter_response=True,
            element_types=parsed_element_types
        )
        
        # 詳細記錄API回應結構
        forecast_logger.info(f"API回應基本結構: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        
        if "error" in data:
            forecast_logger.error(f"API返回錯誤: {data['error']}")
            return {"error": f"取得天氣預報資料時發生錯誤: {data['error']}"}
        
        if "records" in data:
            forecast_logger.info(f"records 結構: {list(data['records'].keys()) if isinstance(data['records'], dict) else type(data['records'])}")
            
            # 如果是七日預報且有可用的元素類型資訊，添加到回應中
            if forecast_type == "7d" and "available_element_types" in data:
                forecast_logger.info(f"可用的天氣元素類型: {data['available_element_types']}")
                
                # 添加提示訊息，告知使用者可以查詢哪些類型的資料
                if not element_types:  # 如果使用者沒有指定元素類型
                    data["message"] = f"目前只顯示天氣預報綜合描述。您也可以查詢其他天氣資料類型，例如：{', '.join(data['available_element_types'][:5])}等。請在查詢時指定 element_types 參數。"
            
            # 檢查是否存在 'location' 欄位（36小時預報）或 'Locations' 欄位（7天預報）
            if "location" in data["records"]:
                locations_data = data["records"]["location"]
                forecast_logger.info(f"找到 {len(locations_data)} 個地點資料")
                
                # 處理地點資料
                result = []
                for loc in locations_data:
                    # 如果指定了位置但不匹配，則跳過
                    if location and location not in loc["locationName"]:
                        forecast_logger.debug(f"跳過不匹配的地點: {loc['locationName']}")
                        continue
                        
                    loc_name = loc["locationName"]
                    forecast_logger.info(f"處理地點: {loc_name}")
                    
                    # 建立回應格式
                    response = {
                        "location": loc_name,
                        "forecast_type": forecast_type,
                        "forecasts": []
                    }
                    result.append(response)
                    
                    # 建立時間段到預報數據的映射
                    time_forecasts = {}
                    
                    if "weatherElement" not in loc:
                        forecast_logger.error(f"地點 {loc_name} 中缺少 weatherElement 欄位")
                        continue
                    
                    # 處理每個天氣元素
                    for element in loc["weatherElement"]:
                        element_name = element["elementName"]
                        if "time" not in element:
                            continue
                            
                        for period in element["time"]:
                            if "startTime" not in period or "endTime" not in period:
                                continue
                                
                            time_key = (period["startTime"], period["endTime"])
                            if time_key not in time_forecasts:
                                time_forecasts[time_key] = {
                                    "start_time": period["startTime"],
                                    "end_time": period["endTime"],
                                    "Wx": None,
                                    "WxCode": None,
                                    "MaxT": None,
                                    "MinT": None,
                                    "PoP": None,
                                    "CI": None
                                }
                            
                            # 根據元素類型更新資料
                            if "parameter" in period:
                                param_name = period["parameter"].get("parameterName")
                                param_value = period["parameter"].get("parameterValue")
                                param_unit = period["parameter"].get("parameterUnit", "")
                                
                                if element_name == "Wx" and param_name:
                                    time_forecasts[time_key]["Wx"] = param_name
                                    time_forecasts[time_key]["WxCode"] = param_value
                                    forecast_logger.info(f"解析天氣現象: {param_name} (代碼: {param_value})")
                                elif element_name == "MaxT" and param_name:
                                    time_forecasts[time_key]["MaxT"] = f"{param_name}{param_unit}"
                                    forecast_logger.info(f"解析最高溫度: {param_name}{param_unit}")
                                elif element_name == "MinT" and param_name:
                                    time_forecasts[time_key]["MinT"] = f"{param_name}{param_unit}"
                                    forecast_logger.info(f"解析最低溫度: {param_name}{param_unit}")
                                elif element_name == "PoP" and param_name:
                                    time_forecasts[time_key]["PoP"] = f"{param_name}%"
                                    forecast_logger.info(f"解析降雨機率: {param_name}%")
                                elif element_name == "CI" and param_name:
                                    time_forecasts[time_key]["CI"] = param_name
                                    forecast_logger.info(f"解析舒適度: {param_name}")
                    
                    # 將每個時段的預報整理成結構化格式
                    for (start_time, end_time), forecast in sorted(time_forecasts.items()):
                        forecast_item = {
                            "start_time": start_time,
                            "end_time": end_time,
                            "weather": forecast['Wx'] or "未知",
                            "weather_code": forecast['WxCode'] or "",
                            "max_temperature": forecast['MaxT'] or "未知",
                            "min_temperature": forecast['MinT'] or "未知",
                            "precipitation_probability": forecast['PoP'] or "未知",
                            "comfort_index": forecast['CI'] or "未知"
                        }
                        response["forecasts"].append(forecast_item)
                    
                    # 如果有預報資料，加入結果列表
                    if response["forecasts"]:
                        forecast_logger.info(f"成功解析地點 {loc_name} 的預報資料，共 {len(response['forecasts'])} 筆")
                    else:
                        logger.warning(f"地點 {loc_name} 沒有預報資料")
                
                # 處理最終結果
                if not result:
                    logger.warning(f"未找到地點 {location if location else '所有地點'} 的天氣預報資料")
                    return {"error": f"找不到 {location} 的天氣預報資料" if location else "無法取得天氣預報資料"}
                elif len(result) == 1:
                    return result[0]
                else:
                    return {"locations": result}
                
            elif "Locations" in data["records"]:
                locations_list = data["records"]["Locations"]
                logger.info(f"Locations 欄位類型: {type(locations_list)}")
                
                # 尋找匹配的地點資料
                locations_data = []
                
                # 如果 Locations 是一個列表，需要遍歷它來找到 Location 欄位
                if isinstance(locations_list, list):
                    for locations_group in locations_list:
                        if "Location" in locations_group:
                            # 將所有地點資料加入列表
                            locations_data.extend(locations_group["Location"])
                # 如果 Locations 是一個字典，直接檢查是否有 Location 欄位
                elif isinstance(locations_list, dict) and "Location" in locations_list:
                    locations_data = locations_list["Location"]
                
                if locations_data:
                    logger.info(f"找到 {len(locations_data)} 個地點資料")
                    for i, loc in enumerate(locations_data[:2]):  # 只記錄前兩個地點以避免日誌過長
                        logger.info(f"地點 {i+1}: {loc.get('LocationName', '未知')}")
                    
                    # 處理地點資料
                    result = []
                    for loc in locations_data:
                        # 結構可能有所不同，檢查地點名稱欄位
                        loc_name_field = "LocationName" if "LocationName" in loc else "locationName"
                        if loc_name_field not in loc:
                            logger.debug(f"跳過缺少地點名稱的資料: {loc}")
                            continue
                            
                        # 如果指定了位置但不匹配，則跳過
                        loc_name = loc[loc_name_field]
                        if location:
                            # 建立可能的地點名稱變體
                            location_variants = [location]
                            if '臺' in location:
                                location_variants.append(location.replace('臺', '台'))
                            elif '台' in location:
                                location_variants.append(location.replace('台', '臺'))
                            
                            # 添加「市」和「縣」的變體
                            for base_variant in location_variants.copy():
                                if not base_variant.endswith('市') and not base_variant.endswith('縣'):
                                    location_variants.append(base_variant + '市')
                                    location_variants.append(base_variant + '縣')
                            
                            logger.info(f"地點變體: {location_variants}")
                            logger.info(f"正在匹配地點: {loc_name}")
                                
                            # 檢查是否為目標地點或其行政區
                            is_match = False
                            
                            # 先檢查是否為目標地點
                            # 使用更寬魅的匹配方式，檢查地點名稱是否包含目標地點名稱，或目標地點名稱是否包含地點名稱
                            if any(variant in loc_name or loc_name in variant for variant in location_variants):
                                is_match = True
                                logger.info(f"找到匹配的地點: {loc_name}")
                            else:
                                # 如果不是目標地點，檢查是否為其行政區
                                # 先檢查是否有行政區資料
                                districts = loc.get("Districts", [])
                                if districts:
                                    logger.info(f"檢查行政區: {[d.get('DistrictName', '') for d in districts]}")
                                    # 檢查每個行政區是否匹配
                                    for district in districts:
                                        district_name = district.get('DistrictName', '')
                                        if any(variant in district_name or district_name in variant for variant in location_variants):
                                            is_match = True
                                            logger.info(f"找到匹配的行政區: {district_name}")
                                            # 使用行政區的資料
                                            loc = district
                                            loc_name = district_name
                                            break
                            
                            if not is_match:
                                logger.debug(f"跳過不匹配的地點: {loc_name}")
                                continue
                                
                        logger.info(f"處理地點: {loc_name}")
                        
                        # 建立時間段到預報數據的映射
                        time_forecasts = {}
                        
                        # 檢查天氣元素欄位名稱，可能是 weatherElement 或 WeatherElement 或其他可能的欄位名稱
                        weather_element_field = None
                        possible_weather_element_fields = ["weatherElement", "WeatherElement", "weather_element", "Weather_Element"]
                        
                        # 先檢查常見的欄位名稱
                        for field in possible_weather_element_fields:
                            if field in loc and loc[field]:
                                weather_element_field = field
                                logger.info(f"在地點 {loc_name} 中找到天氣元素欄位: {field}")
                                break
                        
                        # 如果沒找到，嘗試尋找包含 'element' 或 'Element' 的欄位
                        if not weather_element_field:
                            for field in loc.keys():
                                if ('element' in field.lower() or 'weather' in field.lower()) and isinstance(loc[field], list):
                                    weather_element_field = field
                                    logger.info(f"在地點 {loc_name} 中找到可能的天氣元素欄位: {field}")
                                    break
                        
                        # 如果仍然沒有找到天氣元素欄位，輸出詳細的訊息並跳過處理
                        if not weather_element_field:
                            logger.error(f"地點 {loc_name} 中缺少天氣元素欄位")
                            # 輸出可用的欄位名稱以協助診斷
                            logger.error(f"可用的欄位名稱: {list(loc.keys())}")
                            continue
                            
                        # 檢查元素名稱欄位是 elementName 還是 ElementName 或其他可能的欄位名稱
                        element_name_field = None
                        possible_element_name_fields = ["elementName", "ElementName", "name", "Name", "element_name", "Element_Name"]
                        
                        # 確保天氣元素列表不為空
                        if loc[weather_element_field] and len(loc[weather_element_field]) > 0:
                            first_element = loc[weather_element_field][0]
                            
                            # 先檢查常見的欄位名稱
                            for field in possible_element_name_fields:
                                if field in first_element:
                                    element_name_field = field
                                    logger.info(f"找到元素名稱欄位: {field}")
                                    break
                            
                            # 如果沒找到，嘗試尋找包含 'name' 或 'Name' 的欄位
                            if not element_name_field:
                                for field in first_element.keys():
                                    if 'name' in field.lower() or 'element' in field.lower():
                                        element_name_field = field
                                        logger.info(f"找到可能的元素名稱欄位: {field}")
                                        break
                            
                            # 如果仍然沒有找到元素名稱欄位，輸出詳細的訊息
                            if not element_name_field:
                                logger.warning(f"無法確定元素名稱欄位，可用的欄位: {list(first_element.keys())}")
                                # 預設使用 elementName
                                element_name_field = "elementName"
                            
                        # 記錄天氣元素類型
                        # 輸出天氣元素的詳細資訊
                        logger.info(f"天氣元素欄位類型: {type(loc[weather_element_field])}")
                        logger.info(f"天氣元素欄位內容: {loc[weather_element_field][:100] if len(str(loc[weather_element_field])) > 100 else loc[weather_element_field]}")
                        
                        # 如果是字典，嘗試尋找其中的元素列表
                        if isinstance(loc[weather_element_field], dict):
                            logger.info(f"天氣元素欄位是字典，其中的鍵: {list(loc[weather_element_field].keys())}")
                            # 嘗試尋找可能包含元素列表的鍵
                            for key in loc[weather_element_field].keys():
                                if isinstance(loc[weather_element_field][key], list):
                                    logger.info(f"在鍵 {key} 中找到列表類型的值")
                                    # 更新天氣元素欄位
                                    weather_element_field = f"{weather_element_field}.{key}"
                                    break
                        
                        # 如果是字串，嘗試解析為 JSON
                        if isinstance(loc[weather_element_field], str):
                            try:
                                import json
                                parsed = json.loads(loc[weather_element_field])
                                logger.info(f"將字串解析為 JSON: {type(parsed)}")
                                # 更新天氣元素欄位
                                loc[weather_element_field] = parsed
                            except json.JSONDecodeError:
                                logger.warning(f"無法將天氣元素欄位解析為 JSON")
                        
                        # 如果是列表，檢查其內容
                        if isinstance(loc[weather_element_field], list):
                            if len(loc[weather_element_field]) > 0:
                                logger.info(f"天氣元素列表長度: {len(loc[weather_element_field])}")
                                logger.info(f"第一個元素的類型: {type(loc[weather_element_field][0])}")
                                if isinstance(loc[weather_element_field][0], dict):
                                    logger.info(f"第一個元素的鍵: {list(loc[weather_element_field][0].keys())}")
                            else:
                                logger.warning(f"天氣元素列表為空")
                                
                                # 如果天氣元素列表為空，嘗試從原始資料中擷取
                                logger.info(f"地點 {loc_name} 的可用欄位: {list(loc.keys())}")
                                
                                # 直接檢查原始資料中的天氣元素
                                if 'weatherElement' in loc and loc['weatherElement']:
                                    loc[weather_element_field] = loc['weatherElement']
                                    logger.info(f"從原始資料中擷取 weatherElement: {len(loc[weather_element_field])} 個元素")
                                elif 'WeatherElement' in loc and loc['WeatherElement']:
                                    loc[weather_element_field] = loc['WeatherElement']
                                    logger.info(f"從原始資料中擷取 WeatherElement: {len(loc[weather_element_field])} 個元素")
                        
                        # 列出天氣元素
                        try:
                            weather_elements = [elem.get(element_name_field, "未知") for elem in loc[weather_element_field]]
                            logger.info(f"地點 {loc_name} 的天氣元素: {weather_elements}")
                        except Exception as e:
                            logger.error(f"無法列出天氣元素: {str(e)}")
                            # 嘗試直接列出天氣元素欄位的內容
                            logger.info(f"天氣元素欄位內容: {loc[weather_element_field][:200] if len(str(loc[weather_element_field])) > 200 else loc[weather_element_field]}")
                        
                        # 先找出所有時段
                        for element in loc[weather_element_field]:
                            # 檢查元素名稱欄位是 elementName 還是 ElementName
                            element_name = element.get(element_name_field, element.get("elementName", element.get("ElementName", "未知")))
                            
                            # 檢查時間欄位是 time 還是 Time
                            time_field = None
                            for field in ["time", "Time"]:
                                if field in element:
                                    time_field = field
                                    break
                                    
                            if not time_field:
                                logger.error(f"元素 {element_name} 中缺少時間欄位 (time/Time)")
                                continue
                                
                            for period in element[time_field]:
                                # 檢查開始和結束時間欄位的不同格式
                                start_time_field = None
                                end_time_field = None
                                
                                for field in ["startTime", "StartTime"]:
                                    if field in period:
                                        start_time_field = field
                                        break
                                        
                                for field in ["endTime", "EndTime"]:
                                    if field in period:
                                        end_time_field = field
                                        break
                                        
                                if not start_time_field or not end_time_field:
                                    logger.error(f"時段缺少開始或結束時間")
                                    continue
                                    
                                time_key = (period[start_time_field], period[end_time_field])
                                if time_key not in time_forecasts:
                                    time_forecasts[time_key] = {
                                        "Wx": "未知",      # 天氣現象
                                        "WxCode": "",     # 天氣代碼
                                        "MaxT": "未知",    # 最高溫
                                        "MinT": "未知",    # 最低溫
                                        "PoP": "未知",     # 降雨機率
                                        "CI": "未知",      # 舒適度
                                        "weather_elements": {},  # 存儲所有元素資料
                                    }
                                
                                # 根據元素類型更新資料
                                # 檢查元素名稱欄位是 elementName 還是 ElementName
                                element_name = element.get(element_name_field, element.get("elementName", element.get("ElementName", "未知")))
                                
                                # 直接將整個元素資料保存到 weather_elements 字典中
                                # 這樣前端可以直接使用元素資料，不需要後端解析內部欄位結構
                                time_forecasts[time_key]["weather_elements"][element_name] = element
                                
                                # 記錄元素處理
                                logger.info(f"處理元素: {element_name} 於時段 {time_key[0]} 至 {time_key[1]}")
                                    
                                # 已經直接將整個元素資料保存到 weather_elements 字典中
                                # 不再需要解析元素值欄位
                                # 為了向後相容，我們仍然會將一些常用的元素值記錄到特定欄位
                                element_value_field = None
                                for field in ["elementValue", "ElementValue"]:
                                    if field in period and period[field]:
                                        element_value_field = field
                                        break
                                        
                                if element_value_field:
                                    # 處理「天氣預報綜合描述」元素 (7天預報)
                                    if element_name == "天氣預報綜合描述" and period[element_value_field]:
                                        if len(period[element_value_field]) > 0:
                                            # 嘗試從不同格式獲取描述
                                            element_value = period[element_value_field][0]
                                            description = "未知"
                                            
                                            # 檢查各種可能的欄位名稱
                                            for desc_field in ["value", "Value", "WeatherDescription", "weatherDescription"]:
                                                if desc_field in element_value:
                                                    description = element_value.get(desc_field, "未知")
                                                    break
                                            
                                            # 如果沒有找到任何已知的欄位，嘗試使用字串表示
                                            if description == "未知":
                                                description = str(element_value)
                                                logger.warning(f"使用備用方法解析天氣預報綜合描述: {description[:50]}..." if len(description) > 50 else f"使用備用方法解析天氣預報綜合描述: {description}")
                                                
                                            # 使用天氣預報綜合描述作為天氣現象
                                            time_forecasts[time_key]["Wx"] = description
                                            time_forecasts[time_key]["WxCode"] = ""  # 綜合描述沒有對應的代碼
                                            logger.info(f"解析天氣預報綜合描述: {description[:50]}..." if len(description) > 50 else f"解析天氣預報綜合描述: {description}")
                                    # 處理 F-D0047-091 格式 (7天預報)
                                    elif element_name == "天氣現象" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0:
                                            # 檢查是否有 Weather 和 WeatherCode 欄位
                                            if "Weather" in period["elementValue"][0]:
                                                time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("Weather", "未知")
                                                time_forecasts[time_key]["WxCode"] = period["elementValue"][0].get("WeatherCode", "")
                                                logger.info(f"解析天氣現象 (7天預報): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                            # 如果沒有 Weather 欄位，嘗試使用舊格式
                                            elif "value" in period["elementValue"][0]:
                                                time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("value", "未知")
                                                if len(period["elementValue"]) > 1:
                                                    time_forecasts[time_key]["WxCode"] = period["elementValue"][1].get("value", "")
                                                logger.info(f"解析天氣現象 (舊格式): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "Wx" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0:
                                            time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("value", "未知")
                                            if len(period["elementValue"]) > 1:
                                                time_forecasts[time_key]["WxCode"] = period["elementValue"][1].get("value", "")
                                            logger.info(f"解析天氣現象 (Wx): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "MaxT" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MaxT"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析最高溫度 (MaxT): {time_forecasts[time_key]['MaxT']}")
                                    elif element_name == "MinT" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MinT"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析最低溫度 (MinT): {time_forecasts[time_key]['MinT']}")
                                    elif element_name == "最高溫度":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["MaxTemperature", "value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["MaxT"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析最高溫度: {time_forecasts[time_key]['MaxT']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["MaxT"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析最高溫度: {time_forecasts[time_key]['MaxT']}")
                                                            break
                                                break
                                    elif element_name == "最低溫度":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["MinTemperature", "value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["MinT"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析最低溫度: {time_forecasts[time_key]['MinT']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["MinT"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析最低溫度: {time_forecasts[time_key]['MinT']}")
                                                            break
                                                break
                                    elif element_name == "PoP" or element_name == "降雨機率":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["PoP"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析降雨機率: {time_forecasts[time_key]['PoP']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["PoP"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析降雨機率: {time_forecasts[time_key]['PoP']}")
                                                            break
                                                break
                                    elif element_name == "12小時降雨機率" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "ProbabilityOfPrecipitation" in period["elementValue"][0]:
                                            time_forecasts[time_key]["PoP"] = period["elementValue"][0].get("ProbabilityOfPrecipitation", "未知")
                                            logger.info(f"解析降雨機率 (7天預報): {time_forecasts[time_key]['PoP']}")
                                    elif element_name == "CI" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["CI"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析舒適度 (CI): {time_forecasts[time_key]['CI']}")
                                elif "parameter" in period:
                                    # 處理 F-C0032-001 格式 (36小時預報)
                                    if element_name == "Wx" and period["parameter"]:
                                        time_forecasts[time_key]["Wx"] = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["WxCode"] = period["parameter"].get("parameterValue", "")
                                        logger.info(f"解析天氣現象: {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "MaxT" and period["parameter"]:
                                        # 最高溫度可能有單位資訊
                                        temp_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["MaxT"] = temp_value
                                        logger.info(f"解析最高溫度: {temp_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "MinT" and period["parameter"]:
                                        # 最低溫度可能有單位資訊
                                        temp_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["MinT"] = temp_value
                                        logger.info(f"解析最低溫度: {temp_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "PoP" and period["parameter"]:
                                        # 降雨機率可能有單位資訊
                                        pop_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["PoP"] = pop_value
                                        logger.info(f"解析降雨機率: {pop_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "CI" and period["parameter"]:
                                        time_forecasts[time_key]["CI"] = period["parameter"].get("parameterName", "未知")
                                        logger.info(f"解析舒適度: {time_forecasts[time_key]['CI']}")
                        
                        logger.info(f"地點 {loc_name} 的時段數: {len(time_forecasts)}")
                        
                        # 建立回應格式
                        response = {
                            "location": loc_name,
                            "forecast_type": forecast_type,
                            "forecasts": []
                        }
                        
                        # 收集可用的天氣元素類型
                        available_element_types = []
                        for element in loc.get("weatherElement", []):
                            element_name = element.get("elementName")
                            if element_name and element_name not in available_element_types:
                                available_element_types.append(element_name)
                        
                        # 將可用的天氣元素類型添加到回應中
                        response["available_element_types"] = available_element_types
                        
                        # 檢查是否只要求「天氣預報綜合描述」元素
                        only_weather_description = element_types and element_types == "天氣預報綜合描述"
                        
                        # 如果沒有指定元素類型，預設只顯示天氣預報綜合描述
                        if not element_types:
                            only_weather_description = True
                            response["message"] = f"目前只顯示天氣預報綜合描述。您也可以查詢其他天氣資料類型，例如：{', '.join(available_element_types[:5])}等。請在查詢時指定 element_types 參數。"
                        
                        # 將每個時段的預報整理成結構化格式
                        for (start_time, end_time), forecast in sorted(time_forecasts.items()):
                            if only_weather_description:
                                # 如果只要求綜合描述，則只返回時間和描述
                                forecast_item = {
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "weather_description": forecast['Wx']
                                }
                            else:
                                # 否則返回完整的天氣資訊
                                forecast_item = {
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "weather": forecast['Wx'],
                                    "weather_code": forecast['WxCode'] if forecast['WxCode'] != "" else None,
                                    "temperature": {
                                        "min": float(forecast['MinT']) if forecast['MinT'] != "未知" and forecast['MinT'].replace('.', '', 1).isdigit() else None,
                                        "max": float(forecast['MaxT']) if forecast['MaxT'] != "未知" and forecast['MaxT'].replace('.', '', 1).isdigit() else None
                                    },
                                    "precipitation_probability": float(forecast['PoP']) if forecast['PoP'] != "未知" and forecast['PoP'].replace('.', '', 1).isdigit() else None,
                                    "comfort": forecast['CI'] if forecast['CI'] != "未知" else None
                                }
                                
                                # 如果有指定元素類型且不是預設的「天氣預報綜合描述」，則加入該元素的資料
                                if element_types and element_types != "天氣預報綜合描述" and "weather_elements" in forecast:
                                    # 將使用者指定的元素類型資料加入回應
                                    requested_elements = [e.strip() for e in element_types.split(",")] if isinstance(element_types, str) else element_types
                                    if isinstance(requested_elements, list):
                                        # 如果指定了特定元素，則只回傳該元素的資料，不包含其他欄位
                                        # 這樣可以減少回應的大小，並使前端更容易處理
                                        forecast_item = {
                                            "start_time": start_time,
                                            "end_time": end_time,
                                            "weather_elements": {}
                                        }
                                        
                                        for elem_name, elem_data in forecast["weather_elements"].items():
                                            if elem_name in requested_elements:
                                                # 直接將整個元素資料加入回應
                                                # 不在後端分析元素內的欄位結構，讓前端自行處理
                                                forecast_item["weather_elements"][elem_name] = elem_data
                                                logger.info(f"加入元素 {elem_name} 到回應中")
                                                

                                    else:
                                        logger.warning(f"無法解析元素類型: {requested_elements}")
                            response["forecasts"].append(forecast_item)
                        
                        # 如果有預報資料，加入結果列表
                        if response["forecasts"]:
                            logger.info(f"成功解析地點 {loc_name} 的七日預報資料，共 {len(response['forecasts'])} 筆")
                            result.append(response)
                        else:
                            logger.warning(f"地點 {loc_name} 沒有七日預報資料")
                    
                    # 處理最終結果
                    if not result:
                        logger.warning(f"未找到地點 {location if location else '所有地點'} 的七日天氣預報資料")
                        return {"error": f"找不到 {location} 的七日天氣預報資料" if location else "無法取得七日天氣預報資料"}
                    elif len(result) == 1:
                        return result[0]
                    else:
                        return {"locations": result}
            
            # 檢查老的 API 格式 (location 欄位)
            elif "location" in data["records"]:
                locations = data["records"]["location"]
                logger.info(f"找到 {len(locations)} 個地點資料")
                for i, loc in enumerate(locations[:2]):  # 只記錄前兩個地點以避免日誌過長
                    logger.info(f"地點 {i+1}: {loc.get('locationName', '未知')}")
                    
                    if not data or "records" not in data or not data["records"]:
                        logger.error("API回應中缺少 records 欄位")
                        return "無法取得天氣預報資料。"
                        
                    records = data["records"]
                    if "location" not in records or not records["location"]:
                        logger.error("records 中缺少 location 欄位")
                        return "無可用的天氣預報資料。"
                        
                    result = []
                    for loc in records["location"]:
                        # 如果指定了位置但不匹配，則跳過
                        if location and location not in loc["locationName"]:
                            logger.debug(f"跳過不匹配的地點: {loc['locationName']}")
                            continue
                            
                        loc_name = loc["locationName"]
                        logger.info(f"處理地點: {loc_name}")
                        
                        # 建立時間段到預報數據的映射
                        time_forecasts = {}
                        
                        # 檢查天氣元素欄位名稱，可能是 weatherElement 或 WeatherElement 或其他可能的欄位名稱
                        weather_element_field = None
                        possible_weather_element_fields = ["weatherElement", "WeatherElement", "weather_element", "Weather_Element"]
                        
                        # 先檢查常見的欄位名稱
                        for field in possible_weather_element_fields:
                            if field in loc and loc[field]:
                                weather_element_field = field
                                logger.info(f"在地點 {loc_name} 中找到天氣元素欄位: {field}")
                                break
                        
                        # 如果沒找到，嘗試尋找包含 'element' 或 'Element' 的欄位
                        if not weather_element_field:
                            for field in loc.keys():
                                if ('element' in field.lower() or 'weather' in field.lower()) and isinstance(loc[field], list):
                                    weather_element_field = field
                                    logger.info(f"在地點 {loc_name} 中找到可能的天氣元素欄位: {field}")
                                    break
                        
                        # 如果仍然沒有找到天氣元素欄位，輸出詳細的訊息並跳過處理
                        if not weather_element_field:
                            logger.error(f"地點 {loc_name} 中缺少天氣元素欄位")
                            # 輸出可用的欄位名稱以協助診斷
                            logger.error(f"可用的欄位名稱: {list(loc.keys())}")
                            continue
                            
                        # 檢查元素名稱欄位是 elementName 還是 ElementName 或其他可能的欄位名稱
                        element_name_field = None
                        possible_element_name_fields = ["elementName", "ElementName", "name", "Name", "element_name", "Element_Name"]
                        
                        # 確保天氣元素列表不為空
                        if loc[weather_element_field] and len(loc[weather_element_field]) > 0:
                            first_element = loc[weather_element_field][0]
                            
                            # 先檢查常見的欄位名稱
                            for field in possible_element_name_fields:
                                if field in first_element:
                                    element_name_field = field
                                    logger.info(f"找到元素名稱欄位: {field}")
                                    break
                            
                            # 如果沒找到，嘗試尋找包含 'name' 或 'Name' 的欄位
                            if not element_name_field:
                                for field in first_element.keys():
                                    if 'name' in field.lower() or 'element' in field.lower():
                                        element_name_field = field
                                        logger.info(f"找到可能的元素名稱欄位: {field}")
                                        break
                            
                            # 如果仍然沒有找到元素名稱欄位，輸出詳細的訊息
                            if not element_name_field:
                                logger.warning(f"無法確定元素名稱欄位，可用的欄位: {list(first_element.keys())}")
                                # 預設使用 elementName
                                element_name_field = "elementName"
                            
                        # 記錄天氣元素類型
                        # 輸出天氣元素的詳細資訊
                        logger.info(f"天氣元素欄位類型: {type(loc[weather_element_field])}")
                        logger.info(f"天氣元素欄位內容: {loc[weather_element_field][:100] if len(str(loc[weather_element_field])) > 100 else loc[weather_element_field]}")
                        
                        # 如果是字典，嘗試尋找其中的元素列表
                        if isinstance(loc[weather_element_field], dict):
                            logger.info(f"天氣元素欄位是字典，其中的鍵: {list(loc[weather_element_field].keys())}")
                            # 嘗試尋找可能包含元素列表的鍵
                            for key in loc[weather_element_field].keys():
                                if isinstance(loc[weather_element_field][key], list):
                                    logger.info(f"在鍵 {key} 中找到列表類型的值")
                                    # 更新天氣元素欄位
                                    weather_element_field = f"{weather_element_field}.{key}"
                                    break
                        
                        # 如果是字串，嘗試解析為 JSON
                        if isinstance(loc[weather_element_field], str):
                            try:
                                import json
                                parsed = json.loads(loc[weather_element_field])
                                logger.info(f"將字串解析為 JSON: {type(parsed)}")
                                # 更新天氣元素欄位
                                loc[weather_element_field] = parsed
                            except json.JSONDecodeError:
                                logger.warning(f"無法將天氣元素欄位解析為 JSON")
                        
                        # 如果是列表，檢查其內容
                        if isinstance(loc[weather_element_field], list):
                            if len(loc[weather_element_field]) > 0:
                                logger.info(f"天氣元素列表長度: {len(loc[weather_element_field])}")
                                logger.info(f"第一個元素的類型: {type(loc[weather_element_field][0])}")
                                if isinstance(loc[weather_element_field][0], dict):
                                    logger.info(f"第一個元素的鍵: {list(loc[weather_element_field][0].keys())}")
                            else:
                                logger.warning(f"天氣元素列表為空")
                                
                                # 如果天氣元素列表為空，嘗試從原始資料中擷取
                                logger.info(f"地點 {loc_name} 的可用欄位: {list(loc.keys())}")
                                
                                # 直接檢查原始資料中的天氣元素
                                if 'weatherElement' in loc and loc['weatherElement']:
                                    loc[weather_element_field] = loc['weatherElement']
                                    logger.info(f"從原始資料中擷取 weatherElement: {len(loc[weather_element_field])} 個元素")
                                elif 'WeatherElement' in loc and loc['WeatherElement']:
                                    loc[weather_element_field] = loc['WeatherElement']
                                    logger.info(f"從原始資料中擷取 WeatherElement: {len(loc[weather_element_field])} 個元素")
                        
                        # 列出天氣元素
                        try:
                            weather_elements = [elem.get(element_name_field, "未知") for elem in loc[weather_element_field]]
                            logger.info(f"地點 {loc_name} 的天氣元素: {weather_elements}")
                        except Exception as e:
                            logger.error(f"無法列出天氣元素: {str(e)}")
                            # 嘗試直接列出天氣元素欄位的內容
                            logger.info(f"天氣元素欄位內容: {loc[weather_element_field][:200] if len(str(loc[weather_element_field])) > 200 else loc[weather_element_field]}")
                        
                        # 先找出所有時段
                        for element in loc[weather_element_field]:
                            # 檢查元素名稱欄位是 elementName 還是 ElementName
                            element_name = element.get(element_name_field, element.get("elementName", element.get("ElementName", "未知")))
                            
                            # 檢查時間欄位是 time 還是 Time
                            time_field = None
                            for field in ["time", "Time"]:
                                if field in element:
                                    time_field = field
                                    break
                                    
                            if not time_field:
                                logger.error(f"元素 {element_name} 中缺少時間欄位 (time/Time)")
                                continue
                                
                            for period in element[time_field]:
                                # 檢查開始和結束時間欄位的不同格式
                                start_time_field = None
                                end_time_field = None
                                
                                for field in ["startTime", "StartTime"]:
                                    if field in period:
                                        start_time_field = field
                                        break
                                        
                                for field in ["endTime", "EndTime"]:
                                    if field in period:
                                        end_time_field = field
                                        break
                                        
                                if not start_time_field or not end_time_field:
                                    logger.error(f"時段缺少開始或結束時間")
                                    continue
                                    
                                time_key = (period[start_time_field], period[end_time_field])
                                if time_key not in time_forecasts:
                                    time_forecasts[time_key] = {
                                        "Wx": "未知",      # 天氣現象
                                        "WxCode": "",     # 天氣代碼
                                        "MaxT": "未知",    # 最高溫
                                        "MinT": "未知",    # 最低溫
                                        "PoP": "未知",     # 降雨機率
                                        "CI": "未知",      # 舒適度
                                        "weather_elements": {},  # 存儲所有元素資料
                                    }
                                
                                # 根據元素類型更新資料
                                # 檢查元素名稱欄位是 elementName 還是 ElementName
                                element_name = element.get(element_name_field, element.get("elementName", element.get("ElementName", "未知")))
                                
                                # 直接將整個元素資料保存到 weather_elements 字典中
                                # 這樣前端可以直接使用元素資料，不需要後端解析內部欄位結構
                                time_forecasts[time_key]["weather_elements"][element_name] = element
                                
                                # 記錄元素處理
                                logger.info(f"處理元素: {element_name} 於時段 {time_key[0]} 至 {time_key[1]}")
                                    
                                # 已經直接將整個元素資料保存到 weather_elements 字典中
                                # 不再需要解析元素值欄位
                                # 為了向後相容，我們仍然會將一些常用的元素值記錄到特定欄位
                                element_value_field = None
                                for field in ["elementValue", "ElementValue"]:
                                    if field in period and period[field]:
                                        element_value_field = field
                                        break
                                        
                                if element_value_field:
                                    # 處理「天氣預報綜合描述」元素 (7天預報)
                                    if element_name == "天氣預報綜合描述" and period[element_value_field]:
                                        if len(period[element_value_field]) > 0:
                                            # 嘗試從不同格式獲取描述
                                            element_value = period[element_value_field][0]
                                            description = "未知"
                                            
                                            # 檢查各種可能的欄位名稱
                                            for desc_field in ["value", "Value", "WeatherDescription", "weatherDescription"]:
                                                if desc_field in element_value:
                                                    description = element_value.get(desc_field, "未知")
                                                    break
                                            
                                            # 如果沒有找到任何已知的欄位，嘗試使用字串表示
                                            if description == "未知":
                                                description = str(element_value)
                                                logger.warning(f"使用備用方法解析天氣預報綜合描述: {description[:50]}..." if len(description) > 50 else f"使用備用方法解析天氣預報綜合描述: {description}")
                                                
                                            # 使用天氣預報綜合描述作為天氣現象
                                            time_forecasts[time_key]["Wx"] = description
                                            time_forecasts[time_key]["WxCode"] = ""  # 綜合描述沒有對應的代碼
                                            logger.info(f"解析天氣預報綜合描述: {description[:50]}..." if len(description) > 50 else f"解析天氣預報綜合描述: {description}")
                                    # 處理 F-D0047-091 格式 (7天預報)
                                    elif element_name == "天氣現象" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0:
                                            # 檢查是否有 Weather 和 WeatherCode 欄位
                                            if "Weather" in period["elementValue"][0]:
                                                time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("Weather", "未知")
                                                time_forecasts[time_key]["WxCode"] = period["elementValue"][0].get("WeatherCode", "")
                                                logger.info(f"解析天氣現象 (7天預報): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                            # 如果沒有 Weather 欄位，嘗試使用舊格式
                                            elif "value" in period["elementValue"][0]:
                                                time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("value", "未知")
                                                if len(period["elementValue"]) > 1:
                                                    time_forecasts[time_key]["WxCode"] = period["elementValue"][1].get("value", "")
                                                logger.info(f"解析天氣現象 (舊格式): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "Wx" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0:
                                            time_forecasts[time_key]["Wx"] = period["elementValue"][0].get("value", "未知")
                                            if len(period["elementValue"]) > 1:
                                                time_forecasts[time_key]["WxCode"] = period["elementValue"][1].get("value", "")
                                            logger.info(f"解析天氣現象 (Wx): {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "MaxT" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MaxT"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析最高溫度 (MaxT): {time_forecasts[time_key]['MaxT']}")
                                    elif element_name == "MinT" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MinT"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析最低溫度 (MinT): {time_forecasts[time_key]['MinT']}")
                                    elif element_name == "最高溫度":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["MaxTemperature", "value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["MaxT"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析最高溫度: {time_forecasts[time_key]['MaxT']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["MaxT"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析最高溫度: {time_forecasts[time_key]['MaxT']}")
                                                            break
                                                break
                                    elif element_name == "最低溫度":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["MinTemperature", "value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["MinT"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析最低溫度: {time_forecasts[time_key]['MinT']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["MinT"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析最低溫度: {time_forecasts[time_key]['MinT']}")
                                                            break
                                                break
                                    elif element_name == "PoP" or element_name == "降雨機率":
                                        # 支援不同的欄位名稱格式
                                        for value_field in ["elementValue", "ElementValue", "parameter", "Parameter"]:
                                            if value_field in period and period[value_field]:
                                                if isinstance(period[value_field], list) and len(period[value_field]) > 0:
                                                    for field in ["value", "Value", "parameterName", "ParameterName"]:
                                                        if field in period[value_field][0]:
                                                            time_forecasts[time_key]["PoP"] = period[value_field][0].get(field, "未知")
                                                            logger.info(f"解析降雨機率: {time_forecasts[time_key]['PoP']}")
                                                            break
                                                elif isinstance(period[value_field], dict):
                                                    for field in ["parameterName", "ParameterName", "value", "Value"]:
                                                        if field in period[value_field]:
                                                            time_forecasts[time_key]["PoP"] = period[value_field].get(field, "未知")
                                                            logger.info(f"解析降雨機率: {time_forecasts[time_key]['PoP']}")
                                                            break
                                                break
                                    elif element_name == "12小時降雨機率" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "ProbabilityOfPrecipitation" in period["elementValue"][0]:
                                            time_forecasts[time_key]["PoP"] = period["elementValue"][0].get("ProbabilityOfPrecipitation", "未知")
                                            logger.info(f"解析降雨機率 (7天預報): {time_forecasts[time_key]['PoP']}")
                                    elif element_name == "CI" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["CI"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析舒適度 (CI): {time_forecasts[time_key]['CI']}")
                                elif "parameter" in period:
                                    # 處理 F-C0032-001 格式 (36小時預報)
                                    if element_name == "Wx" and period["parameter"]:
                                        time_forecasts[time_key]["Wx"] = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["WxCode"] = period["parameter"].get("parameterValue", "")
                                        logger.info(f"解析天氣現象: {time_forecasts[time_key]['Wx']} (代碼: {time_forecasts[time_key]['WxCode']})")
                                    elif element_name == "MaxT" and period["parameter"]:
                                        # 最高溫度可能有單位資訊
                                        temp_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["MaxT"] = temp_value
                                        logger.info(f"解析最高溫度: {temp_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "MinT" and period["parameter"]:
                                        # 最低溫度可能有單位資訊
                                        temp_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["MinT"] = temp_value
                                        logger.info(f"解析最低溫度: {temp_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "PoP" and period["parameter"]:
                                        # 降雨機率可能有單位資訊
                                        pop_value = period["parameter"].get("parameterName", "未知")
                                        time_forecasts[time_key]["PoP"] = pop_value
                                        logger.info(f"解析降雨機率: {pop_value} {period['parameter'].get('parameterUnit', '')}")
                                    elif element_name == "CI" and period["parameter"]:
                                        time_forecasts[time_key]["CI"] = period["parameter"].get("parameterName", "未知")
                                        logger.info(f"解析舒適度: {time_forecasts[time_key]['CI']}")
                        
                        logger.info(f"地點 {loc_name} 的時段數: {len(time_forecasts)}")
                        
                        # 建立回應格式
                        response = {
                            "location": loc_name,
                            "forecast_type": forecast_type,
                            "forecasts": []
                        }
                        
                        # 收集可用的天氣元素類型
                        available_element_types = []
                        for element in loc.get("weatherElement", []):
                            element_name = element.get("elementName")
                            if element_name and element_name not in available_element_types:
                                available_element_types.append(element_name)
                        
                        # 將可用的天氣元素類型添加到回應中
                        response["available_element_types"] = available_element_types
                        
                        # 檢查是否只要求「天氣預報綜合描述」元素
                        only_weather_description = element_types and element_types == "天氣預報綜合描述"
                        
                        # 如果沒有指定元素類型，預設只顯示天氣預報綜合描述
                        if not element_types:
                            only_weather_description = True
                            response["message"] = f"目前只顯示天氣預報綜合描述。您也可以查詢其他天氣資料類型，例如：{', '.join(available_element_types[:5])}等。請在查詢時指定 element_types 參數。"
                        
                        # 將每個時段的預報整理成結構化格式
                        for (start_time, end_time), forecast in sorted(time_forecasts.items()):
                            if only_weather_description:
                                # 如果只要求綜合描述，則只返回時間和描述
                                forecast_item = {
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "weather_description": forecast['Wx']
                                }
                            else:
                                # 否則返回完整的天氣資訊
                                forecast_item = {
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "weather": forecast['Wx'],
                                    "weather_code": forecast['WxCode'] if forecast['WxCode'] != "" else None,
                                    "temperature": {
                                        "min": float(forecast['MinT']) if forecast['MinT'] != "未知" and forecast['MinT'].replace('.', '', 1).isdigit() else None,
                                        "max": float(forecast['MaxT']) if forecast['MaxT'] != "未知" and forecast['MaxT'].replace('.', '', 1).isdigit() else None
                                    },
                                    "precipitation_probability": float(forecast['PoP']) if forecast['PoP'] != "未知" and forecast['PoP'].replace('.', '', 1).isdigit() else None,
                                    "comfort": forecast['CI'] if forecast['CI'] != "未知" else None
                                }
                                
                                # 如果有指定元素類型且不是預設的「天氣預報綜合描述」，則加入該元素的資料
                                if element_types and element_types != "天氣預報綜合描述" and "weather_elements" in forecast:
                                    # 將使用者指定的元素類型資料加入回應
                                    requested_elements = [e.strip() for e in element_types.split(",")] if isinstance(element_types, str) else element_types
                                    if isinstance(requested_elements, list):
                                        # 如果指定了特定元素，則只回傳該元素的資料，不包含其他欄位
                                        # 這樣可以減少回應的大小，並使前端更容易處理
                                        forecast_item = {
                                            "start_time": start_time,
                                            "end_time": end_time,
                                            "weather_elements": {}
                                        }
                                        
                                        for elem_name, elem_data in forecast["weather_elements"].items():
                                            if elem_name in requested_elements:
                                                # 直接將整個元素資料加入回應
                                                # 不在後端分析元素內的欄位結構，讓前端自行處理
                                                forecast_item["weather_elements"][elem_name] = elem_data
                                                logger.info(f"加入元素 {elem_name} 到回應中")
                                                

                                    else:
                                        logger.warning(f"無法解析元素類型: {requested_elements}")
                            response["forecasts"].append(forecast_item)
                        
                        # 如果有預報資料，加入結果列表
                        if response["forecasts"]:
                            logger.info(f"成功解析地點 {loc_name} 的預報資料，共 {len(response['forecasts'])} 筆")
                            result.append(response)
                        else:
                            logger.warning(f"地點 {loc_name} 沒有預報資料")
                    
                    # 處理最終結果
                    if not result:
                        logger.warning(f"未找到地點 {location if location else '所有地點'} 的天氣預報資料")
                        return {"error": f"找不到 {location} 的天氣預報資料" if location else "無法取得天氣預報資料"}
                    elif len(result) == 1:
                        return result[0]
                    else:
                        return {"locations": result}
        
        if not data or "records" not in data or not data["records"]:
            logger.error("API回應中缺少 records 欄位")
            return {"error": "無法取得天氣預報資料"}
        
        logger.warning(f"未找到地點 {location if location else '所有地點'} 的天氣預報資料")
        return {"error": f"找不到 {location} 的天氣預報資料" if location else "無法取得天氣預報資料"}
        
    except Exception as e:
        logger.error(f"取得天氣預報時發生錯誤: {str(e)}", exc_info=True)
        return {"error": f"取得天氣預報資料時發生錯誤: {str(e)}"}

@mcp.tool()
async def get_weather_warnings(hazard_type: Optional[str] = None, location: Optional[str] = None) -> dict:
    """取得臺灣的氣象警特報資訊。
    
    Args:
        hazard_type: 可選的災害類型過濾條件 (例如: 濃霧, 大雨, 豪雨)
        location: 可選的地點名稱過濾條件 (例如: 臺北市, 高雄市)
    
    Returns:
        dict: 包含警特報資訊的字典，格式為 {"warnings": [...]} 或 {"error": "錯誤訊息"}
    """
    try:
        warnings_logger.info(f"查詢天氣警特報，災害類型: {hazard_type if hazard_type else '全部類型'}，地點: {location if location else '全部地區'}")
        data = await cwa_api.get_weather_warnings(hazard_type=hazard_type, location=location)
        
        # 檢查API回應是否有錯誤
        if "error" in data:
            warnings_logger.error(f"API返回錯誤: {data['error']}")
            return {"error": f"取得天氣警特報時發生錯誤: {data['error']}"}
        
        # 檢查API回應是否包含必要的資料結構
        if not data or "records" not in data:
            warnings_logger.error("API回應中缺少 records 欄位")
            return {"error": "無法取得天氣警特報資料"}
            
        # 檢查是否有警特報資料
        if "record" not in data["records"] or not data["records"]["record"]:
            warnings_logger.info("目前無天氣警特報")
            return {"warnings": []}
            
        # 處理警特報資料
        warnings = []
        for warning in data["records"]["record"]:
            # 如果指定了地點但不匹配，則跳過
            if location and location not in warning.get("locationName", ""):
                continue
                
            # 如果指定了災害類型但不匹配，則跳過
            if hazard_type and hazard_type not in warning.get("phenomena", ""):
                continue
                
            # 建立結構化的警特報資料
            warning_data = {
                "hazard_type": warning.get("phenomena", "未知"),
                "hazard_level": warning.get("hazardLevel", ""),
                "location": warning.get("locationName", []),
                "start_time": warning.get("validTime", {}).get("startTime", "未知"),
                "end_time": warning.get("validTime", {}).get("endTime", "未知"),
                "issued_time": warning.get("datasetInfo", {}).get("publishTime", "未知"),
                "content": warning.get("contents", {}).get("content", "無詳細資訊")
            }
            
            # 記錄詳細的警特報資訊，包括時間範圍
            warnings_logger.info(f"處理警特報: {warning_data['hazard_type']} - 地點: {warning_data['location']}, 時間: {warning_data['start_time']} 至 {warning_data['end_time']}")
            warnings.append(warning_data)
        
        warnings_logger.info(f"成功取得 {len(warnings)} 筆天氣警特報資料")
        return {"warnings": warnings}
        
    except Exception as e:
        warnings_logger.error(f"取得天氣警特報時發生錯誤: {str(e)}", exc_info=True)
        return {"error": f"取得天氣警特報時發生錯誤: {str(e)}"}

@mcp.tool()
async def get_rainfall_data(location: Optional[str] = None) -> dict:
    """取得臺灣的降雨觀測資料。

    Args:
        location: 臺灣的城市或地區名稱 (例如: 臺北市, 高雄市)
        
    Returns:
        dict: 包含降雨觀測資料的字典，格式為 {"observations": [...]} 或 {"error": "錯誤訊息"}
    """
    try:
        observations_logger.info(f"查詢降雨觀測資料，地點: {location if location else '全部地區'}")
        data = await cwa_api.get_rainfall_data(location=location)
        
        # 檢查API回應是否有錯誤
        if "error" in data:
            observations_logger.error(f"API返回錯誤: {data['error']}")
            return {"error": f"取得降雨觀測資料時發生錯誤: {data['error']}"}
        
        # 檢查API回應是否包含必要的資料結構
        if not data or "records" not in data:
            observations_logger.error("API回應中缺少 records 欄位")
            return {"error": "無法取得降雨觀測資料"}
            
        # 檢查是否有降雨觀測資料
        if "location" not in data["records"] or not data["records"]["location"]:
            observations_logger.warning("無降雨觀測資料可用")
            return {"observations": []}
            
        # 處理降雨觀測資料
        observations = []
        location_count = 0
        
        # 如果指定了地點，則只取前10筆資料，否則取前50筆資料
        max_records = 10 if location else 50
        
        for loc in data["records"]["location"]:
            # 限制回傳的資料數量
            if len(observations) >= max_records:
                observations_logger.info(f"已達到最大資料數量限制 {max_records} 筆")
                break
                
            # 獲取地點名稱，可能為空字串
            loc_name = loc.get("locationName", "")
            
            # 如果 locationName 為空，使用預設值
            if not loc_name:
                # 如果指定了地點，則使用指定的地點名稱
                if location:
                    loc_name = location
                else:
                    # 如果沒有指定地點，則使用預設值
                    loc_name = "觀測站點" + str(location_count + 1)
                    location_count += 1
            
            time = loc.get("time", {}).get("obsTime", "未知")
            
            # 建立結構化的觀測資料
            observation = {
                "location": loc_name,
                "time": time,
                "measurements": {}
            }
            
            # 處理每個天氣要素
            for element in loc.get("weatherElement", []):
                element_name = element.get("elementName", "")
                element_value = element.get("elementValue", "")
                if element_name:
                    observation["measurements"][element_name] = element_value
            
            observations.append(observation)
        
        observations_logger.info(f"成功取得 {len(observations)} 筆降雨觀測資料")
        return {"observations": observations}
        
    except Exception as e:
        observations_logger.error(f"取得降雨觀測資料時發生錯誤: {str(e)}", exc_info=True)
        return {"error": f"取得降雨觀測資料時發生錯誤: {str(e)}"}

@mcp.tool()
async def get_weather_observation(location: Optional[str] = None) -> dict:
    """取得臺灣的即時天氣觀測資料。

    Args:
        location: 可選的地點名稱過濾條件 (例如: 臺北市, 高雄市)
        
    Returns:
        dict: 包含天氣觀測資料的字典，格式為 {"observations": [...]} 或 {"error": "錯誤訊息"}
    """
    try:
        # 確保地名格式正確
        if location:
            location = location.strip()
            observations_logger.info(f"查詢氣象觀測，地點: {location}")
        else:
            observations_logger.info("查詢氣象觀測，地點: 全部地區")
        
        data = await cwa_api.get_weather_observation(location=location)
        
        # 檢查API回應是否有錯誤
        if "error" in data:
            observations_logger.error(f"API返回錯誤: {data['error']}")
            return {"error": f"取得氣象觀測資料時發生錯誤: {data['error']}"}
        
        # 檢查API回應是否包含必要的資料結構
        if not data or "records" not in data:
            observations_logger.error("API回應中缺少 records 欄位")
            return {"error": "無法取得氣象觀測資料"}
            
        # 檢查是否有觀測資料
        if "location" not in data["records"] or not data["records"]["location"]:
            observations_logger.warning(f"未找到地點 {location if location else '所有地點'} 的觀測資料")
            return {"observations": []}
            
        # 處理觀測資料
        observations = []
        for loc in data["records"]["location"]:
            # 如果指定了地點但不匹配，則跳過
            if location and location not in loc.get("locationName", ""):
                continue
                
            loc_name = loc.get("locationName", "未知")
            observations_logger.info(f"處理觀測站: {loc_name}")
            
            # 檢查是否有天氣要素資料
            if "weatherElement" not in loc:
                observations_logger.error(f"觀測站 {loc_name} 中缺少 weatherElement 欄位")
                continue
            
            # 建立結構化的觀測資料
            observation = {
                "location": loc_name,
                "time": loc.get("time", {}).get("obsTime", "未知"),
                "weather_elements": {}
            }
            
            # 處理每個天氣要素
            for element in loc["weatherElement"]:
                if "elementName" in element and "elementValue" in element:
                    element_name = element["elementName"]
                    element_value = element["elementValue"]
                    observation["weather_elements"][element_name] = element_value
                    
                    # 為常用的天氣要素設置快速存取屬性
                    if element_name == "TEMP":
                        observation["temperature"] = f"{element_value}°C"
                    elif element_name == "HUMD":
                        try:
                            humidity = float(element_value) * 100
                            observation["humidity"] = f"{humidity:.1f}%"
                        except:
                            observation["humidity"] = element_value
                    elif element_name == "Weather":
                        observation["weather"] = element_value
                    elif element_name == "WDIR":
                        observation["wind_direction"] = f"{element_value}°"
                    elif element_name == "WDSD":
                        observation["wind_speed"] = f"{element_value} m/s"
                    elif element_name == "24R":
                        observation["rainfall"] = f"{element_value} mm"
            
            observations.append(observation)
        
        observations_logger.info(f"成功取得 {len(observations)} 筆天氣觀測資料")
        return {"observations": observations}
        
    except Exception as e:
        observations_logger.error(f"取得氣象觀測資料時發生錯誤: {str(e)}", exc_info=True)
        return {"error": f"取得氣象觀測資料時發生錯誤: {str(e)}"}

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')