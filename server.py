import os
import sys
import logging
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from weather_api import CWAWeatherAPI

# Setup logging
# Ensure log directory exists
os.makedirs(os.path.dirname("/Users/scl/Library/Logs/Claude/mcp-server-taiwan-weather.log"), exist_ok=True)

# Configure logging with both file and console handlers
logger = logging.getLogger("taiwan-weather-mcp")
logger.setLevel(logging.INFO)

# File handler for logging to specified file
file_handler = logging.FileHandler("/Users/scl/Library/Logs/Claude/mcp-server-taiwan-weather.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Console handler for logging to stderr
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Load environment variables
load_dotenv()

# Initialize CWA API client
cwa_api = CWAWeatherAPI()

# Initialize FastMCP server
mcp = FastMCP("taiwan-weather")

@mcp.tool()
async def get_weather_forecast(location: Optional[str] = None, forecast_type: str = "36h") -> str:
    """Get weather forecast for a location in Taiwan.

    Args:
        location: City or district name in Taiwan (e.g. 臺北市, 高雄市)
        forecast_type: Type of forecast, either "36h" for 36-hour forecast or "7d" for 7-day forecast
    """
    try:
        # 確保地名使用正確的格式
        if location:
            if not any(suffix in location for suffix in ['市', '縣', '鄉', '鎮']):
                location = f"{location}市"
            logger.info(f"查詢天氣預報，地點: {location}")
        
        # 根據 forecast_type 參數選擇不同的預報類型
        logger.info(f"查詢{forecast_type}天氣預報，地點: {location if location else '全部地區'}")
        data = await cwa_api.get_weather_forecast(location=location, forecast_type=forecast_type)
        
        # 詳細記錄API回應結構
        logger.info(f"API回應基本結構: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        
        if "error" in data:
            logger.error(f"API返回錯誤: {data['error']}")
            return f"取得天氣預報資料時發生錯誤: {data['error']}"
        
        if "records" in data:
            logger.info(f"records 結構: {list(data['records'].keys()) if isinstance(data['records'], dict) else type(data['records'])}")
            
            # 檢查是否存在 'Locations' 欄位（API可能使用這個而非 'location'）
            if "Locations" in data["records"]:
                locations = data["records"]["Locations"]
                if "Location" in locations:  # 檢查 Locations 中是否有 Location 欄位
                    locations_data = locations["Location"]
                    logger.info(f"找到 {len(locations_data)} 個地點資料")
                    for i, loc in enumerate(locations_data[:2]):  # 只記錄前兩個地點以避免日誌過長
                        logger.info(f"地點 {i+1}: {loc.get('locationName', '未知')}")
                    
                    # 處理地點資料
                    result = []
                    for loc in locations_data:
                        # 如果指定了位置但不匹配，則跳過
                        if location and location not in loc["locationName"]:
                            logger.debug(f"跳過不匹配的地點: {loc['locationName']}")
                            continue
                            
                        loc_name = loc["locationName"]
                        logger.info(f"處理地點: {loc_name}")
                        
                        # 建立時間段到預報數據的映射
                        time_forecasts = {}
                        
                        if "weatherElement" not in loc:
                            logger.error(f"地點 {loc_name} 中缺少 weatherElement 欄位")
                            continue
                            
                        # 記錄天氣元素類型
                        weather_elements = [elem["elementName"] for elem in loc["weatherElement"]]
                        logger.info(f"地點 {loc_name} 的天氣元素: {weather_elements}")
                        
                        # 先找出所有時段
                        for element in loc["weatherElement"]:
                            if "time" not in element:
                                logger.error(f"元素 {element.get('elementName', '未知')} 中缺少 time 欄位")
                                continue
                                
                            for period in element["time"]:
                                if "startTime" not in period or "endTime" not in period:
                                    logger.error(f"時段缺少開始或結束時間")
                                    continue
                                    
                                time_key = (period["startTime"], period["endTime"])
                                if time_key not in time_forecasts:
                                    time_forecasts[time_key] = {
                                        "Wx": "未知",      # 天氣現象
                                        "WxCode": "",     # 天氣代碼
                                        "MaxT": "未知",    # 最高溫
                                        "MinT": "未知",    # 最低溫
                                        "PoP": "未知",     # 降雨機率
                                        "CI": "未知",      # 舒適度
                                    }
                                
                                # 根據元素類型更新資料
                                element_name = element["elementName"]
                                
                                # 檢查是否有 elementValue 或 parameter 欄位
                                if not ("elementValue" in period or "parameter" in period):
                                    logger.error(f"時段缺少 elementValue 或 parameter 欄位")
                                    continue
                                    
                                # 根據不同的 API 回應格式處理天氣元素值
                                if "elementValue" in period:
                                    # 處理 F-D0047-091 格式 (7天預報)
                                    if element_name == "天氣現象" and period["elementValue"]:
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
                                    elif element_name == "最高溫度" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "MaxTemperature" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MaxT"] = period["elementValue"][0].get("MaxTemperature", "未知")
                                            logger.info(f"解析最高溫度 (7天預報): {time_forecasts[time_key]['MaxT']}")
                                    elif element_name == "最低溫度" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "MinTemperature" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MinT"] = period["elementValue"][0].get("MinTemperature", "未知")
                                            logger.info(f"解析最低溫度 (7天預報): {time_forecasts[time_key]['MinT']}")
                                    elif element_name == "PoP" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["PoP"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析降雨機率 (PoP): {time_forecasts[time_key]['PoP']}")
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
                        
                        # 將每個時段的預報整理成易讀格式
                        forecasts = []
                        for (start_time, end_time), forecast in time_forecasts.items():
                            forecast_text = f"""
時間: {start_time} 至 {end_time}
天氣: {forecast['Wx']}
溫度: {forecast['MinT']}°C 至 {forecast['MaxT']}°C
降雨機率: {forecast['PoP']}%
舒適度: {forecast['CI']}"""
                            forecasts.append(forecast_text.strip())
                        
                        if forecasts:
                            result.append(f"\n{loc_name}天氣預報:\n" + "\n---\n".join(forecasts))
                    
                    if result:
                        return "\n==========\n".join(result)
            
            # 檢查老的 API 格式 (location 欄位)
            elif "location" in data["records"]:
                locations = data["records"]["location"]
                logger.info(f"找到 {len(locations)} 個地點資料 (使用舊格式)")
                # 這裡保留原始的處理邏輯以保持兼容性
                if "location" in data["records"]:
                    logger.info(f"records 結構: {list(data['records'].keys()) if isinstance(data['records'], dict) else type(data['records'])}")
                    
                    if "location" in data["records"]:
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
                        
                        if "weatherElement" not in loc:
                            logger.error(f"地點 {loc_name} 中缺少 weatherElement 欄位")
                            continue
                            
                        # 記錄天氣元素類型
                        weather_elements = [elem["elementName"] for elem in loc["weatherElement"]]
                        logger.info(f"地點 {loc_name} 的天氣元素: {weather_elements}")
                        
                        # 先找出所有時段
                        for element in loc["weatherElement"]:
                            if "time" not in element:
                                logger.error(f"元素 {element.get('elementName', '未知')} 中缺少 time 欄位")
                                continue
                                
                            for period in element["time"]:
                                if "startTime" not in period or "endTime" not in period:
                                    logger.error(f"時段缺少開始或結束時間")
                                    continue
                                    
                                time_key = (period["startTime"], period["endTime"])
                                if time_key not in time_forecasts:
                                    time_forecasts[time_key] = {
                                        "Wx": "未知",      # 天氣現象
                                        "WxCode": "",     # 天氣代碼
                                        "MaxT": "未知",    # 最高溫
                                        "MinT": "未知",    # 最低溫
                                        "PoP": "未知",     # 降雨機率
                                        "CI": "未知",      # 舒適度
                                    }
                                
                                # 根據元素類型更新資料
                                element_name = element["elementName"]
                                
                                # 檢查是否有 elementValue 或 parameter 欄位
                                if not ("elementValue" in period or "parameter" in period):
                                    logger.error(f"時段缺少 elementValue 或 parameter 欄位")
                                    continue
                                    
                                # 根據不同的 API 回應格式處理天氣元素值
                                if "elementValue" in period:
                                    # 處理 F-D0047-091 格式 (7天預報)
                                    if element_name == "天氣現象" and period["elementValue"]:
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
                                    elif element_name == "最高溫度" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "MaxTemperature" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MaxT"] = period["elementValue"][0].get("MaxTemperature", "未知")
                                            logger.info(f"解析最高溫度 (7天預報): {time_forecasts[time_key]['MaxT']}")
                                    elif element_name == "最低溫度" and period["elementValue"]:
                                        if len(period["elementValue"]) > 0 and "MinTemperature" in period["elementValue"][0]:
                                            time_forecasts[time_key]["MinT"] = period["elementValue"][0].get("MinTemperature", "未知")
                                            logger.info(f"解析最低溫度 (7天預報): {time_forecasts[time_key]['MinT']}")
                                    elif element_name == "PoP" and period["elementValue"]:
                                        if "value" in period["elementValue"][0]:
                                            time_forecasts[time_key]["PoP"] = period["elementValue"][0].get("value", "未知")
                                            logger.info(f"解析降雨機率 (PoP): {time_forecasts[time_key]['PoP']}")
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
                        
                        # 將每個時段的預報整理成易讀格式
                        forecasts = []
                        for (start_time, end_time), forecast in time_forecasts.items():
                            forecast_text = f"""
時間: {start_time} 至 {end_time}
天氣: {forecast['Wx']}
溫度: {forecast['MinT']}°C 至 {forecast['MaxT']}°C
降雨機率: {forecast['PoP']}%
舒適度: {forecast['CI']}"""
                            forecasts.append(forecast_text.strip())
                        
                        if forecasts:
                            result.append(f"\n{loc_name}天氣預報:\n" + "\n---\n".join(forecasts))
                    
                    if not result:
                        logger.warning(f"未找到地點 {location if location else '所有地點'} 的天氣預報資料")
                        return f"找不到 {location} 的天氣預報資料" if location else "無法取得天氣預報資料"
                    
                    return "\n==========\n".join(result)
        
        if not data or "records" not in data or not data["records"]:
            logger.error("API回應中缺少 records 欄位")
            return "無法取得天氣預報資料。"
        
        logger.warning(f"未找到地點 {location if location else '所有地點'} 的天氣預報資料")
        return f"找不到 {location} 的天氣預報資料" if location else "無法取得天氣預報資料"
        
    except Exception as e:
        logger.error(f"取得天氣預報時發生錯誤: {str(e)}", exc_info=True)
        return f"取得天氣預報資料時發生錯誤: {str(e)}"

@mcp.tool()
async def get_weather_warnings(hazard_type: Optional[str] = None, location: Optional[str] = None) -> str:
    """Get active weather warnings for Taiwan.
    
    Args:
        hazard_type: Optional hazard type to filter results (e.g. 濃霧, 大雨, 豪雨)
        location: Optional location name to filter results (e.g. 臺北市, 高雄市)
    """
    try:
        logger.info(f"查詢天氣警特報，災害類型: {hazard_type if hazard_type else '全部類型'}，地點: {location if location else '全部地區'}")
        data = await cwa_api.get_weather_warnings(hazard_type=hazard_type, location=location)
        
        if "error" in data:
            logger.error(f"API返回錯誤: {data['error']}")
            return f"取得天氣警特報時發生錯誤: {data['error']}"
        
        if not data or "records" not in data:
            logger.error("API回應中缺少 records 欄位")
            return "無法取得天氣警特報資料"
            
        if "record" not in data["records"] or not data["records"]["record"]:
            logger.info("目前無天氣警特報")
            return "目前無天氣警特報"
            
        warnings = []
        for warning in data["records"]["record"]:
            # 獲取警特報類型
            hazard = warning.get("phenomena", "未知")
            
            # 獲取警特報等級
            hazard_level = warning.get("hazardLevel", "")
            if hazard_level:
                hazard = f"{hazard} ({hazard_level})"
            
            # 獲取發布時間
            issued_time = warning.get("datasetInfo", {}).get("publishTime", "未知")
            
            # 獲取影響地區
            affected_areas = warning.get("locationName", [])
            areas_text = "、".join(affected_areas[:10])
            if len(affected_areas) > 10:
                areas_text += " 等地區"
            
            # 獲取警特報內容
            content = warning.get("contents", {}).get("content", "無詳細資訊")
            
            warning_text = f"""
警特報類型: {hazard}
發布時間: {issued_time}
影響地區: {areas_text}
詳細內容: {content}
"""
            warnings.append(warning_text.strip())
            
        if warnings:
            return "\n==========\n".join(warnings)
        else:
            return "目前無天氣警特報"
        
    except Exception as e:
        logger.error(f"取得天氣警特報時發生錯誤: {str(e)}", exc_info=True)
        return f"取得天氣警特報時發生錯誤: {str(e)}"

@mcp.tool()
async def get_rainfall_data(location: Optional[str] = None) -> str:
    """Get rainfall observation data for a location in Taiwan.

    Args:
        location: City or district name in Taiwan (e.g. Taipei, Kaohsiung)
    """
    try:
        data = await cwa_api.get_rainfall_data(location=location)
        
        if not data or "records" not in data:
            return "Unable to fetch rainfall data."
            
        if "location" not in data["records"] or not data["records"]["location"]:
            return "No rainfall data available."
            
        observations = []
        for loc in data["records"]["location"]:
            loc_name = loc["locationName"]
            time = loc.get("time", {}).get("obsTime", "Unknown")
            
            obs_text = f"""
Location: {loc_name}
Time: {time}
Measurements:"""
            
            for element in loc.get("weatherElement", []):
                obs_text += f"\n{element['elementName']}: {element['elementValue']}"
                
            observations.append(obs_text)
            
        return "\n---\n".join(observations)
        
    except Exception as e:
        return f"Error fetching rainfall data: {str(e)}"

@mcp.tool()
async def get_weather_observation(location: Optional[str] = None) -> str:
    """Get current weather observation data for a location in Taiwan.

    Args:
        location: Optional location name to filter results (e.g. 臺北市, 高雄市)
    """
    try:
        # 確保地名使用正確的格式
        if location:
            # 移除不必要的轉換，讓 API 處理各種格式的地名
            location = location.strip()
            logger.info(f"查詢氣象觀測，地點: {location}")
        
        data = await cwa_api.get_weather_observation(location=location)
        
        # 詳細記錄API回應結構
        logger.info(f"API回應基本結構: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        
        if "error" in data:
            logger.error(f"API返回錯誤: {data['error']}")
            return f"取得氣象觀測資料時發生錯誤: {data['error']}"
        
        if "records" in data and "location" in data["records"]:
            locations = data["records"]["location"]
            logger.info(f"找到 {len(locations)} 個觀測站資料")
            
            if len(locations) == 0:
                logger.warning(f"未找到地點 {location if location else '所有地點'} 的觀測資料")
                return f"找不到 {location} 的觀測資料" if location else "無法取得觀測資料"
            
            result = []
            for loc in locations:
                loc_name = loc["locationName"]
                logger.info(f"處理觀測站: {loc_name}")
                
                if "weatherElement" not in loc:
                    logger.error(f"觀測站 {loc_name} 中缺少 weatherElement 欄位")
                    continue
                
                # 建立天氣要素字典
                weather_data = {}
                for element in loc["weatherElement"]:
                    if "elementName" in element and "elementValue" in element:
                        weather_data[element["elementName"]] = element["elementValue"]
                
                # 獲取天氣狀況
                weather_condition = weather_data.get("Weather", "未知")
                
                # 建立觀測資料文字
                obs_text = f"""
觀測站: {loc_name}
觀測時間: {loc.get("time", {}).get("obsTime", "未知")}
天氣狀況: {weather_condition}
溫度: {weather_data.get("TEMP", "未知")} °C
相對濕度: {weather_data.get("HUMD", "未知")} %
氣壓: {weather_data.get("PRES", "未知")} hPa
風向: {weather_data.get("WDIR", "未知")}°
風速: {weather_data.get("WDSD", "未知")} m/s
日累積雨量: {weather_data.get("24R", "未知")} mm
能見度: {weather_data.get("VisibilityDescription", "未知")}
日照時數: {weather_data.get("SunshineDuration", "未知")} 小時
紫外線指數: {weather_data.get("UVIndex", "未知")}"""
                
                result.append(obs_text.strip())
            
            if result:
                return "\n==========\n".join(result)
            else:
                logger.warning(f"未找到地點 {location if location else '所有地點'} 的觀測資料")
                return f"找不到 {location} 的觀測資料" if location else "無法取得觀測資料"
        
        logger.warning(f"未找到地點 {location if location else '所有地點'} 的觀測資料")
        return f"找不到 {location} 的觀測資料" if location else "無法取得觀測資料"
        
    except Exception as e:
        logger.error(f"取得氣象觀測資料時發生錯誤: {str(e)}", exc_info=True)
        return f"取得氣象觀測資料時發生錯誤: {str(e)}"

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')